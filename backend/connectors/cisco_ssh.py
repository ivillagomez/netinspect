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
        """Connect once, run all relevant commands, disconnect. Returns raw dict."""
        if options is None:
            options = DiagnosticOptions()
        cisco_mac = mac_to_cisco(mac)
        result = {"switch": self.name, "host": self.host, "reachable": False}

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

            except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
                result["error"] = str(e)
                logger.warning(f"[{self.name}] Connection failed: {e}")
            except Exception as e:
                result["error"] = str(e)
                logger.warning(f"[{self.name}] Error: {e}")
            finally:
                self._disconnect()
            return result

        return await self._run(_work)

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
            out = self._cmd(f"show mac address-table interface {port}")
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
            out = self._cmd(f"show interfaces {port} status")
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
            out = self._cmd(f"show interfaces {port}")
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
        """show interfaces <port> trunk — if port appears, it's trunking."""
        try:
            out = self._cmd(f"show interfaces {port} trunk")
            return bool(re.search(r"trunking", out, re.IGNORECASE)) and "not trunking" not in out.lower()
        except Exception:
            return False

    def _get_cdp_neighbor(self, port: str) -> Optional[CDPNeighbor]:
        """show cdp neighbors <port> detail"""
        try:
            out = self._cmd(f"show cdp neighbors {port} detail")
            return self._parse_single_cdp_entry(port, out)
        except Exception as e:
            logger.debug(f"[{self.name}] cdp_neighbor error: {e}")
        return None

    def _get_lldp_neighbor(self, port: str) -> Optional[LLDPNeighbor]:
        """show lldp neighbors <port> detail"""
        try:
            out = self._cmd(f"show lldp neighbors {port} detail")
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
            out = self._cmd(f"show spanning-tree interface {port}")
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
            out = self._cmd(f"show power inline {port}")
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
            port_m = re.search(r"Port id:\s*(.+)", block)
            remote_port = shorten_interface(port_m.group(1).strip()) if port_m else ""
            ip_m = re.search(r"(?:Management Addresses|IP):\s*\n?\s*(?:IP:\s*)?(\d+\.\d+\.\d+\.\d+)", block)
            remote_ip = ip_m.group(1) if ip_m else None
            desc_m = re.search(r"System Description:\s*\n\s*(.+)", block)
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
