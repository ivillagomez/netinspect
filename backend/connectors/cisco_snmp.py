"""
Optional SNMP connector for Cisco switches.

Replaces SSH for the parts that are faster via SNMP:
  - MAC address table lookup (BRIDGE-MIB / Q-BRIDGE-MIB)
  - Interface status + error counters (IF-MIB)
  - System info/hostname (SNMPv2-MIB)

SSH is still used for CDP/LLDP, STP, PoE, port-channel members, and
IOS version details — things that either require CLI parsing or lack
good MIB support on Cisco IOS.

Requires: puresnmp>=2.0.0  (pure-Python, no C dependencies)
If puresnmp is not installed the module loads but HAS_SNMP is False
and all methods return None gracefully.
"""

import re
import logging
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional import — SNMP is truly optional
# ---------------------------------------------------------------------------
try:
    from puresnmp import Client
    from puresnmp.credentials import V2C, V1
    from x690.types import ObjectIdentifier as OID
    HAS_SNMP = True
except ImportError:
    HAS_SNMP = False
    logger.debug("puresnmp not installed — SNMP enhancement disabled")

# ---------------------------------------------------------------------------
# OID constants
# ---------------------------------------------------------------------------

# SNMPv2-MIB
OID_SYS_DESCR  = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME   = "1.3.6.1.2.1.1.5.0"

# IF-MIB
OID_IF_DESCR        = "1.3.6.1.2.1.2.2.1.2"    # ifDescr table
OID_IF_NAME         = "1.3.6.1.2.1.31.1.1.1.1"  # ifName table (shorter names)
OID_IF_OPER_STATUS  = "1.3.6.1.2.1.2.2.1.8"     # 1=up 2=down
OID_IF_SPEED        = "1.3.6.1.2.1.31.1.1.1.15" # ifHighSpeed (Mbps)
OID_IF_IN_ERRORS    = "1.3.6.1.2.1.2.2.1.14"    # ifInErrors
OID_IF_OUT_ERRORS   = "1.3.6.1.2.1.2.2.1.20"    # ifOutErrors
OID_IF_IN_DISCARDS  = "1.3.6.1.2.1.2.2.1.13"    # ifInDiscards
OID_IF_OUT_DISCARDS = "1.3.6.1.2.1.2.2.1.19"    # ifOutDiscards
OID_IF_DUPLEX       = "1.3.6.1.4.1.9.2.2.1.1.20" # CISCO-IF-MIB: 1=full 2=half 3=auto

# BRIDGE-MIB (RFC 1493) — per-VLAN instance on Cisco (community@vlan)
OID_DOT1D_FDB_ADDR     = "1.3.6.1.2.1.17.4.3.1.1"  # dot1dTpFdbAddress
OID_DOT1D_FDB_PORT     = "1.3.6.1.2.1.17.4.3.1.2"  # dot1dTpFdbPort
OID_DOT1D_BASE_PORT_IF = "1.3.6.1.2.1.17.1.4.1.2"  # dot1dBasePortIfIndex

# Q-BRIDGE-MIB (IEEE 802.1Q) — unified across VLANs, index = {vlan}.{mac_bytes}
OID_DOT1Q_FDB_PORT     = "1.3.6.1.2.1.17.7.1.2.2.1.2"  # dot1qTpFdbPort
OID_DOT1Q_FDB_STATUS   = "1.3.6.1.2.1.17.7.1.2.2.1.3"  # 3=learned


