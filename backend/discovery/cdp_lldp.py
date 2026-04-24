"""CDP / LLDP auto-discovery engine.

Walk a network starting from a seed IP, SSH into each reachable switch,
parse CDP / LLDP neighbor tables, and recurse into newly found devices.

Progress is yielded as DiscoveryEvent objects so callers can stream them
to the frontend via SSE.
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


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class DiscoveredDevice:
    hostname:    str
    mgmt_ip:     str
    platform:    str = ""
    local_port:  str = ""   # our port facing the neighbor
    remote_port: str = ""   # their port facing us
    source:      str = "cdp"   # "cdp" | "lldp"
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


# ── Scope helpers ──────────────────────────────────────────────────────────────

def _in_scope(ip: str, scopes: List[str]) -> bool:
    """True if ip falls inside any of the provided CIDR scopes.
    Empty scope list means allow-all."""
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
        return "cisco_ios"   # Ruckus ICX uses Brocade/IOS-like CLI
    if any(k in p for k in ("extreme", "exos")):
        return "cisco_ios"   # reasonable fallback for Extreme
    # Default: Cisco IOS
    return "cisco_ios"


def _is_skippable(platform: str, hostname: str) -> Optional[str]:
    """Return a skip reason if this device should not be recursed into."""
    p = platform.lower()
    h = hostname.lower()
    if any(k in p for k in ("air-", "ap-", "aironet", "wave 2", "catalyst 9120", "catalyst 9130")):
        return "access point"
    if any(k in h for k in ("-ap-", "_ap_", "-ap.", "ap01", "ap02")):
        return "access point"
    if any(k in p for k in ("asa", "firepower", "fortigate", "paloalto", "pa-")):
        return "firewall/security appliance"
    if any(k in p for k in ("router", "cisco 18", "cisco 19", "cisco 28", "cisco 29",
                             "cisco 38", "cisco 39", "isr", "asr")):
        return "router"
    return None


# ── CDP / LLDP parsers ─────────────────────────────────────────────────────────

def _parse_cdp_neighbors(output: str) -> List[DiscoveredDevice]:
    """Parse 'show cdp neighbors detail' output into DiscoveredDevice list."""
    devices = []
    # Split on the dashed separator lines
    blocks = re.split(r'-{5,}', output)
    for block in blocks:
        if not block.strip():
            continue
        hostname  = _re_first(r'Device ID:\s*(\S+)', block)
        if not hostname:
            continue
        # Management IP: prefer "IP address:" line
        mgmt_ip   = _re_first(r'IP address:\s*(\d+\.\d+\.\d+\.\d+)', block)
        if not mgmt_ip:
            mgmt_ip = _re_first(r'IPv4 [Aa]ddress:\s*(\d+\.\d+\.\d+\.\d+)', block)
        if not mgmt_ip:
            continue  # can't SSH without an IP

        platform    = _re_first(r'Platform:\s*([^,\n]+)', block) or ""
        local_port  = _re_first(r'Interface:\s*([^,\n]+)', block) or ""
        remote_port = _re_first(r'Port ID \(outgoing port\):\s*(\S+)', block) or ""

        # Strip domain suffix from hostname
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
    """Parse 'show lldp neighbors detail' output.
    Handles Cisco IOS, Aruba AOS-S, and Ruckus ICX variants."""
    devices = []
    # Split on separator lines (dashes) — works for Cisco and Ruckus
    blocks = re.split(r'-{5,}', output)
    # For Aruba AOS-S, blocks are separated by blank lines + "Local Port"
    if len(blocks) <= 1:
        blocks = re.split(r'(?=Local [Pp]ort\s*:)', output)

    for block in blocks:
        if not block.strip():
            continue

        # ── Hostname ──────────────────────────────────────────────
        hostname = (
            _re_first(r'System Name[:\s]+(\S+)', block)
            or _re_first(r"Neighbor's system name[:\s]+(\S+)", block)
            or _re_first(r'SysName\s*:\s*(\S+)', block)
        )
        if not hostname:
            continue

        # ── Management IP ─────────────────────────────────────────
        mgmt_ip = (
            _re_first(r'Management Addresses?.*?IP(?:v4)?:\s*(\d+\.\d+\.\d+\.\d+)', block, re.S)
            or _re_first(r'Mgmt Address\s*:\s*(\d+\.\d+\.\d+\.\d+)', block)
            or _re_first(r"Management address \(IPv4\):\s*(\d+\.\d+\.\d+\.\d+)", block)
            or _re_first(r'IP(?:v4)? address:\s*(\d+\.\d+\.\d+\.\d+)', block)
        )
        if not mgmt_ip:
            continue

        # ── Platform ──────────────────────────────────────────────
        platform = (
            _re_first(r'System Description[:\s]*\n\s*(.+)', block)
            or _re_first(r"Neighbor's system description[:\s]+(.+)", block)
            or _re_first(r'System Descr\s*:\s*(.+)', block)
            or ""
        )

        # ── Ports ─────────────────────────────────────────────────
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

        hostname = hostname.split(".")[0].strip()
        devices.append(DiscoveredDevice(
            hostname    = hostname,
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


# ── SSH worker (runs in thread pool) ──────────────────────────────────────────

def _ssh_get_neighbors(ip: str, username: str, password: str,
                       device_type: str, timeout: int) -> List[DiscoveredDevice]:
    """SSH into a switch, run CDP then LLDP, return combined neighbor list.
    Must be called from a thread (Netmiko is synchronous)."""
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

        # ── Try LLDP (fallback or supplement) ─────────────────────
        if not neighbors:
            try:
                # Aruba AOS-S uses a different command
                if device_type.startswith("aruba"):
                    lldp_out = conn.send_command("show lldp info remote-device detail",
                                                 read_timeout=20)
                else:
                    lldp_out = conn.send_command("show lldp neighbors detail", read_timeout=20)
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


# ── Main discovery coroutine ───────────────────────────────────────────────────

async def discover_from_seed(
    seed_ip:     str,
    username:    str,
    password:    str,
    device_type: str        = "cisco_ios",
    scope:       List[str]  = None,
    max_depth:   int        = 5,
    timeout:     int        = 15,
) -> AsyncIterator[DiscoveryEvent]:
    """
    Async generator that walks the network via CDP/LLDP from seed_ip.

    Yields DiscoveryEvent objects:
      - "connecting" — about to SSH into an IP
      - "found"      — device discovered and will be recursed
      - "skip"       — in-scope IP skipped (AP, router, already visited, etc.)
      - "error"      — SSH failed (timeout, auth, etc.)
      - "done"       — walk complete; .devices = deduplicated found list

    All discovered devices (successful SSH only) are included in the final
    "done" event so the frontend can offer an "add to inventory" checklist.
    """
    if scope is None:
        scope = []

    loop       = asyncio.get_event_loop()
    visited: Set[str] = set()
    found:   List[DiscoveredDevice] = []

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

        try:
            neighbors = await loop.run_in_executor(
                _EXECUTOR,
                _ssh_get_neighbors, ip, username, password, dt, timeout,
            )
        except RuntimeError as exc:
            reason = str(exc)
            if "auth_failed" in reason:
                reason = "authentication failed"
            elif "ssh_timeout" in reason:
                reason = "SSH timeout"
            else:
                reason = "connection error"
            yield DiscoveryEvent(type="error", ip=ip, reason=reason, depth=depth)
            continue

        # The device we just connected to is itself a valid device
        # (we already have its IP; use the first neighbor's remote info to get hostname if possible)
        # Add to found list with what we know
        self_hostname = ip   # best we have until we see ourselves as a neighbor
        found.append(DiscoveredDevice(hostname=self_hostname, mgmt_ip=ip, device_type=dt))

        # Yield all discovered neighbors
        for n in neighbors:
            skip_reason = _is_skippable(n.platform, n.hostname)
            if skip_reason:
                yield DiscoveryEvent(
                    type="skip", ip=n.mgmt_ip, hostname=n.hostname,
                    platform=n.platform, reason=skip_reason, depth=depth + 1,
                )
                continue

            # Deduplicate by mgmt_ip in the "found" list
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

    # Deduplicate found list (keep first occurrence of each IP)
    seen_ips: Set[str] = set()
    deduped: List[DiscoveredDevice] = []
    for d in found:
        if d.mgmt_ip not in seen_ips:
            seen_ips.add(d.mgmt_ip)
            deduped.append(d)

    yield DiscoveryEvent(
        type    = "done",
        devices = [asdict(d) for d in deduped],
    )
