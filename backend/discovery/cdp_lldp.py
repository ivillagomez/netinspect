"""CDP / LLDP auto-discovery engine.

Walk a network starting from a seed IP, query each reachable switch for its
CDP / LLDP neighbor table, and recurse into newly found devices.

Two transport modes are supported:
  - SSH  : Netmiko session → 'show cdp/lldp neighbors detail' (any vendor)
  - SNMP : puresnmp async walks of CDP-MIB (Cisco) and LLDP-MIB (all vendors)
  - both : SNMP first, SSH fallback when SNMP returns nothing or is unavailable

Progress is yielded as DiscoveryEvent objects so callers can stream them
to the frontend via Server-Sent Events.
"""

import asyncio
import ipaddress
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import AsyncIterator, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=6, thread_name_prefix="discovery")

# ── Optional SNMP import (same pattern as cisco_snmp.py) ──────────────────────
try:
    from puresnmp import Client
    from puresnmp.credentials import V2C, V1
    HAS_SNMP = True
except ImportError:
    HAS_SNMP = False
    logger.debug("puresnmp not installed — SNMP discovery disabled")


# ── OID constants ──────────────────────────────────────────────────────────────

# CISCO-CDP-MIB cdpCacheTable  (Cisco-proprietary)
OID_CDP_TABLE = "1.3.6.1.4.1.9.9.23.1.2.1.1"
#   .3.<ifIdx>.<nbIdx>  cdpCacheAddressType  (1=IP)
#   .4.<ifIdx>.<nbIdx>  cdpCacheAddress      (raw IP bytes)
#   .6.<ifIdx>.<nbIdx>  cdpCacheDeviceId     (hostname string)
#   .7.<ifIdx>.<nbIdx>  cdpCacheDevicePort   (remote port string)
#   .8.<ifIdx>.<nbIdx>  cdpCachePlatform     (platform string)

# LLDP-MIB lldpRemTable (RFC 2922, vendor-neutral)
OID_LLDP_SYS_NAME  = "1.0.8802.1.1.2.1.4.1.1.9"   # lldpRemSysName
OID_LLDP_SYS_DESC  = "1.0.8802.1.1.2.1.4.1.1.5"   # lldpRemSysDesc
OID_LLDP_PORT_ID   = "1.0.8802.1.1.2.1.4.1.1.7"   # lldpRemPortId
#   all keyed by <timeFilter>.<localPortNum>.<remIndex>

# LLDP-MIB lldpRemManAddrTable — IPv4 address is encoded in the OID index:
#   <col>.<timeFilter>.<localPortNum>.<remIndex>.<addrSubtype>.<addrLen>.<b1>.<b2>.<b3>.<b4>
OID_LLDP_MGMT = "1.0.8802.1.1.2.1.4.2.1.4"        # lldpRemManAddrIfSubtype (walk trigger)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DiscoveredDevice:
    hostname:    str
    mgmt_ip:     str
    platform:    str = ""
    local_port:  str = ""   # our port facing the neighbor
    remote_port: str = ""   # their port facing us
    source:      str = "cdp"   # "cdp" | "lldp" | "snmp-cdp" | "snmp-lldp"
    device_type: str = "cisco_ios"   # best-guess Netmiko driver


@dataclass
class DiscoveryEvent:
    type:        str             # connecting | found | skip | error | done
    ip:          str  = ""
    hostname:    str  = ""
    platform:    str  = ""
    device_type: str  = ""
    reason:      str  = ""
    depth:       int  = 0
    devices: List[Dict] = field(default_factory=list)

    def to_sse(self) -> str:
        return f"data: {json.dumps(asdict(self))}\n\n"


# ── Scope / filter helpers ─────────────────────────────────────────────────────

def _in_scope(ip: str, scopes: List[str]) -> bool:
    """True if ip falls inside any of the provided CIDR scopes (empty = allow all)."""
    if not scopes:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for s in scopes:
        try:
            if addr in ipaddress.ip_network(s.strip(), strict=False):
                return True
        except ValueError:
            pass
    return False


def _guess_device_type(platform: str) -> str:
    """Map a CDP/LLDP platform string to a Netmiko device_type."""
    p = platform.lower()
    if any(k in p for k in ("aruba", "procurve", "hp j9", "hp j8", "arubaos", "aos-s")):
        return "aruba_os"
    if any(k in p for k in ("icx", "ruckus", "brocade", "fastiron", "turboiron")):
        return "cisco_ios"   # Ruckus ICX is Brocade / IOS-like CLI
    if any(k in p for k in ("extreme", "exos")):
        return "cisco_ios"   # reasonable fallback
    return "cisco_ios"