def _normalize_mac(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def _bytes_to_mac(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def _oid_suffix_to_mac(suffix_ints) -> str:
    """Convert last 6 integers of an OID suffix to a MAC address string."""
    return ":".join(f"{x:02x}" for x in suffix_ints[-6:])


def _shorten_interface(name: str) -> str:
    """GigabitEthernet1/0/1 → Gi1/0/1"""
    for long, short in [
        ("GigabitEthernet", "Gi"),
        ("FastEthernet",    "Fa"),
        ("TenGigabitEthernet", "Te"),
        ("TwentyFiveGigE", "Twe"),
        ("HundredGigE",    "Hu"),
        ("Port-channel",   "Po"),
    ]:
        if name.startswith(long):
            return name.replace(long, short, 1)
    return name


class CiscoSNMP:
    """
    Async SNMP client for Cisco IOS switches.

    Usage:
        snmp = CiscoSNMP(host, community, port=161, version="2c")
        mac  = await snmp.get_mac_entry("b4:70:64:1d:6b:c0")
        sys  = await snmp.get_system_info()
    """

    def __init__(self, host: str, community: str, port: int = 161, version: str = "2c"):
        self.host      = host
        self.community = community
        self.port      = port
        self.version   = version
        # Caches populated on first use
        self._ifindex_to_name: Optional[Dict[int, str]] = None
        self._name_to_ifindex: Optional[Dict[str, int]] = None
        self._bridge_port_to_ifindex: Optional[Dict[int, int]] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _creds(self):
        if not HAS_SNMP:
            raise RuntimeError("puresnmp not installed")
        return V2C(self.community) if self.version != "1" else V1(self.community)

    async def _walk_table(self, base_oid: str) -> Dict[str, object]:
        """
        Walk an OID subtree. Returns {full_oid_string: value}.
        Uses BulkWalk (SNMPv2c GETBULK) for efficiency.
        """
        results: Dict[str, object] = {}
        try:
            c = Client(self.host, self._creds(), port=self.port)
            async for oid, value in c.bulkwalk([OID(base_oid)]):
                results[str(oid)] = value
        except Exception as e:
            logger.debug("SNMP walk %s@%s failed: %s", base_oid, self.host, e)
        return results

    async def _get_oids(self, oids: list) -> Dict[str, object]:
        """Fetch multiple OIDs in a single GETMANY request."""
        results: Dict[str, object] = {}
        try:
            c = Client(self.host, self._creds(), port=self.port)
            values = await c.multiget([OID(o) for o in oids])
            for oid, value in zip(oids, values):
                results[oid] = value
        except Exception as e:
            logger.debug("SNMP multiget @%s failed: %s", self.host, e)
        return results

    def _extract_index(self, oid: str, base_oid: str) -> Optional[Tuple]:
        """
        Given full_oid and base_oid, return the instance index as a tuple of ints.
        e.g. base=1.2.3, full=1.2.3.4.5  →  (4, 5)
        """
        prefix = base_oid.rstrip(".")
        if not oid.startswith(prefix + "."):
            return None
        suffix = oid[len(prefix) + 1:]
        try:
            return tuple(int(x) for x in suffix.split("."))
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Interface index cache
    # ------------------------------------------------------------------

    async def _build_if_cache(self):
        """Build bidirectional ifIndex ↔ name mapping (from ifName, fallback ifDescr)."""
        if self._ifindex_to_name is not None:
            return  # already built

        idx_to_name: Dict[int, str] = {}

        # Try ifName first (shorter names like Gi1/0/1)
        for oid, val in (await self._walk_table(OID_IF_NAME)).items():
            idx = self._extract_index(oid, OID_IF_NAME)
            if idx:
                try:
                    name = str(val).strip("\x00").strip()
                    if name:
                        idx_to_name[idx[0]] = _shorten_interface(name)
                except Exception:
                    pass

        # Fall back to ifDescr if ifName gave nothing
        if not idx_to_name:
            for oid, val in (await self._walk_table(OID_IF_DESCR)).items():
                idx = self._extract_index(oid, OID_IF_DESCR)
                if idx:
                    try:
                        name = str(val).strip("\x00").strip()
                        if name:
                            idx_to_name[idx[0]] = _shorten_interface(name)
                    except Exception:
                        pass

        self._ifindex_to_name = idx_to_name
        self._name_to_ifindex = {v: k for k, v in idx_to_name.items()}
        logger.debug("SNMP if-cache @%s: %d interfaces", self.host, len(idx_to_name))

    async def _ifindex_for(self, name: str) -> Optional[int]:
        """Return ifIndex for a named interface (e.g. 'Gi1/0/3')."""
        await self._build_if_cache()
        short = _shorten_interface(name)
        idx = self._name_to_ifindex.get(short) or self._name_to_ifindex.get(name)
        if idx is None:
            # Partial match (e.g. "GigabitEthernet1/0/3" vs "Gi1/0/3")
            for k, v in self._name_to_ifindex.items():
                if k.endswith(name) or name.endswith(k):
                    return v
        return idx

    async def _build_bridge_port_cache(self):
        """Build bridge_port → ifIndex from dot1dBasePortIfIndex."""
        if self._bridge_port_to_ifindex is not None:
            return
        bp_map: Dict[int, int] = {}
        for oid, val in (await self._walk_table(OID_DOT1D_BASE_PORT_IF)).items():
            idx = self._extract_index(oid, OID_DOT1D_BASE_PORT_IF)
            if idx:
                try:
                    bp_map[idx[0]] = int(val)
                except Exception:
                    pass
        self._bridge_port_to_ifindex = bp_map

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def test(self) -> bool:
        """Return True if SNMP is reachable on this host."""
        if not HAS_SNMP:
            return False
        try:
            c = Client(self.host, self._creds(), port=self.port)
            await c.get(OID(OID_SYS_NAME))
            return True
        except Exception:
            return False

    async def get_system_info(self) -> Dict:
        """
        Return {hostname, sys_descr, model, ios_version} from SNMPv2-MIB.
        Model and IOS version are parsed from sysDescr.
        """
        if not HAS_SNMP:
            return {}
        data = await self._get_oids([OID_SYS_NAME, OID_SYS_DESCR])
        if not data:
            return {}

        hostname  = str(data.get(OID_SYS_NAME, "")).strip("\x00").strip()
        sys_descr = str(data.get(OID_SYS_DESCR, "")).strip("\x00").strip()

        # Parse IOS version from sysDescr
        # e.g. "Cisco IOS Software, Version 15.2(7)E5, ..."
        ios_version = ""
        m = re.search(r"Version\s+(\S+)", sys_descr, re.IGNORECASE)
        if m:
            ios_version = m.group(1).rstrip(",")

        # Parse model
        model = ""
        m = re.search(r"cisco\s+([\w-]+\s*\d+[\w/-]*)", sys_descr, re.IGNORECASE)
        if m:
            model = m.group(1).strip()

        return {
            "hostname":    hostname,
            "sys_descr":   sys_descr,
            "ios_version": ios_version,
            "model":       model,
        }

    async def get_mac_entry(self, mac: str) -> Optional[Dict]:
        """
        Look up a MAC address in the switch MAC table via Q-BRIDGE-MIB.

        Returns dict with {port, vlan, mac} where port is the short
        interface name (e.g. 'Gi1/0/3'), or None if not found.

        Strategy:
          1. Walk dot1qTpFdbPort (Q-BRIDGE-MIB) — index = {vlan}.{6 mac bytes}
          2. Map bridge port → ifIndex via dot1dBasePortIfIndex
          3. Map ifIndex → interface name via ifName/ifDescr
        """
        if not HAS_SNMP:
            return None
        target = _normalize_mac(mac)

        try:
            await self._build_if_cache()
            await self._build_bridge_port_cache()

            found_port: Optional[int] = None
            found_vlan: Optional[int] = None

            c = Client(self.host, self._creds(), port=self.port)
            async for oid, value in c.bulkwalk([OID(OID_DOT1Q_FDB_PORT)]):
                    idx = self._extract_index(str(oid), OID_DOT1Q_FDB_PORT)
                    if not idx or len(idx) < 7:
                        continue
                    # Index structure: {vlan_id}.{mac_byte*6}
                    vlan = idx[0]
                    mac_str = _oid_suffix_to_mac(idx[1:7])
                    if _normalize_mac(mac_str) == target:
                        found_vlan = vlan
                        found_port = int(value)
                        break

            if found_port is None:
                logger.debug("SNMP MAC %s not found in Q-BRIDGE table @%s", mac, self.host)
                return None

            # Map bridge port → ifIndex → interface name
            if_idx = self._bridge_port_to_ifindex.get(found_port)
            if if_idx is None:
                logger.debug("SNMP bridge port %d has no ifIndex mapping @%s", found_port, self.host)
                return None

            if_name = self._ifindex_to_name.get(if_idx, f"port{if_idx}")
            logger.info("SNMP MAC %s found: vlan=%s port=%s (%s) @%s",
                        mac, found_vlan, found_port, if_name, self.host)
            return {"port": if_name, "vlan": str(found_vlan), "mac": mac}

        except Exception as e:
            logger.warning("SNMP get_mac_entry(%s) @%s failed: %s", mac, self.host, e)
            return None

    async def get_interface_stats(self, ifname: str) -> Optional[Dict]:
        """
        Return IF-MIB stats for the named interface.
        Returns dict with {oper_status, speed_mbps, in_errors, out_errors,
        in_discards, out_discards} or None if not found.
        """
        if not HAS_SNMP:
            return None
        try:
            await self._build_if_cache()
            if_idx = await self._ifindex_for(ifname)
            if if_idx is None:
                logger.debug("SNMP ifindex not found for %s @%s", ifname, self.host)
                return None

            oids = [
                f"{OID_IF_OPER_STATUS}.{if_idx}",
                f"{OID_IF_SPEED}.{if_idx}",
                f"{OID_IF_IN_ERRORS}.{if_idx}",
                f"{OID_IF_OUT_ERRORS}.{if_idx}",
                f"{OID_IF_IN_DISCARDS}.{if_idx}",
                f"{OID_IF_OUT_DISCARDS}.{if_idx}",
            ]
            data = await self._get_oids(oids)
            if not data:
                return None

            def _int(key):
                try:
                    return int(data.get(key, 0) or 0)
                except Exception:
                    return 0

            oper = _int(f"{OID_IF_OPER_STATUS}.{if_idx}")
            return {
                "oper_status":  "up" if oper == 1 else "down",
                "speed_mbps":   _int(f"{OID_IF_SPEED}.{if_idx}"),
                "in_errors":    _int(f"{OID_IF_IN_ERRORS}.{if_idx}"),
                "out_errors":   _int(f"{OID_IF_OUT_ERRORS}.{if_idx}"),
                "in_discards":  _int(f"{OID_IF_IN_DISCARDS}.{if_idx}"),
                "out_discards": _int(f"{OID_IF_OUT_DISCARDS}.{if_idx}"),
                "source":       "snmp",
            }
        except Exception as e:
            logger.warning("SNMP get_interface_stats(%s) @%s failed: %s", ifname, self.host, e)
            return None
