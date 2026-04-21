import asyncio
import logging
import time
from collections import deque
from typing import Optional, List, Dict, Tuple

from backend.config import AppConfig
from backend.connectors.fortigate import FortiGateClient, normalize_mac
from backend.connectors.cisco_ssh import CiscoSwitch
from backend.connectors.ruckus_r1 import RuckusR1Client
from backend.models import Hop, DeviceType, Issue, IssueSeverity, TraceResult
from backend.tracer import resolver as _resolver
from backend.tracer.diagnostics import run_all_checks

logger = logging.getLogger(__name__)


class NetworkTracer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.fg = FortiGateClient(config.fortigate)
        self.cisco_switches = [CiscoSwitch(sw) for sw in config.cisco_switches]
        self.r1 = RuckusR1Client(config.ruckus_r1)

    async def trace(self, query: str) -> TraceResult:
        start = time.time()
        result = TraceResult(query=query)

        # --- Step 1: Resolve input to MAC/IP ---
        try:
            resolution = await _resolver.resolve(query, self.fg)
        except Exception as e:
            logger.error(f"Resolution failed: {e}")
            result.status = "error"
            result.error = f"Resolution failed: {e}"
            result.trace_time_ms = int((time.time() - start) * 1000)
            return result

        result.resolved_mac = resolution.mac
        result.resolved_ip = resolution.ip
        result.resolved_fg_name = resolution.fg_name

        if not resolution.mac:
            result.status = "not_found"
            result.error = (
                f"Could not resolve '{query}' to a MAC address. "
                "Ensure the device is active and present in the FortiGate ARP table."
            )
            result.trace_time_ms = int((time.time() - start) * 1000)
            return result

        mac = resolution.mac
        norm_mac = normalize_mac(mac)

        # --- Step 2: Build FortiGate hop ---
        fg_hop = await self._build_fg_hop(mac, resolution.ip)
        result.path.append(fg_hop)

        # --- Step 3: Query all Cisco switches in parallel ---
        cisco_tasks = [sw.gather_all(norm_mac) for sw in self.cisco_switches]
        cisco_results = await asyncio.gather(*cisco_tasks, return_exceptions=True)

        # Build topology from CDP/LLDP neighbor tables
        topology = self._build_topology(cisco_results)

        # Find which switch has the MAC on an access port
        edge_info = self._find_edge(cisco_results)

        # --- Step 4: Check Ruckus R1 (wireless client or R1-managed switch) ---
        r1_client_info = None
        r1_switch_info = None
        try:
            r1_client_info, r1_switch_info = await asyncio.gather(
                self.r1.find_client_by_mac(norm_mac),
                self.r1.find_switch_port_for_mac(norm_mac),
            )
        except Exception as e:
            logger.warning(f"R1 lookup failed: {e}")

        # --- Step 5: Build ordered path ---
        if edge_info:
            # Device is wired — trace path through switches
            switch_hops = self._build_switch_path(edge_info, cisco_results, topology)
            result.path.extend(switch_hops)

            # Check if edge switch's client port connects to a Ruckus AP
            ap_hop = await self._check_ap_on_edge(edge_info, cisco_results)
            if ap_hop:
                result.path.append(ap_hop)
                # Wireless client connected through this AP
                end_hop = self._build_wireless_end_hop(r1_client_info, mac, resolution.ip, len(result.path))
                if end_hop:
                    result.path.append(end_hop)
            else:
                # Directly wired end device
                result.path.append(self._build_wired_end_hop(mac, resolution.ip, len(result.path)))

        elif r1_client_info:
            # Wireless client found via R1
            ap_id = r1_client_info.get("apId") or r1_client_info.get("connectedApId")
            if ap_id:
                ap_hop = await self._build_r1_ap_hop(str(ap_id), len(result.path))
                if ap_hop:
                    result.path.append(ap_hop)
            result.path.append(self._build_wireless_end_hop(r1_client_info, mac, resolution.ip, len(result.path)))

        elif r1_switch_info:
            # Device on an R1-managed switch
            sw_hop = self._build_r1_switch_hop(r1_switch_info, len(result.path))
            result.path.append(sw_hop)
            result.path.append(self._build_wired_end_hop(mac, resolution.ip, len(result.path)))

        else:
            # MAC not found on any switch
            result.status = "partial"
            result.path.append(Hop(
                order=len(result.path),
                device_type=DeviceType.UNKNOWN,
                device_name="Device not located",
                device_ip=resolution.ip,
                issues=[Issue(
                    severity=IssueSeverity.WARNING,
                    category="discovery",
                    message="Device MAC not found on any switch",
                    detail="Device may be offline, or connected to an unmanaged switch",
                )],
            ))

        # --- Step 6: Run diagnostics ---
        all_issues = run_all_checks(result.path)
        result.all_issues = all_issues

        if not result.status or result.status == "success":
            has_critical = any(i.severity == IssueSeverity.CRITICAL for i in all_issues)
            result.status = "issues" if has_critical else "success"

        result.trace_time_ms = int((time.time() - start) * 1000)
        return result

    # ------------------------------------------------------------------
    # Hop builders
    # ------------------------------------------------------------------

    async def _build_fg_hop(self, mac: str, ip: Optional[str]) -> Hop:
        try:
            hostname = await self.fg.get_hostname()
            arp_entry = await self.fg.get_arp_entry(mac=mac)
            fg_interface = arp_entry.get("interface", "") if arp_entry else ""
        except Exception:
            hostname = "FortiGate"
            fg_interface = ""

        return Hop(
            order=0,
            device_type=DeviceType.FIREWALL,
            device_name=hostname,
            device_ip=self.config.fortigate.host,
            egress_port=fg_interface or None,
            raw_data={"arp_interface": fg_interface},
        )

    def _build_switch_path(
        self,
        edge_info: Dict,
        cisco_results: List,
        topology: Dict[str, List],
    ) -> List[Hop]:
        """Build ordered list of switch hops from edge to core."""
        edge_switch_name = edge_info["switch"]
        path_names = self._trace_path_to_fg(edge_switch_name, topology)

        hops = []
        # path_names goes from edge → core (reverse order for display FG→edge)
        # We reverse so FortiGate is order 0, then core switches, then edge
        for i, sw_name in enumerate(reversed(path_names)):
            raw = self._get_result_for_switch(sw_name, cisco_results)
            if not raw:
                continue
            is_edge = sw_name == edge_switch_name
            hop = self._build_cisco_hop(
                raw=raw,
                order=i + 1,
                is_edge=is_edge,
                edge_info=edge_info if is_edge else None,
            )
            hops.append(hop)

        if not hops and edge_info:
            # Fallback: just add edge switch
            raw = self._get_result_for_switch(edge_switch_name, cisco_results)
            if raw:
                hops.append(self._build_cisco_hop(raw=raw, order=1, is_edge=True, edge_info=edge_info))

        return hops

    def _build_cisco_hop(self, raw: Dict, order: int, is_edge: bool, edge_info: Optional[Dict]) -> Hop:
        from backend.connectors.cisco_ssh import shorten_interface
        hostname = raw.get("hostname") or raw.get("switch", "Unknown Switch")
        host_ip = raw.get("host", "")

        if is_edge and edge_info:
            mac_entry = edge_info.get("mac_entry")
            ingress_port = mac_entry.port if mac_entry else None
            vlan = mac_entry.vlan if mac_entry else None
        else:
            ingress_port = None
            vlan = None

        # egress port = CDP/LLDP neighbor toward next hop (toward FG)
        egress_port = None
        cdp_n = raw.get("cdp_neighbor") if is_edge else None
        lldp_n = raw.get("lldp_neighbor") if is_edge else None

        return Hop(
            order=order,
            device_type=DeviceType.CISCO_SWITCH,
            device_name=hostname,
            device_ip=host_ip,
            ingress_port=ingress_port,
            egress_port=egress_port,
            vlan=vlan,
            interface_status=raw.get("int_status"),
            interface_details=raw.get("int_details"),
            cdp_neighbor=cdp_n,
            lldp_neighbor=lldp_n,
            stp_info=raw.get("stp_info"),
            poe_status=raw.get("poe_status"),
            reachable=raw.get("reachable", False),
            raw_data={
                "version": raw.get("version", {}),
                "is_trunk": raw.get("is_trunk", False),
                "error": raw.get("error"),
            },
        )

    def _build_wired_end_hop(self, mac: str, ip: Optional[str], order: int) -> Hop:
        return Hop(
            order=order,
            device_type=DeviceType.WIRED_CLIENT,
            device_name=ip or mac,
            device_ip=ip,
            raw_data={"mac": mac},
        )

    def _build_wireless_end_hop(self, r1_client: Optional[Dict], mac: str, ip: Optional[str], order: int) -> Hop:
        name = ip or mac
        ssid = ""
        rssi = None
        if r1_client:
            name = r1_client.get("hostname") or r1_client.get("clientName") or name
            ssid = r1_client.get("ssid") or r1_client.get("wlanName") or ""
            rssi = r1_client.get("rssi") or r1_client.get("signal")
        issues = []
        if rssi and int(rssi) < -75:
            issues.append(Issue(
                severity=IssueSeverity.WARNING,
                category="wireless",
                message=f"Weak RSSI: {rssi} dBm",
                detail="Poor signal quality — client may experience packet loss",
            ))
        return Hop(
            order=order,
            device_type=DeviceType.WIRELESS_CLIENT,
            device_name=name,
            device_ip=ip,
            issues=issues,
            raw_data={"mac": mac, "ssid": ssid, "rssi": rssi, "r1_data": r1_client or {}},
        )

    async def _build_r1_ap_hop(self, ap_id: str, order: int) -> Optional[Hop]:
        try:
            ap = await self.r1.get_ap_by_id(ap_id)
            if not ap:
                return None
            name = ap.get("name") or ap.get("apName") or f"AP-{ap_id}"
            ip = ap.get("ip") or ap.get("ipAddress")
            mac = ap.get("mac") or ap.get("macAddress", "")
            return Hop(
                order=order,
                device_type=DeviceType.RUCKUS_AP,
                device_name=name,
                device_ip=ip,
                raw_data={"ap_id": ap_id, "mac": mac, "r1_data": ap},
            )
        except Exception as e:
            logger.warning(f"R1 AP hop build failed: {e}")
        return None

    def _build_r1_switch_hop(self, r1_switch_info: Dict, order: int) -> Hop:
        sw = r1_switch_info.get("switch", {})
        port = r1_switch_info.get("port", {})
        name = sw.get("name") or sw.get("switchName") or "Ruckus Switch"
        ip = sw.get("ip") or sw.get("ipAddress")
        port_name = port.get("portName") or port.get("name") or port.get("id", "")
        return Hop(
            order=order,
            device_type=DeviceType.RUCKUS_SWITCH,
            device_name=name,
            device_ip=ip,
            ingress_port=str(port_name),
            raw_data={"r1_data": r1_switch_info},
        )

    async def _check_ap_on_edge(self, edge_info: Dict, cisco_results: List) -> Optional[Hop]:
        """If the edge switch port's CDP/LLDP neighbor is a Ruckus AP, build AP hop."""
        cdp = edge_info.get("cdp_neighbor")
        lldp = edge_info.get("lldp_neighbor")

        for neighbor in [cdp, lldp]:
            if not neighbor:
                continue
            if any(kw in (neighbor.remote_device + " " + getattr(neighbor, "platform", "")).lower()
                   for kw in ("ruckus", "ap", "r510", "r550", "r650", "t750")):
                ap_mac = normalize_mac(neighbor.remote_device) if _looks_like_mac(neighbor.remote_device) else None
                if ap_mac:
                    ap = await self.r1.get_ap_by_mac(ap_mac)
                    if ap:
                        ap_id = ap.get("id") or ap.get("apId")
                        return await self._build_r1_ap_hop(str(ap_id), len([]) + 10)
                # Try by IP
                if neighbor.remote_ip:
                    for ap in await self.r1.get_all_aps():
                        if ap.get("ip") == neighbor.remote_ip or ap.get("ipAddress") == neighbor.remote_ip:
                            ap_id = ap.get("id") or ap.get("apId")
                            return await self._build_r1_ap_hop(str(ap_id), 10)
        return None

    # ------------------------------------------------------------------
    # Topology helpers
    # ------------------------------------------------------------------

    def _build_topology(self, cisco_results: List) -> Dict[str, List]:
        """Build {switch_name: [CDPNeighbor|LLDPNeighbor, ...]} neighbor map."""
        topology: Dict[str, List] = {}
        for raw in cisco_results:
            if isinstance(raw, Exception) or not isinstance(raw, dict):
                continue
            sw_name = raw.get("hostname") or raw.get("switch", "")
            neighbors = []
            for n in raw.get("all_cdp", []):
                neighbors.append(n)
            for n in raw.get("all_lldp", []):
                # Don't double-add if CDP already has it
                already = any(
                    getattr(existing, "remote_device", "") == n.remote_device
                    for existing in neighbors
                )
                if not already:
                    neighbors.append(n)
            topology[sw_name] = neighbors
        return topology

    def _trace_path_to_fg(self, edge_switch: str, topology: Dict[str, List]) -> List[str]:
        """BFS from edge switch, following neighbors, return ordered list edge→core."""
        fg_ip = self.config.fortigate.host
        known_ips = {sw.host for sw in self.cisco_switches}

        visited = set()
        path: List[str] = []
        queue = deque([(edge_switch, [edge_switch])])

        while queue:
            current, current_path = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            for neighbor in topology.get(current, []):
                neighbor_ip = getattr(neighbor, "remote_ip", None)
                neighbor_name = getattr(neighbor, "remote_device", "")

                # Check if neighbor is the FortiGate
                if neighbor_ip == fg_ip or "fortigate" in neighbor_name.lower() or "forti" in neighbor_name.lower():
                    return current_path

                # Check if neighbor is another known switch
                if neighbor_ip in known_ips or neighbor_name in topology:
                    next_name = neighbor_name if neighbor_name in topology else neighbor_ip
                    if next_name and next_name not in visited:
                        queue.append((next_name, current_path + [next_name]))

        return path if path else [edge_switch]

    def _find_edge(self, cisco_results: List) -> Optional[Dict]:
        """Find the switch+result where MAC is on an ACCESS port."""
        for raw in cisco_results:
            if isinstance(raw, Exception) or not isinstance(raw, dict):
                continue
            if not raw.get("reachable") or not raw.get("mac_entry"):
                continue
            if not raw.get("is_trunk", True):
                return raw
        # Fallback: any switch that found the MAC
        for raw in cisco_results:
            if isinstance(raw, Exception) or not isinstance(raw, dict):
                continue
            if raw.get("mac_entry"):
                return raw
        return None

    def _get_result_for_switch(self, sw_name_or_ip: str, cisco_results: List) -> Optional[Dict]:
        for raw in cisco_results:
            if isinstance(raw, Exception) or not isinstance(raw, dict):
                continue
            if raw.get("hostname") == sw_name_or_ip or raw.get("switch") == sw_name_or_ip or raw.get("host") == sw_name_or_ip:
                return raw
        return None


def _looks_like_mac(s: str) -> bool:
    return bool(re.match(r"^([0-9a-f]{2}[:\-.]){5}[0-9a-f]{2}$", s, re.IGNORECASE))