def _is_skippable(platform: str, hostname: str) -> Optional[str]:
    """Return a skip reason if this device should not be recursed into."""
    p = platform.lower()
    h = hostname.lower()
    if any(k in p for k in ("air-", "ap-", "aironet", "wave 2",
                             "catalyst 9120", "catalyst 9130")):
        return "access point"
    if any(k in h for k in ("-ap-", "_ap_", "-ap.", "ap01", "ap02", "-ap0")):
        return "access point"
    if any(k in p for k in ("asa", "firepower", "fortigate", "paloalto", "pa-")):
        return "firewall / security appliance"
    if any(k in p for k in ("router", "cisco 18", "cisco 19", "cisco 28",
                             "cisco 29", "cisco 38", "cisco 39", "isr", "asr")):
        return "router"
    return None


# ── OID helpers ────────────────────────────────────────────────────────────────

def _oid_suffix(full_oid: str, base_oid: str) -> Optional[List[int]]:
    """Return OID index as list of ints, or None if base doesn't match."""
    prefix = base_oid.rstrip(".")
    if not full_oid.startswith(prefix + "."):
        return None
    try:
        return [int(x) for x in full_oid[len(prefix) + 1:].split(".")]
    except ValueError:
        return None


def _decode_val(val) -> str:
    """Convert SNMP value to a clean string."""
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace").strip("\x00").strip()
    return str(val).strip() if val is not None else ""


# ── SSH-based neighbor discovery (runs in thread pool) ────────────────────────

def _ssh_get_neighbors(ip: str, username: str, password: str,
                       device_type: str, timeout: int) -> List[DiscoveredDevice]:
    """SSH into a switch, run CDP then LLDP, return combined neighbor list.
    Synchronous — must be called from a thread executor."""
    try:
        from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
    except ImportError:
        raise RuntimeError("netmiko not installed")

    conn_params = dict(
        device_type     = device_type,
        host            = ip,
        username        = username,
        password        = password,
        timeout         = timeout,
        session_timeout = timeout,
        fast_cli        = True,
    )

    conn = None
    try:
        conn = ConnectHandler(**conn_params)
        neighbors: List[DiscoveredDevice] = []

        # ── Try CDP ────────────────────────────────────────────────
        try:
            cdp_out = conn.send_command("show cdp neighbors detail", read_timeout=20)
            if cdp_out and "% CDP is not enabled" not in cdp_out and "Invalid input" not in cdp_out:
                neighbors.extend(_parse_cdp_neighbors(cdp_out))
        except Exception:
            pass

        # ── LLDP fallback ──────────────────────────────────────────
        if not neighbors:
            try:
                cmd = ("show lldp info remote-device detail"
                       if device_type.startswith("aruba")
                       else "show lldp neighbors detail")
                lldp_out = conn.send_command(cmd, read_timeout=20)
                if lldp_out and "Invalid input" not in lldp_out:
                    neighbors.extend(_parse_lldp_neighbors(lldp_out, device_type))
            except Exception:
                pass

        return neighbors

    except NetmikoAuthenticationException:
        raise RuntimeError("auth_failed")
    except NetmikoTimeoutException:
        raise RuntimeError("ssh_timeout")
    except Exception as exc:
        raise RuntimeError(f"ssh_error: {type(exc).__name__}")
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:
                pass


# ── SNMP-based neighbor discovery (async, no thread needed) ───────────────────

async def _snmp_get_neighbors(ip: str, community: str,
                               port: int = 161, version: str = "2c") -> List[DiscoveredDevice]:
    """Query CDP-MIB (Cisco) then LLDP-MIB via SNMP to discover neighbors.
    Returns empty list if puresnmp is not installed or SNMP is unreachable."""
    if not HAS_SNMP:
        raise RuntimeError("puresnmp not installed — run: pip install puresnmp")

    creds = V2C(community) if version != "1" else V1(community)
    neighbors: List[DiscoveredDevice] = []

    # ── Try CDP-MIB first (Cisco-specific) ───────────────────────
    try:
        neighbors = await _snmp_cdp_walk(ip, creds, port)
    except Exception as e:
        logger.debug("SNMP CDP walk %s: %s", ip, e)

    # ── LLDP-MIB fallback (all vendors) ─────────────────────────
    if not neighbors:
        try:
            neighbors = await _snmp_lldp_walk(ip, creds, port)
        except Exception as e:
            logger.debug("SNMP LLDP walk %s: %s", ip, e)

    if not neighbors:
        raise RuntimeError("snmp_no_data")

    return neighbors


