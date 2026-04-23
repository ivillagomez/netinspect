import re
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Tuple, TYPE_CHECKING

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

from backend.config import CiscoSwitchConfig
from backend.models import (
    MACEntry, InterfaceStatus, InterfaceDetails,
    CDPNeighbor, LLDPNeighbor, STPPortInfo, PoEStatus, DiagnosticOptions,
)

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=10)

# Whitelist for interface / port names used in CLI commands.
# Prevents command injection if a compromised switch returns a crafted MAC table entry.
_SAFE_PORT_RE = re.compile(r'^[\w\-./]+$')


def _safe_port(port: str) -> str:
    """Validate a port/interface name before interpolating into a CLI command.

    Raises ValueError if the name contains characters outside the safe set so the
    caller can catch it and skip the command rather than injecting arbitrary text.
    """
    if not _SAFE_PORT_RE.match(port):
        raise ValueError(f"Unsafe port name rejected: {port!r}")
    return port


def normalize_mac(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def mac_to_cisco(mac: str) -> str:
    m = normalize_mac(mac)
    return f"{m[0:4]}.{m[4:8]}.{m[8:12]}"


def shorten_interface(name: str) -> str:
    """Convert GigabitEthernet1/0/1 → Gi1/0/1 etc."""
    replacements = [
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("TenGigabitEthernet", "Te"),
        ("TwentyFiveGigE", "Twe"),
        ("HundredGigE", "Hu"),
        ("Port-channel", "Po"),
    ]
    for long, short in replacements:
        if name.startswith(long):
            return name.replace(long, short, 1)
    return name


class CiscoSwitch:
    def __init__(self, config: CiscoSwitchConfig):
        self.config = config
        self.name = config.name
        self.host = config.host
        self._conn = None
        self._hostname: Optional[str] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self):
        self._conn = ConnectHandler(
            device_type=self.config.device_type,
            host=self.config.host,
            username=self.config.username,
            password=self.config.password,
            timeout=self.config.timeout,
            session_timeout=self.config.timeout,
            global_delay_factor=1,
        )

    def _disconnect(self):
        if self._conn:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            self._conn = None

    def _cmd(self, command: str) -> str:
        if not self._conn:
            raise RuntimeError("Not connected")
        return self._conn.send_command(command, read_timeout=self.config.timeout)

    async def _run(self, fn, *args):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, fn, *args)

    # ------------------------------------------------------------------
    # High-level async API
    # ------------------------------------------------------------------

    async def gather_all(self, mac: str, options: Optional[DiagnosticOptions] = None) -> Dict:
        """Connect once, run all relevant commands, disconnect. Returns raw dict.

        If snmp_community is set in config, SNMP runs concurrently with SSH and
        provides MAC entry, system info, and interface stats via IF-MIB/Q-BRIDGE-MIB.
        SSH always runs for CDP/LLDP, STP, PoE, port-channel, and IOS version.
        """
        if options is None:
            options = DiagnosticOptions()
        cisco_mac = mac_to_cisco(mac)
        result = {"switch": self.name, "host": self.host, "reachable": False}

        # ------------------------------------------------------------------
        # Optional SNMP client — instantiated only if configured + available
        # ------------------------------------------------------------------
        snmp = None
        if self.config.snmp_community:
            try:
                from backend.connectors.cisco_snmp import CiscoSNMP, HAS_SNMP
                if HAS_SNMP:
                    snmp = CiscoSNMP(
                        self.host,
                        self.config.snmp_community,
                        port=self.config.snmp_port,
                        version=self.config.snmp_version,
                    )
                    logger.debug("[%s] SNMP fast path enabled (community configured)", self.name)
            except Exception as e:
                logger.debug("[%s] SNMP client init failed: %s", self.name, e)

        # ------------------------------------------------------------------
        # SSH work (sync, runs in thread executor) — unchanged
        # ------------------------------------------------------------------
        def _work():
            try:
                self._connect()
                result["reachable"] = True
                result["hostname"] = self._get_hostname()
                result["mac_entry"] = self._find_mac(cisco_mac)
                result["version"] = self._get_version_summary()
                # Always collect CDP/LLDP for topology (needed even if neighbor_info disabled)
                result["all_cdp"] = self._get_all_cdp_neighbors()
                result["all_lldp"] = self._get_all_lldp_neighbors()
                # ARP table useful on L3 switches to correlate IPs
                result["arp_table"] = self._get_arp_table()

                if result["mac_entry"]:
                    port = result["mac_entry"].port
                    # Full MAC table for this port — shows all MACs (helps find upstream switches)
                    result["port_mac_table"] = self._get_mac_table_for_port(port)
                    result["is_trunk"] = self._is_trunk_port(port)

                    # Port-channel: also collect member link status
                    if port.upper().startswith("PO") or port.lower().startswith("port-channel"):
                        result["etherchannel_members"] = self._get_etherchannel_members(port)

                    if options.interface_status or options.error_counters or options.mtu_check:
                        result["int_status"] = self._get_interface_status(port)
                        result["int_details"] = self._get_interface_details(port)

                    if options.neighbor_info:
                        result["cdp_neighbor"] = self._get_cdp_neighbor(port)
                        result["lldp_neighbor"] = self._get_lldp_neighbor(port)

                    if options.stp:
                        result["stp_info"] = self._get_stp_info(port)

                    if options.poe:
                        result["poe_status"] = self._get_poe_status(port)

                result["system_mtu"]  = self._get_system_mtu()
                result["system_logs"] = self._get_system_logs()

                # Uplink port error counters — checks health of links toward upstream devices
                # (Ruckus switch errors are visible here on the Cisco side of that link)
                result["uplink_details"] = self._get_uplink_details(
                    result.get("all_cdp", []) + result.get("all_lldp", []),
                    result.get("mac_entry"),
                    options,
                )

            except NetmikoTimeoutException:
                result["error"] = "Connection timed out"
                logger.warning("[%s] SSH connection timed out", self.name)
            except NetmikoAuthenticationException:
                result["error"] = "Authentication failed"
                logger.warning("[%s] SSH authentication failed", self.name)
            except Exception as e:
                result["error"] = "Unexpected error during trace"
                logger.warning("[%s] Error: %s", self.name, type(e).__name__, exc_info=True)
            finally:
                self._disconnect()
            return result

        # ------------------------------------------------------------------
        # Execute: SSH + SNMP concurrently when SNMP is available
        # ------------------------------------------------------------------
        if snmp is not None:
            ssh_result, snmp_mac, snmp_sys = await asyncio.gather(
                self._run(_work),
                snmp.get_mac_entry(mac),
                snmp.get_system_info(),
                return_exceptions=True,
            )

            # _work() catches its own exceptions and always returns the dict;
            # guard anyway in case something bubbled out of run_in_executor.
            if isinstance(ssh_result, dict):
                result = ssh_result

            result["snmp_source"] = False

            # Merge SNMP system info
            if snmp_sys and not isinstance(snmp_sys, Exception):
                result["snmp_system"] = snmp_sys
                logger.debug("[%s] SNMP sysName=%s model=%s ios=%s",
                             self.name,
                             snmp_sys.get("hostname"),
                             snmp_sys.get("model"),
                             snmp_sys.get("ios_version"))
            elif isinstance(snmp_sys, Exception):
                logger.debug("[%s] SNMP system info failed: %s", self.name, snmp_sys)

            # Merge SNMP MAC entry — fill in if SSH missed it, always store raw
            if snmp_mac and not isinstance(snmp_mac, Exception):
                result["snmp_mac"] = snmp_mac
                result["snmp_source"] = True
                if not result.get("mac_entry"):
                    result["mac_entry"] = MACEntry(
                        mac=snmp_mac["mac"],
                        vlan=int(snmp_mac.get("vlan", 0)),
                        port=snmp_mac["port"],
                        entry_type="dynamic",
                    )
                    logger.info("[%s] MAC entry from SNMP (SSH missed): port=%s vlan=%s",
                                self.name, snmp_mac["port"], snmp_mac.get("vlan"))
                else:
                    logger.debug("[%s] SNMP confirmed MAC on port=%s vlan=%s",
                                 self.name, snmp_mac["port"], snmp_mac.get("vlan"))

                # SNMP interface stats for the port — richer than CLI counters
                if options.interface_status or options.error_counters or options.mtu_check:
                    try:
                        snmp_stats = await snmp.get_interface_stats(snmp_mac["port"])
                        if snmp_stats:
                            result["snmp_int_stats"] = snmp_stats
                            logger.debug("[%s] SNMP if-stats port=%s: %s",
                                         self.name, snmp_mac["port"], snmp_stats)
                    except Exception as e:
                        logger.debug("[%s] SNMP interface stats failed: %s", self.name, e)

            elif isinstance(snmp_mac, Exception):
                logger.debug("[%s] SNMP MAC lookup failed: %s", self.name, snmp_mac)

        else:
            # No SNMP configured — pure SSH path (original behaviour)
            result = await self._run(_work)

        return result

    async def get_all_neighbors(self) -> Dict:
        """Collect CDP+LLDP neighbor tables, ARP table, and MAC summary (for topology building)."""
        result = {"switch": self.name, "host": self.host, "reachable": False}

        def _work():
            try:
                self._connect()
                result["reachable"] = True
                result["hostname"] = self._get_hostname()
                result["all_cdp"] = self._get_all_cdp_neighbors()
                result["all_lldp"] = self._get_all_lldp_neighbors()
                result["arp_table"] = self._get_arp_table()
                result["version"] = self._get_version_summary()
            except Exception as e:
                result["error"] = str(e)
                logger.warning(f"[{self.name}] Neighbor collection failed: {e}")
            finally:
                self._disconnect()
            return result

        return await self._run(_work)

    # ------------------------------------------------------------------
    # Private sync helpers (called inside executor)
    # ------------------------------------------------------------------

    def _get_hostname(self) -> str:
        try:
            out = self._cmd("show version")
            m = re.search(r"^(\S+)\s+uptime", out, re.MULTILINE)
            if m:
                return m.group(1)
        except Exception:
            pass
        return self.config.name

    def _get_version_summary(self) -> Dict:
        try:
            out = self._cmd("show version")
            ios_version = ""
            model = ""
            serial = ""

            m = re.search(r"Cisco IOS.*?Version\s+(\S+)", out, re.IGNORECASE)
            if m:
                ios_version = m.group(1).rstrip(",")

            # Try to extract exact model number (e.g. WS-C2960X-48FPS-L, C9200-24P, etc.)
            # Cisco 2960-X style
            m = re.search(r"cisco\s+(WS-C[\w-]+)", out, re.IGNORECASE)
            if m:
                model = m.group(1)
            if not model:
                # Catalyst 9000 style: cisco C9200-24P or cisco Catalyst 9200-24P
                m = re.search(r"cisco\s+(?:Catalyst\s+)?(C?\d{4}[\w-]+)", out, re.IGNORECASE)
                if m:
                    model = m.group(1)
            if not model:
                # Generic fallback
                m = re.search(r"(?:cisco|Model)\s+([\w-]+)", out, re.IGNORECASE)
                if m:
                    model = m.group(1)

            # Serial number
            m = re.search(r"Processor board ID\s+(\S+)", out, re.IGNORECASE)
            if m:
                serial = m.group(1)

            return {"ios_version": ios_version, "model": model, "serial": serial}
        except Exception:
            return {}

    def _find_mac(self, cisco_mac: str) -> Optional[MACEntry]:
        """show mac address-table address <mac>"""
        try:
            out = self._cmd(f"show mac address-table address {cisco_mac}")
            pattern = re.compile(
                r"^\s*(\d+)\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(\w+)\s+(\S+)",
                re.MULTILINE | re.IGNORECASE,
            )
            for m in pattern.finditer(out):
                vlan, mac_found, entry_type, port = m.groups()
                if normalize_mac(mac_found) == normalize_mac(cisco_mac):
                    return MACEntry(
                        mac=mac_found,
                        vlan=int(vlan),
                        port=shorten_interface(port),
                        entry_type=entry_type,
                    )
        except Exception as e:
            logger.debug(f"[{self.name}] find_mac error: {e}")
        return None

    def _get_mac_table_for_port(self, port: str) -> List[MACEntry]:
        """show mac address-table interface <port> — all MACs seen on this port."""
        entries = []
        try:
            out = self._cmd(f"show mac address-table interface {_safe_port(port)}")
            pattern = re.compile(
                r"^\s*(\d+)\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+(\w+)\s+(\S+)",
                re.MULTILINE | re.IGNORECASE,
            )
            for m in pattern.finditer(out):
                vlan, mac_found, entry_type, iface = m.groups()
                entries.append(MACEntry(
                    mac=mac_found,
                    vlan=int(vlan),
                    port=shorten_interface(iface),
                    entry_type=entry_type,
                ))
        except Exception as e:
            logger.debug(f"[{self.name}] mac_table_for_port error: {e}")
        return entries

    def _get_arp_table(self) -> List[Dict]:
        """show ip arp — returns list of {ip, mac, interface} for L3 switches."""
        entries = []
        try:
            out = self._cmd("show ip arp")
            # Format: Protocol  Address  Age  Hardware Addr  Type  Interface
            pattern = re.compile(
                r"^Internet\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+ARPA\s+(\S+)",
                re.MULTILINE | re.IGNORECASE,
            )
            for m in pattern.finditer(out):
                ip, mac, iface = m.groups()
                entries.append({"ip": ip, "mac": mac, "interface": shorten_interface(iface)})
        except Exception as e:
            logger.debug(f"[{self.name}] arp_table error: {e}")
        return entries

    def _get_interface_status(self, port: str) -> Optional[InterfaceStatus]:
        """show interfaces <port> status"""
        try:
            out = self._cmd(f"show interfaces {_safe_port(port)} status")
            pattern = re.compile(
                r"^(\S+)\s+(\S*)\s+(connected|notconnect|err-disabled|disabled|inactive)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)?$",
                re.MULTILINE | re.IGNORECASE,
            )
            for m in pattern.finditer(out):
                iface, desc, status, vlan, duplex, speed, port_type = m.groups()
                return InterfaceStatus(
                    name=shorten_interface(iface),
                    status=status.lower(),
                    vlan=vlan,
                    duplex=duplex,
                    speed=speed,
                    port_type=(port_type or "").strip(),
                )
        except Exception as e:
            logger.debug(f"[{self.name}] int_status error: {e}")
        return None

    def _get_interface_details(self, port: str) -> Optional[InterfaceDetails]:
        """show interfaces <port>"""
        try:
            out = self._cmd(f"show interfaces {_safe_port(port)}")
            is_up = bool(re.search(r"is up, line protocol is up", out, re.IGNORECASE))
            err_disabled = bool(re.search(r"err-disabled", out, re.IGNORECASE))

            def _int(pattern, default=0):
                m = re.search(pattern, out, re.IGNORECASE)
                return int(m.group(1)) if m else default

            mtu = _int(r"MTU (\d+) bytes")
            bw = _int(r"BW (\d+) Kbit")

            duplex = ""
            m = re.search(r"(\w+-[Dd]uplex|half.duplex|full.duplex)", out)
            if m:
                duplex = m.group(1).lower().replace("-duplex", "").replace(" duplex", "")

            speed = ""
            m = re.search(r"(\d+(?:\.\d+)?[GMK]?b(?:it)?(?:/s)?),?\s+(?:\w+\s+)?(?:auto-speed|speed)", out, re.IGNORECASE)
            if not m:
                m = re.search(r"BW (\d+) Kbit", out)
                if m:
                    kbps = int(m.group(1))
                    speed = f"{kbps // 1000}M" if kbps < 1_000_000 else f"{kbps // 1_000_000}G"
            else:
                speed = m.group(1)

            description = ""
            m = re.search(r"Description:\s*(.+)", out)
            if m:
                description = m.group(1).strip()

            return InterfaceDetails(
                name=shorten_interface(port),
                description=description,
                mtu=mtu,
                duplex=duplex,
                speed=speed,
                bandwidth_kbps=bw,
                input_errors=_int(r"(\d+) input errors"),
                output_errors=_int(r"(\d+) output errors"),
                crc_errors=_int(r"(\d+) CRC"),
                runts=_int(r"(\d+) runts"),
                giants=_int(r"(\d+) giants"),
                input_rate_bps=_int(r"(\d+) bits/sec,\s+\d+ packets/sec\s+input"),
                output_rate_bps=_int(r"(\d+) bits/sec,\s+\d+ packets/sec\s+output"),
                is_up=is_up,
                err_disabled=err_disabled,
            )
        except Exception as e:
            logger.debug(f"[{self.name}] int_details error: {e}")
        return None

    def _is_trunk_port(self, port: str) -> bool:
        """show interfaces <port> trunk — Cisco outputs 'not-trunking' for access ports."""
        try:
            out = self._cmd(f"show interfaces {_safe_port(port)} trunk")
            # 'not-trunking' (hyphen) appears for access ports; match either form
            if re.search(r"not.trunking", out, re.IGNORECASE):
                return False
            return bool(re.search(r"\btrunking\b", out, re.IGNORECASE))
        except Exception:
            return False

    def _get_cdp_neighbor(self, port: str) -> Optional[CDPNeighbor]:
        """show cdp neighbors <port> detail"""
        try:
            out = self._cmd(f"show cdp neighbors {_safe_port(port)} detail")
            return self._parse_single_cdp_entry(port, out)
        except Exception as e:
            logger.debug(f"[{self.name}] cdp_neighbor error: {e}")
        return None

    def _get_lldp_neighbor(self, port: str) -> Optional[LLDPNeighbor]:
        """show lldp neighbors <port> detail"""
        try:
            out = self._cmd(f"show lldp neighbors {_safe_port(port)} detail")
            return self._parse_single_lldp_entry(port, out)
        except Exception as e:
            logger.debug(f"[{self.name}] lldp_neighbor error: {e}")
        return None

    def _get_all_cdp_neighbors(self) -> List[CDPNeighbor]:
        try:
            out = self._cmd("show cdp neighbors detail")
            return self._parse_all_cdp(out)
        except Exception as e:
            logger.debug(f"[{self.name}] all_cdp error: {e}")
        return []

    def _get_all_lldp_neighbors(self) -> List[LLDPNeighbor]:
        try:
            out = self._cmd("show lldp neighbors detail")
            return self._parse_all_lldp(out)
        except Exception as e:
            logger.debug(f"[{self.name}] all_lldp error: {e}")
        return []

    def _get_stp_info(self, port: str) -> List[STPPortInfo]:
        try:
            out = self._cmd(f"show spanning-tree interface {_safe_port(port)}")
            results = []
            pattern = re.compile(
                r"(VLAN\d+|MST\d+)\s+(Root|Desg|Altn|Back|Mstr)\s+(FWD|BLK|LIS|LRN|DIS)\s+(\d+)",
                re.IGNORECASE,
            )
            for m in pattern.finditer(out):
                vlan_str, role, state, cost = m.groups()
                vlan_num = int(re.sub(r"\D", "", vlan_str))
                results.append(STPPortInfo(vlan=vlan_num, role=role.lower(), state=state.lower(), cost=int(cost)))
            return results
        except Exception as e:
            logger.debug(f"[{self.name}] stp error: {e}")
        return []

    def _get_poe_status(self, port: str) -> Optional[PoEStatus]:
        try:
            out = self._cmd(f"show power inline {_safe_port(port)}")
            if "Invalid" in out or "not found" in out.lower() or "% Error" in out:
                return None
            pattern = re.compile(
                r"(\S+)\s+(auto|off|static|never)\s+(on|off|Delivering|Power-deny|fault|deny)\s+([\d.]+)\s+(.*?)\s+(\d+|-)\s+([\d.]+|-)",
                re.IGNORECASE,
            )
            m = pattern.search(out)
            if m:
                _, admin, oper, power, device, poe_class, max_w = m.groups()
                return PoEStatus(
                    admin=admin,
                    operational=oper,
                    power_watts=float(power),
                    device=device.strip(),
                    poe_class=str(poe_class).strip(),
                    max_watts=float(max_w) if max_w != "-" else 0.0,
                )
        except Exception as e:
            logger.debug(f"[{self.name}] poe error: {e}")
        return None

    def _get_system_mtu(self) -> Dict:
        """show system mtu — global MTU setting (Catalyst switches)."""
        try:
            out = self._cmd("show system mtu")
            result = {}
            m = re.search(r"System MTU size is (\d+)", out)
            if m:
                result["system_mtu"] = int(m.group(1))
            m = re.search(r"System Jumbo MTU size is (\d+)", out)
            if m:
                result["jumbo_mtu"] = int(m.group(1))
            m = re.search(r"Routing MTU size is (\d+)", out)
            if m:
                result["routing_mtu"] = int(m.group(1))
            return result
        except Exception:
            return {}

    def _get_system_logs(self) -> List[Dict]:
        """Capture WARN/ERR/CRIT log entries via 'show logging'.

        Cisco syslog severity is the digit in the mnemonic: %FAC-SEV-MNEMONIC
        0-2 → CRIT, 3 → ERR, 4 → WARN. Returns up to 50 entries.
        """
        entries = []
        try:
            out = self._cmd(
                "show logging | include %-[0-4]-"
            )
            sev_re = re.compile(r"%[\w]+-(\d+)-[\w]+", re.IGNORECASE)
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                m = sev_re.search(line)
                if not m:
                    continue
                level = int(m.group(1))
                if level > 4:
                    continue
                sev = "CRIT" if level <= 2 else ("ERR" if level == 3 else "WARN")
                entries.append({"severity": sev, "message": line})
                if len(entries) >= 50:
                    break
        except Exception as e:
            logger.debug("[%s] system_logs error: %s", self.name, e)
        return entries

    def _get_etherchannel_members(self, port: str) -> List[Dict]:
        """show etherchannel <group> summary — member ports and bundle state for a Po interface."""
        members = []
        try:
            m = re.search(r"\d+", port)
            if not m:
                return members
            group = m.group(0)
            out = self._cmd(f"show etherchannel {group} summary")
            # Matches: Gi1/0/1(P)  Gi1/0/2(D)  etc.
            pattern = re.compile(r"((?:Gi|Te|Fa|Twe|Hu)[\d/]+)\((\w)\)", re.IGNORECASE)
            flag_map = {
                "P": "bundled", "D": "down", "s": "suspended",
                "I": "stand-alone", "H": "hot-standby", "w": "waiting",
            }
            for match in pattern.finditer(out):
                iface, flag = match.groups()
                members.append({
                    "port": shorten_interface(iface),
                    "status": flag_map.get(flag, flag),
                })
        except Exception as e:
            logger.debug(f"[{self.name}] etherchannel error: {e}")
        return members

    def _get_uplink_details(self, all_neighbors: list, mac_entry, options) -> Dict:
        """
        Collect interface details on all uplink ports (every CDP/LLDP neighbor port that
        is NOT the access port where the end device was found).  This lets us report error
        counters on the Cisco ↔ Ruckus link even though we can't SSH into the Ruckus.
        Only runs when error_counters or interface_status option is enabled.
        """
        if not (options.error_counters or options.interface_status):
            return {}
        access_port = mac_entry.port if mac_entry else None
        seen = set()
        result = {}
        for n in all_neighbors:
            lp = getattr(n, "local_port", None)
            if not lp or lp == access_port or lp in seen:
                continue
            seen.add(lp)
            details = self._get_interface_details(lp)
            if details:
                result[lp] = details
        return result

    # ------------------------------------------------------------------
    # CDP / LLDP parsing helpers
    # ------------------------------------------------------------------

    def _parse_all_cdp(self, output: str) -> List[CDPNeighbor]:
        entries = re.split(r"-{10,}", output)
        results = []
        for block in entries:
            device_m = re.search(r"Device ID:\s*(.+)", block)
            if not device_m:
                continue
            remote_device = device_m.group(1).strip()
            ip_m = re.search(r"IP(?:v4)? address:\s*(\S+)", block)
            remote_ip = ip_m.group(1) if ip_m else None
            platform_m = re.search(r"Platform:\s*(.+?),", block)
            platform = platform_m.group(1).strip() if platform_m else ""
            intf_m = re.search(r"Interface:\s*(\S+),\s*Port ID.*?:\s*(\S+)", block)
            if not intf_m:
                continue
            local_port = shorten_interface(intf_m.group(1).rstrip(","))
            remote_port = shorten_interface(intf_m.group(2).rstrip(","))
            cap_m = re.search(r"Capabilities:\s*(.+)", block)
            caps = [c.strip() for c in cap_m.group(1).split(",")] if cap_m else []
            results.append(CDPNeighbor(
                local_port=local_port,
                remote_device=remote_device,
                remote_port=remote_port,
                remote_ip=remote_ip,
                platform=platform,
                capabilities=caps,
            ))
        return results

    def _parse_single_cdp_entry(self, local_port: str, output: str) -> Optional[CDPNeighbor]:
        entries = self._parse_all_cdp(output)
        if entries:
            e = entries[0]
            e.local_port = shorten_interface(local_port)
            return e
        return None

    # Matches LLDP Port IDs that are MAC addresses (Ruckus ICX reports these
    # with Port ID Subtype 3).  When matched we fall back to Port Description.
    _MAC_PORT_RE = re.compile(
        r'^([0-9a-f]{4}\.){2}[0-9a-f]{4}$'         # Cisco dot-notation  xxxx.xxxx.xxxx
        r'|^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$',    # colon/dash          xx:xx:xx:xx:xx:xx
        re.IGNORECASE,
    )

    def _parse_all_lldp(self, output: str) -> List[LLDPNeighbor]:
        entries = re.split(r"-{10,}", output)
        results = []
        for block in entries:
            local_m = re.search(r"Local Intf:\s*(\S+)", block)
            if not local_m:
                continue
            local_port = shorten_interface(local_m.group(1))
            name_m = re.search(r"System Name:\s*(.+)", block)
            remote_device = name_m.group(1).strip() if name_m else ""

            # Port id is sometimes a MAC address on Ruckus ICX (LLDP Subtype 3).
            # Port Description carries the real port name in that case.
            port_m = re.search(r"Port id:\s*(.+)", block)
            raw_port_id = port_m.group(1).strip() if port_m else ""
            port_desc_m = re.search(r"Port description:\s*(.+)", block, re.IGNORECASE)
            port_desc = port_desc_m.group(1).strip() if port_desc_m else ""

            if self._MAC_PORT_RE.match(raw_port_id) and port_desc:
                # Port id is a MAC address — use Port Description instead
                remote_port = shorten_interface(port_desc)
                logger.debug("LLDP port-id is MAC (%s) — using Port Description: %s",
                             raw_port_id, remote_port)
            elif raw_port_id:
                remote_port = shorten_interface(raw_port_id)
            else:
                remote_port = shorten_interface(port_desc)

            ip_m = re.search(r"(?:Management Addresses|IP):\s*\n?\s*(?:IP:\s*)?(\d+\.\d+\.\d+\.\d+)", block)
            remote_ip = ip_m.group(1) if ip_m else None
            # Match description on same line ("System Description: Ruckus R670 ...")
            # or next line ("System Description:\n  Ruckus R670 ...")
            desc_m = re.search(r"System Description:[ \t]*\n?[ \t]*(\S[^\n]*)", block)
            sys_desc = desc_m.group(1).strip() if desc_m else ""
            if not remote_device and not remote_port:
                continue
            results.append(LLDPNeighbor(
                local_port=local_port,
                remote_device=remote_device,
                remote_port=remote_port,
                remote_ip=remote_ip,
                system_description=sys_desc,
            ))
        return results

    def _parse_single_lldp_entry(self, local_port: str, output: str) -> Optional[LLDPNeighbor]:
        entries = self._parse_all_lldp(output)
        if entries:
            e = entries[0]
            e.local_port = shorten_interface(local_port)
            return e
        return None
