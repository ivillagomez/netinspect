"""
Aruba switch SSH connector — covers both ArubaOS-S (2930/2930F/2930M)
and ArubaOS-CX (6000/6100).  The os_type field on the config selects
which netmiko device_type and which CLI commands to use.
"""
import re
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException

from backend.config import ArubaSwitchConfig
from backend.models import MACEntry, InterfaceStatus, InterfaceDetails, LLDPNeighbor, DiagnosticOptions

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=5)

# Whitelist for port/interface names interpolated into CLI commands
_SAFE_PORT_RE = re.compile(r'^[\w\-./]+$')


def _safe_port(port: str) -> str:
    if not _SAFE_PORT_RE.match(port):
        raise ValueError(f"Unsafe port name rejected: {port!r}")
    return port


def normalize_mac(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def _cisco_mac(norm: str) -> str:
    """xxxx.xxxx.xxxx — used by ArubaOS-S"""
    return f"{norm[0:4]}.{norm[4:8]}.{norm[8:12]}"


def _colon_mac(norm: str) -> str:
    """xx:xx:xx:xx:xx:xx — used by ArubaOS-CX"""
    return ":".join(norm[i:i+2] for i in range(0, 12, 2))


def shorten_interface(name: str) -> str:
    """1/1/1 stays as-is; GigabitEthernet0/0/1 → GE0/0/1 for CX."""
    replacements = [
        ("GigabitEthernet", "GE"),
        ("TenGigabitEthernet", "10GE"),
        ("FortyGigabitEthernet", "40GE"),
        ("HundredGigabitEthernet", "100GE"),
        ("management", "mgmt"),
    ]
    for long, short in replacements:
        if name.lower().startswith(long.lower()):
            return short + name[len(long):]
    return name


# ── Log parsing helpers ───────────────────────────────────────────────────────

_LOG_SEV_MAP = {
    "0": "CRIT", "1": "CRIT", "2": "CRIT",
    "3": "ERR",
    "4": "WARN",
}

def _parse_aruba_os_logs(output: str) -> List[Dict[str, str]]:
    """Parse ArubaOS-S show logging output.

    Example line:
      I 04/23/26 10:12:44 00436 ports: port 1 is now on-line
      W 04/23/26 10:11:00 00075 poe: ...
      E 04/23/26 10:10:00 00075 system: ...
    """
    entries: List[Dict[str, str]] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # First char is severity: E=Error, W=Warning, I=Info, D=Debug
        sev_char = line[0].upper() if line else ""
        if sev_char not in ("E", "W"):
            continue
        sev = "ERR" if sev_char == "E" else "WARN"
        # Strip the leading severity char and whitespace
        msg = line[1:].strip()
        entries.append({"severity": sev, "message": msg})
    return entries[:50]


def _parse_aruba_cx_logs(output: str) -> List[Dict[str, str]]:
    """Parse ArubaOS-CX show log output.

    Example line:
      2026-04-23T10:12:44.123456+00:00 switch CRIT ops-sysd[1]: kernel: Oops
      2026-04-23T10:10:00.000000+00:00 switch ERR  ops-pmd[2]: port down
      2026-04-23T10:09:00.000000+00:00 switch WARN ops-lacpd[3]: LACP timeout
    """
    entries: List[Dict[str, str]] = []
    sev_re = re.compile(
        r"\b(CRIT(?:ICAL)?|ERR(?:OR)?|WARN(?:ING)?)\b",
        re.IGNORECASE,
    )
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        m = sev_re.search(line)
        if not m:
            continue
        raw_sev = m.group(1).upper()
        if raw_sev.startswith("CRIT"):
            sev = "CRIT"
        elif raw_sev.startswith("ERR"):
            sev = "ERR"
        else:
            sev = "WARN"
        entries.append({"severity": sev, "message": line})
    return entries[:50]


class ArubaSwitch:
    def __init__(self, config: ArubaSwitchConfig):
        self.config = config
        self.name = config.name
        self.host = config.host
        self.os_type = config.os_type          # "aruba_os" | "aruba_osix"
        self._is_cx = config.os_type == "aruba_osix"
        self._conn = None

    # ── Connection (pool-backed) ──────────────────────────────────────────────

    def _connect(self):
        from backend.connectors.ssh_pool import _pool
        self._conn = _pool.acquire(self.config)

    def _disconnect(self):
        if self._conn:
            try:
                from backend.connectors.ssh_pool import _pool
                _pool.release(self.config, self._conn)
            except Exception:
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

    # ── Public async API ──────────────────────────────────────────────────────

    async def gather_all(self, norm_mac: str, options: Optional[DiagnosticOptions] = None) -> Dict:
        """Connect, run commands, return raw dict.

        When rest_enabled (AOS-CX only), the Aruba CX REST API runs in parallel
        with SSH.  REST wins on: mac_entry, hostname, LLDP neighbors, interface
        status/details, ARP table.  SSH always runs for system logs.
        """
        if options is None:
            options = DiagnosticOptions()
        result: Dict[str, Any] = {
            "vendor": "aruba",
            "switch": self.name,
            "host": self.host,
            "os_type": self.os_type,
            "reachable": False,
        }

        # ------------------------------------------------------------------
        # Optional ArubaOS-CX REST client (CX only, when rest_enabled)
        # ------------------------------------------------------------------
        rest = None
        if getattr(self.config, "rest_enabled", False) and self._is_cx:
            try:
                from backend.connectors.aruba_cx_rest import ArubaCxRest, HAS_AIOHTTP
                if HAS_AIOHTTP:
                    rest = ArubaCxRest(self.config)
                    logger.debug("[%s] ArubaOS-CX REST hybrid path enabled", self.name)
            except Exception as e:
                logger.debug("[%s] ArubaOS-CX REST init failed: %s", self.name, type(e).__name__)

        def _work():
            try:
                self._connect()
                result["reachable"] = True
                result["hostname"] = self._get_hostname()
                result["mac_entry"] = self._find_mac(norm_mac)
                result["all_lldp"] = self._get_all_lldp()

                if result["mac_entry"]:
                    port = result["mac_entry"].port
                    result["is_trunk"] = self._is_trunk_port(port)
                    if options.interface_status or options.error_counters or options.mtu_check:
                        result["int_status"]  = self._get_interface_status(port)
                        result["int_details"] = self._get_interface_details(port)

                # Always capture logs when connected
                result["system_logs"] = self._get_system_logs()

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

        # Run SSH (always) — REST merge happens after if configured
        ssh_result = await self._run(_work)
        result = ssh_result if isinstance(ssh_result, dict) else result

        # ------------------------------------------------------------------
        # ArubaOS-CX REST hybrid merge
        # ------------------------------------------------------------------
        if rest is not None:
            try:
                logged_in = await rest.login()
                if logged_in:
                    rc_mac, rc_host, rc_lldp, rc_arp = await asyncio.gather(
                        rest.get_mac_entry(norm_mac),
                        rest.get_hostname(),
                        rest.get_lldp_neighbors(),
                        rest.get_arp_table(),
                        return_exceptions=True,
                    )

                    def _rc(val):
                        return None if isinstance(val, Exception) else val

                    if _rc(rc_mac) or _rc(rc_host):
                        result["reachable"]    = True
                        result["rest_source"]  = True

                    if _rc(rc_host):
                        result["hostname"] = rc_host
                    if _rc(rc_mac) and not result.get("mac_entry"):
                        result["mac_entry"] = rc_mac
                        logger.info("[%s] MAC entry from REST API: port=%s vlan=%s",
                                    self.name, rc_mac.port, rc_mac.vlan)
                    if _rc(rc_lldp):
                        result["all_lldp"] = rc_lldp
                    if _rc(rc_arp):
                        result["arp_table"] = rc_arp

                    # Per-port interface details from REST
                    mac_entry = result.get("mac_entry")
                    if mac_entry and mac_entry.port:
                        port = mac_entry.port
                        if options.interface_status or options.error_counters or options.mtu_check:
                            rc_istatus, rc_idetails = await asyncio.gather(
                                rest.get_interface_status(port),
                                rest.get_interface_details(port),
                                return_exceptions=True,
                            )
                            if not isinstance(rc_istatus, Exception) and rc_istatus:
                                result["int_status"] = rc_istatus
                            if not isinstance(rc_idetails, Exception) and rc_idetails:
                                result["int_details"] = rc_idetails

                    await rest.logout()
            except Exception as e:
                logger.debug("[%s] ArubaOS-CX REST merge error: %s", self.name, type(e).__name__)

        return result

    # ── CLI commands (sync, runs in executor) ─────────────────────────────────

    def _get_hostname(self) -> str:
        try:
            if self._is_cx:
                out = self._cmd("show system | include Hostname")
                m = re.search(r"Hostname\s*:\s*(\S+)", out)
                return m.group(1) if m else self.name
            else:
                out = self._cmd("show system")
                m = re.search(r"System Name\s*:\s*(\S+)", out, re.IGNORECASE)
                return m.group(1) if m else self.name
        except Exception:
            return self.name

    def _find_mac(self, norm_mac: str) -> Optional[MACEntry]:
        """Look up a MAC in the forwarding table."""
        try:
            if self._is_cx:
                # ArubaOS-CX: show mac-address-table address <xx:xx:xx:xx:xx:xx>
                mac_q = _colon_mac(norm_mac)
                out = self._cmd(f"show mac-address-table address {mac_q}")
                # Output format: VLAN  MAC                Port     Type
                #                10    aa:bb:cc:dd:ee:ff  1/1/5    dynamic
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and normalize_mac(parts[1]) == norm_mac:
                        return MACEntry(
                            mac=parts[1],
                            vlan=int(parts[0]) if parts[0].isdigit() else 0,
                            port=shorten_interface(parts[2]),
                            entry_type=parts[3],
                        )
            else:
                # ArubaOS-S: show mac-address <xxxx.xxxx.xxxx>
                mac_q = _cisco_mac(norm_mac)
                out = self._cmd(f"show mac-address {mac_q}")
                # Output: MAC Address    Located on Port    VLAN  ...
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and normalize_mac(parts[0]) == norm_mac:
                        # format: <mac>  <port>  <vlan>  ...
                        port = parts[1] if len(parts) > 1 else ""
                        vlan = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                        return MACEntry(mac=parts[0], vlan=vlan, port=port, entry_type="dynamic")
        except Exception as e:
            logger.debug("[%s] find_mac error: %s", self.name, e)
        return None

    def _get_all_lldp(self) -> List[LLDPNeighbor]:
        """Retrieve all LLDP neighbors."""
        try:
            if self._is_cx:
                return self._parse_cx_lldp(self._cmd("show lldp neighbor-info detail"))
            else:
                return self._parse_os_lldp(self._cmd("show lldp info remote-device detail"))
        except Exception as e:
            logger.debug("[%s] lldp error: %s", self.name, e)
        return []

    def _is_trunk_port(self, port: str) -> bool:
        try:
            safe = _safe_port(port)
            if self._is_cx:
                out = self._cmd(f"show interface {safe}")
                return bool(re.search(r"Mode\s*:\s*Trunk", out, re.IGNORECASE))
            else:
                out = self._cmd(f"show interfaces {safe} trunk")
                return "802.1Q VLAN" in out
        except Exception:
            return False

    def _get_interface_status(self, port: str) -> Optional[InterfaceStatus]:
        try:
            safe = _safe_port(port)
            if self._is_cx:
                out = self._cmd(f"show interface {safe}")
                status = "connected" if re.search(r"Link Status\s*:\s*Up", out, re.IGNORECASE) else "notconnect"
                speed_m = re.search(r"Speed\s*:\s*(\S+)", out, re.IGNORECASE)
                return InterfaceStatus(
                    name=port,
                    status=status,
                    speed=speed_m.group(1) if speed_m else "",
                )
            else:
                out = self._cmd(f"show interfaces {safe}")
                status = "connected" if re.search(r"Status\s*:\s*Up", out, re.IGNORECASE) else "notconnect"
                speed_m = re.search(r"Speed\s*:\s*(\S+)", out, re.IGNORECASE)
                vlan_m = re.search(r"VLAN ID\s*:\s*(\d+)", out, re.IGNORECASE)
                return InterfaceStatus(
                    name=port,
                    status=status,
                    speed=speed_m.group(1) if speed_m else "",
                    vlan=vlan_m.group(1) if vlan_m else "",
                )
        except Exception as e:
            logger.debug("[%s] int_status error: %s", self.name, e)
        return None

    def _get_interface_details(self, port: str) -> Optional[InterfaceDetails]:
        try:
            safe = _safe_port(port)
            cmd = f"show interface {safe}" if self._is_cx else f"show interfaces {safe}"
            out = self._cmd(cmd)

            def _int(pattern, default=0):
                m = re.search(pattern, out, re.IGNORECASE)
                return int(m.group(1)) if m else default

            return InterfaceDetails(
                name=port,
                is_up=bool(re.search(r"Link Status\s*:\s*Up|Status\s*:\s*Up", out, re.IGNORECASE)),
                mtu=_int(r"MTU\s*:\s*(\d+)"),
                input_errors=_int(r"Input Errors\s*:\s*(\d+)|In Errors\s*:\s*(\d+)"),
                output_errors=_int(r"Output Errors\s*:\s*(\d+)|Out Errors\s*:\s*(\d+)"),
                crc_errors=_int(r"CRC\s*:\s*(\d+)"),
            )
        except Exception as e:
            logger.debug("[%s] int_details error: %s", self.name, e)
        return None

    def _get_system_logs(self) -> List[Dict[str, str]]:
        """Capture WARN/ERR/CRIT log entries from the switch."""
        try:
            if self._is_cx:
                out = self._cmd("show log")
                return _parse_aruba_cx_logs(out)
            else:
                out = self._cmd("show logging -s")
                return _parse_aruba_os_logs(out)
        except Exception as e:
            logger.debug("[%s] system_logs error: %s", self.name, e)
        return []

    # ── LLDP parsers ──────────────────────────────────────────────────────────

    def _parse_cx_lldp(self, output: str) -> List[LLDPNeighbor]:
        """Parse ArubaOS-CX 'show lldp neighbor-info detail' output."""
        neighbors: List[LLDPNeighbor] = []
        # Split on dashes separator between entries
        blocks = re.split(r"-{10,}", output)
        for block in blocks:
            local_m  = re.search(r"Local Port\s*:\s*(\S+)", block, re.IGNORECASE)
            remote_m = re.search(r"Chassis-Name\s*:\s*(.+)", block, re.IGNORECASE)
            port_m   = re.search(r"Port-ID\s*:\s*(.+)", block, re.IGNORECASE)
            ip_m     = re.search(r"Management-Addresses\s*:\s*(\d+\.\d+\.\d+\.\d+)", block, re.IGNORECASE)
            desc_m   = re.search(r"System-Description\s*:\s*(.+)", block, re.IGNORECASE)
            if not local_m or not remote_m:
                continue
            neighbors.append(LLDPNeighbor(
                local_port=shorten_interface(local_m.group(1).strip()),
                remote_device=remote_m.group(1).strip(),
                remote_port=shorten_interface(port_m.group(1).strip()) if port_m else "",
                remote_ip=ip_m.group(1).strip() if ip_m else None,
                system_description=desc_m.group(1).strip()[:120] if desc_m else "",
            ))
        return neighbors

    def _parse_os_lldp(self, output: str) -> List[LLDPNeighbor]:
        """Parse ArubaOS-S 'show lldp info remote-device detail' output."""
        neighbors: List[LLDPNeighbor] = []
        blocks = re.split(r"-{10,}", output)
        for block in blocks:
            port_m   = re.search(r"Local Port\s*:\s*(\S+)", block, re.IGNORECASE)
            system_m = re.search(r"System Name\s*:\s*(.+)", block, re.IGNORECASE)
            pid_m    = re.search(r"Port ID\s*:\s*(.+)", block, re.IGNORECASE)
            ip_m     = re.search(r"Management Address\s*:\s*(\d+\.\d+\.\d+\.\d+)", block, re.IGNORECASE)
            desc_m   = re.search(r"System Description\s*:\s*(.+)", block, re.IGNORECASE)
            if not port_m or not system_m:
                continue
            neighbors.append(LLDPNeighbor(
                local_port=port_m.group(1).strip(),
                remote_device=system_m.group(1).strip(),
                remote_port=pid_m.group(1).strip() if pid_m else "",
                remote_ip=ip_m.group(1).strip() if ip_m else None,
                system_description=desc_m.group(1).strip()[:120] if desc_m else "",
            ))
        return neighbors