async def _snmp_cdp_walk(ip: str, creds, port: int) -> List[DiscoveredDevice]:
    """Walk Cisco CDP-MIB cdpCacheTable and return DiscoveredDevice list."""
    entries: Dict[tuple, Dict[int, object]] = {}

    async with Client(ip, creds, port=port) as c:
        async for oid, value in c.bulkwalk(OID_CDP_TABLE):
            suffix = _oid_suffix(str(oid), OID_CDP_TABLE)
            # suffix: [attr, ifIndex, neighborIndex]
            if not suffix or len(suffix) < 3:
                continue
            attr, if_idx, nb_idx = suffix[0], suffix[1], suffix[2]
            key = (if_idx, nb_idx)
            entries.setdefault(key, {})[attr] = value

    devices = []
    for _key, attrs in entries.items():
        raw_host = attrs.get(6)            # cdpCacheDeviceId
        if not raw_host:
            continue
        hostname = _decode_val(raw_host).split(".")[0]
        if not hostname:
            continue

        # cdpCacheAddress (attr 4) is raw IP bytes
        addr_raw = attrs.get(4)
        if not addr_raw:
            continue
        try:
            addr_bytes = bytes(addr_raw) if not isinstance(addr_raw, bytes) else addr_raw
            if len(addr_bytes) < 4:
                continue
            mgmt_ip = ".".join(str(b) for b in addr_bytes[:4])
        except Exception:
            continue

        platform    = _decode_val(attrs.get(8, b""))[:80]
        remote_port = _decode_val(attrs.get(7, b""))

        devices.append(DiscoveredDevice(
            hostname    = hostname,
            mgmt_ip     = mgmt_ip,
            platform    = platform,
            remote_port = remote_port,
            source      = "snmp-cdp",
            device_type = _guess_device_type(platform),
        ))

    return devices


async def _snmp_lldp_walk(ip: str, creds, port: int) -> List[DiscoveredDevice]:
    """Walk LLDP-MIB lldpRemTable and extract neighbor info."""
    sys_names: Dict[tuple, str] = {}
    sys_descs:  Dict[tuple, str] = {}
    port_ids:   Dict[tuple, str] = {}
    mgmt_ips:   Dict[tuple, str] = {}

    async with Client(ip, creds, port=port) as c:

        # lldpRemSysName  (.9.<timeFilter>.<localPortNum>.<remIndex>)
        async for oid, value in c.bulkwalk(OID_LLDP_SYS_NAME):
            s = _oid_suffix(str(oid), OID_LLDP_SYS_NAME)
            if s and len(s) >= 3:
                sys_names[(s[1], s[2])] = _decode_val(value)

        # lldpRemSysDesc
        async for oid, value in c.bulkwalk(OID_LLDP_SYS_DESC):
            s = _oid_suffix(str(oid), OID_LLDP_SYS_DESC)
            if s and len(s) >= 3:
                sys_descs[(s[1], s[2])] = _decode_val(value)[:80]

        # lldpRemPortId
        async for oid, value in c.bulkwalk(OID_LLDP_PORT_ID):
            s = _oid_suffix(str(oid), OID_LLDP_PORT_ID)
            if s and len(s) >= 3:
                port_ids[(s[1], s[2])] = _decode_val(value)

        # lldpRemManAddrTable — IPv4 encoded in OID index:
        # suffix: [timeFilter, localPortNum, remIndex, addrSubtype, addrLen, b1, b2, b3, b4]
        async for oid, _value in c.bulkwalk(OID_LLDP_MGMT):
            s = _oid_suffix(str(oid), OID_LLDP_MGMT)
            if not s or len(s) < 9:
                continue
            # addrSubtype=1 → IPv4; addrLen=4
            if s[3] != 1 or s[4] != 4:
                continue
            key = (s[1], s[2])
            mgmt_ips[key] = ".".join(str(x) for x in s[5:9])

    devices = []
    for key, hostname in sys_names.items():
        hostname = hostname.split(".")[0]
        if not hostname:
            continue
        mgmt_ip = mgmt_ips.get(key)
        if not mgmt_ip:
            continue
        platform    = sys_descs.get(key, "")
        remote_port = port_ids.get(key, "")
        devices.append(DiscoveredDevice(
            hostname    = hostname,
            mgmt_ip     = mgmt_ip,
            platform    = platform,
            remote_port = remote_port,
            source      = "snmp-lldp",
            device_type = _guess_device_type(platform),
        ))

    return devices


# ── SSH CLI parsers ────────────────────────────────────────────────────────────

def _parse_cdp_neighbors(output: str) -> List[DiscoveredDevice]:
    """Parse 'show cdp neighbors detail' output into DiscoveredDevice list."""
    devices = []
    for block in re.split(r'-{5,}', output):
        if not block.strip():
            continue
        hostname = _re_first(r'Device ID:\s*(\S+)', block)
        if not hostname:
            continue
        mgmt_ip = (
            _re_first(r'IP address:\s*(\d+\.\d+\.\d+\.\d+)', block)
            or _re_first(r'IPv4 [Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)', block)
        )
        if not mgmt_ip:
            continue
        platform    = _re_first(r'Platform:\s*([^,\n]+)', block) or ""
        local_port  = _re_first(r'Interface:\s*([^,\n]+)', block) or ""
        remote_port = _re_first(r'Port ID \(outgoing port\):\s*(\S+)', block) or ""
        hostname = hostname.split(".")[0]
        devices.append(DiscoveredDevice(
            hostname    = hostname,
            mgmt_ip     = mgmt_ip.strip(),
            platform    = platform.strip(),
            local_port  = local_port.strip(),
            remote_port = remote_port.strip(),
            source      = "cdp",
            device_type = _guess_device_type(platform),
        ))
    return devices


def _parse_lldp_neighbors(output: str, device_type: str = "cisco_ios") -> List[DiscoveredDevice]:
    """Parse 'show lldp neighbors detail' for Cisco IOS, Aruba AOS-S, Ruckus ICX."""
    devices = []
    blocks = re.split(r'-{5,}', output)
    if len(blocks) <= 1:
        blocks = re.split(r'(?=Local [Pp]ort\s*:)', output)

    for block in blocks:
        if not block.strip():
            continue

        hostname = (
            _re_first(r'System Name[:\s]+(\S+)', block)
            or _re_first(r"Neighbor's system name[:\s]+(\S+)", block)
            or _re_first(r'SysName\s*:\s*(\S+)', block)
        )
        if not hostname:
            continue

        mgmt_ip = (
            _re_first(r'Management Addresses?.*?IP(?:v4)?:\s*(\d+\.\d+\.\d+\.\d+)', block, re.S)
            or _re_first(r'Mgmt Address\s*:\s*(\d+\.\d+\.\d+\.\d+)', block)
            or _re_first(r"Management address \(IPv4\):\s*(\d+\.\d+\.\d+\.\d+)", block)
            or _re_first(r'IP(?:v4)? address:\s*(\d+\.\d+\.\d+\.\d+)', block)
        )
        if not mgmt_ip:
            continue

        platform = (
            _re_first(r'System Description[:\s]*\n\s*(.+)', block)
            or _re_first(r"Neighbor's system description[:\s]+(.+)", block)
            or _re_first(r'System Descr\s*:\s*(.+)', block)
            or ""
        )
        local_port = (
            _re_first(r'Local Intf[:\s]+(\S+)', block)
            or _re_first(r'Local [Pp]ort\s*:\s*(\S+)', block)
            or ""
        )
        remote_port = (
            _re_first(r'Port id[:\s]+(\S+)', block)
            or _re_first(r"Neighbor's port ID[:\s]+(\S+)", block)
            or _re_first(r'PortId\s*:\s*(\S+)', block)
            or ""
        )
        devices.append(DiscoveredDevice(
            hostname    = hostname.split(".")[0].strip(),
            mgmt_ip     = mgmt_ip.strip(),
            platform    = platform.strip()[:80],
            local_port  = local_port.strip(),
            remote_port = remote_port.strip(),
            source      = "lldp",
            device_type = _guess_device_type(platform),
        ))
    return devices


def _re_first(pattern: str, text: str, flags: int = 0) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


# ── Main discovery coroutine ───────────────────────────────────────────────────

async def discover_from_seed(
    seed_ip:        str,
    username:       str       = "",
    password:       str       = "",
    device_type:    str       = "cisco_ios",
    scope:          List[str] = None,
    max_depth:      int       = 5,
    timeout:        int       = 15,
    # Transport mode
    protocol:       str       = "ssh",   # "ssh" | "snmp" | "both"
    snmp_community: str       = "public",
    snmp_port:      int       = 161,
    snmp_version:   str       = "2c",
) -> AsyncIterator[DiscoveryEvent]:
    """
    Async generator that walks the network via CDP/LLDP from seed_ip.

    protocol = "ssh"  → SSH only (Netmiko; requires username + password)
    protocol = "snmp" → SNMP only (puresnmp; requires community string)
    protocol = "both" → SNMP first; SSH fallback when SNMP returns nothing

    Yields DiscoveryEvent objects:
      "connecting" — about to query a device
      "found"      — neighbor discovered and queued for recursion
      "skip"       — device excluded (AP, router, out-of-scope, already visited)
      "error"      — query failed (timeout, auth, no data)
      "done"       — walk complete; .devices = deduplicated list for inventory
    """
    if scope is None:
        scope = []

    loop        = asyncio.get_event_loop()
    visited:    Set[str]              = set()
    found:      List[DiscoveredDevice] = []

    # BFS queue: (ip, device_type_hint, depth)
    queue: List[tuple] = [(seed_ip.strip(), device_type, 0)]

    while queue:
        ip, dt, depth = queue.pop(0)

        if ip in visited:
            continue
        if not _in_scope(ip, scope):
            yield DiscoveryEvent(type="skip", ip=ip, reason="out of scope", depth=depth)
            continue
        if depth > max_depth:
            yield DiscoveryEvent(type="skip", ip=ip, reason="max depth reached", depth=depth)
            continue

        visited.add(ip)
        yield DiscoveryEvent(type="connecting", ip=ip, depth=depth)

        neighbors: List[DiscoveredDevice] = []
        error_reason: Optional[str] = None

        # ── SNMP path ──────────────────────────────────────────────
        if protocol in ("snmp", "both"):
            try:
                neighbors = await _snmp_get_neighbors(
                    ip, snmp_community, snmp_port, snmp_version
                )
            except RuntimeError as exc:
                reason = str(exc)
                if "no_data" in reason:
                    error_reason = "no CDP/LLDP data via SNMP"
                elif "not installed" in reason:
                    error_reason = "puresnmp not installed"
                else:
                    error_reason = "SNMP unreachable"
                if protocol == "snmp":
                    yield DiscoveryEvent(type="error", ip=ip,
                                         reason=error_reason, depth=depth)
                    continue
                # "both" — fall through to SSH

        # ── SSH path (primary or fallback) ────────────────────────
        if protocol in ("ssh", "both") and not neighbors:
            try:
                neighbors = await loop.run_in_executor(
                    _EXECUTOR,
                    _ssh_get_neighbors, ip, username, password, dt, timeout,
                )
            except RuntimeError as exc:
                reason = str(exc)
                if "auth_failed" in reason:
                    error_reason = "authentication failed"
                elif "ssh_timeout" in reason:
                    error_reason = "SSH timeout"
                else:
                    error_reason = "connection error"
                yield DiscoveryEvent(type="error", ip=ip,
                                     reason=error_reason, depth=depth)
                continue

        # ── Record this device and walk its neighbors ──────────────
        # Use the seed's own IP as hostname until a neighbor tells us its real name
        if not any(f.mgmt_ip == ip for f in found):
            found.append(DiscoveredDevice(hostname=ip, mgmt_ip=ip, device_type=dt))

        for n in neighbors:
            skip_reason = _is_skippable(n.platform, n.hostname)
            if skip_reason:
                yield DiscoveryEvent(
                    type="skip", ip=n.mgmt_ip, hostname=n.hostname,
                    platform=n.platform, reason=skip_reason, depth=depth + 1,
                )
                continue

            # Update seed's own record if a neighbor reveals its hostname
            if n.mgmt_ip == ip:
                for f in found:
                    if f.mgmt_ip == ip and f.hostname == ip:
                        f.hostname = n.hostname or ip
                continue

            if not any(f.mgmt_ip == n.mgmt_ip for f in found):
                found.append(n)
                yield DiscoveryEvent(
                    type        = "found",
                    ip          = n.mgmt_ip,
                    hostname    = n.hostname,
                    platform    = n.platform,
                    device_type = n.device_type,
                    depth       = depth + 1,
                )

            if n.mgmt_ip not in visited:
                queue.append((n.mgmt_ip, n.device_type, depth + 1))

    # Deduplicate (keep first occurrence of each IP)
    seen_ips: Set[str] = set()
    deduped:  List[DiscoveredDevice] = []
    for d in found:
        if d.mgmt_ip not in seen_ips:
            seen_ips.add(d.mgmt_ip)
            deduped.append(d)

    yield DiscoveryEvent(
        type    = "done",
        devices = [asdict(d) for d in deduped],
    )
