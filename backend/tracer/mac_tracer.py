import asyncio
import logging
import re
import time
from typing import Optional, List, Dict, Any

from backend.config import AppConfig
from backend.connectors.fortigate import FortiGateClient, normalize_mac
from backend.connectors.fortigate_ssh import FortiGateSSH
from backend.connectors.cisco_ssh import CiscoSwitch
from backend.connectors.ruckus_r1 import RuckusR1Client
from backend.models import (
    Hop, DeviceType, Issue, IssueSeverity, TraceResult,
    DiagnosticOptions, TestResult, TestStatus,
)
from backend.tracer import resolver as _resolver
from backend.tracer.diagnostics import run_all_checks

logger = logging.getLogger(__name__)


class NetworkTracer:
    def __init__(self, config: AppConfig):
        self.config = config
        self.fg = FortiGateClient(config.fortigate)
        self.fg_ssh = FortiGateSSH(config.fortigate)
        self.cisco_switches = [CiscoSwitch(sw) for sw in config.cisco_switches]
        self.r1 = RuckusR1Client(config.ruckus_r1)

    async def trace(self, query: str, options: DiagnosticOptions = None) -> TraceResult:
        if options is None:
            options = DiagnosticOptions()
        start = time.time()
        result = TraceResult(query=query)

        # Step 1 — Resolve input → MAC + IP
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

        # Step 2 — FortiGate hop (always first)
        fg_hop = await self._build_fg_hop(mac, resolution.ip)
        result.path.append(fg_hop)

        # Step 3 — Query all Cisco switches in parallel
        cisco_tasks = [sw.gather_all(norm_mac, options) for sw in self.cisco_switches]
        cisco_results = await asyncio.gather(*cisco_tasks, return_exceptions=True)
        cisco_results = [r for r in cisco_results if isinstance(r, dict)]

        # Step 4 — R1: wireless client + R1-managed switch (parallel)
        r1_client_info = None
        r1_switch_info = None
        try:
            r1_client_info, r1_switch_info = await asyncio.gather(
                self.r1.find_client_by_mac(norm_mac),
                self.r1.find_switch_port_for_mac(norm_mac),
                return_exceptions=True,
            )
            if isinstance(r1_client_info, Exception):
                r1_client_info = None
            if isinstance(r1_switch_info, Exception):
                r1_switch_info = None
        except Exception as e:
            logger.warning(f"R1 lookup failed: {e}")

        # Step 5 — Find edge switch (MAC on access port)
        edge = self._find_edge(cisco_results)

        if edge:
            # ── Chain-walk from edge switch toward FortiGate ──
            switch_hops = await self._walk_path(edge, cisco_results, options)
            result.path.extend(switch_hops)

            last_sw = switch_hops[-1] if switch_hops else None

            if r1_client_info and not isinstance(r1_client_info, Exception):
                # ── Wireless client confirmed via R1 ──
                logger.info(f"[wireless] r1_client_info keys: {list(r1_client_info.keys())}")
                logger.info(f"[wireless] r1_client_info: {r1_client_info}")

                # Check for a Ruckus ICX switch sitting between the Cisco edge and the AP.
                # Guard: if _walk_path already added a non-Cisco switch (ICX) as the last
                # hop, don't add it again via _build_ruckus_sw_from_edge.
                icx_already_in_path = (
                    last_sw is not None
                    and last_sw.device_type != DeviceType.CISCO_SWITCH
                )
                if icx_already_in_path:
                    logger.info(
                        "[wireless] ICX already in path from _walk_path (%s) — skipping duplicate",
                        last_sw.device_name,
                    )
                    ruckus_sw_hop = None
                else:
                    ruckus_sw_hop = await self._build_ruckus_sw_from_edge(edge, len(result.path))
                if ruckus_sw_hop:
                    logger.info(f"[wireless] Ruckus ICX hop built: {ruckus_sw_hop.device_name}")
                    result.path.append(ruckus_sw_hop)
                elif not icx_already_in_path:
                    logger.info("[wireless] No Ruckus ICX switch detected on access port")

                ap_id = (
                    r1_client_info.get("apId")
                    or r1_client_info.get("connectedApId")
                    or r1_client_info.get("ap_id")
                    or r1_client_info.get("accessPointId")
                )
                logger.info(f"[wireless] ap_id resolved to: {ap_id!r}")
                if ap_id:
                    ap_hop = await self._build_ap_hop(str(ap_id), len(result.path))
                    logger.info(f"[wireless] _build_ap_hop returned: {ap_hop}")
                    if ap_hop:
                        result.path.append(ap_hop)
                else:
                    logger.warning("[wireless] No AP ID found in r1_client_info — AP hop skipped")

                result.path.append(self._end_hop_wireless(r1_client_info, mac, resolution.ip, len(result.path)))
            else:
                # ── Not found in R1 as wireless — check access port CDP/LLDP for AP ──
                logger.info("[wireless] r1_client_info is None — falling back to CDP/LLDP AP detection")
                access_port = edge.get("mac_entry").port if edge.get("mac_entry") else None
                all_nbrs = _dedup_neighbors(edge.get("all_cdp", []) + edge.get("all_lldp", []))
                logger.info(
                    "[wireless] edge access_port=%s, neighbors: %s",
                    access_port,
                    [(
                        getattr(n, "local_port", ""),
                        getattr(n, "remote_device", ""),
                        (getattr(n, "platform", "") or getattr(n, "system_description", ""))[:60],
                    ) for n in all_nbrs]
                )
                if last_sw and last_sw.device_type != DeviceType.CISCO_SWITCH:
                    # ── Non-Cisco switch (ICX) already in path from _walk_path ──
                    # Don't add it again.  Check for a direct AP hop; if none,
                    # the client is wireless through the Ruckus infrastructure.
                    ap_hop = await self._check_if_ap(last_sw, edge, cisco_results)
                    if ap_hop:
                        result.path.append(ap_hop)
                    logger.info(
                        "[wireless] Client behind non-Cisco switch %r — treating as wireless",
                        last_sw.device_name,
                    )
                    result.path.append(self._end_hop_wireless(None, mac, resolution.ip, len(result.path)))
                else:
                    # ── Last hop is a Cisco switch — try ICX then direct AP ──
                    # _build_ruckus_sw_from_edge handles Po* access ports by
                    # resolving physical member ports (CDP/LLDP lives on Gi, not Po).
                    ruckus_sw_hop = await self._build_ruckus_sw_from_edge(edge, len(result.path))
                    if ruckus_sw_hop:
                        logger.info(
                            "[wireless] Ruckus ICX detected on access port — adding ICX hop",
                        )
                        result.path.append(ruckus_sw_hop)
                        result.path.append(self._end_hop_wireless(None, mac, resolution.ip, len(result.path)))
                    else:
                        ap_hop = await self._check_if_ap(last_sw, edge, cisco_results)
                        if ap_hop:
                            result.path.append(ap_hop)
                            result.path.append(self._end_hop_wireless(None, mac, resolution.ip, len(result.path)))
                        else:
                            result.path.append(self._end_hop_wired(mac, resolution.ip, len(result.path)))

        elif r1_client_info and not isinstance(r1_client_info, Exception):
            # ── Wireless client found via R1 but no Cisco edge switch found ──
            # Try to find the Ruckus ICX via r1_switch_info
            if r1_switch_info and not isinstance(r1_switch_info, Exception):
                result.path.append(self._build_r1_switch_hop(r1_switch_info, len(result.path)))

            ap_id = r1_client_info.get("apId") or r1_client_info.get("connectedApId")
            if ap_id:
                ap_hop = await self._build_ap_hop(str(ap_id), len(result.path))
                if ap_hop:
                    result.path.append(ap_hop)
            result.path.append(self._end_hop_wireless(r1_client_info, mac, resolution.ip, len(result.path)))

        elif r1_switch_info and not isinstance(r1_switch_info, Exception):
            result.path.append(self._build_r1_switch_hop(r1_switch_info, len(result.path)))
            result.path.append(self._end_hop_wired(mac, resolution.ip, len(result.path)))

        else:
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
                    detail="Device may be offline, on an unmanaged switch, or the MAC has aged out",
                )],
            ))

        # Step 6 — Run diagnostics on all hops
        all_issues, test_summary = run_all_checks(result.path, options)
        result.all_issues = all_issues
        result.test_summary = test_summary

        if not result.status or result.status == "success":
            has_critical = any(i.severity == IssueSeverity.CRITICAL for i in all_issues)
            result.status = "issues" if has_critical else "success"

        result.trace_time_ms = int((time.time() - start) * 1000)
        return result

    # ──────────────────────────────────────────────────────────────
    # Chain-walk path builder  (replaces broken BFS)
    # ──────────────────────────────────────────────────────────────

    async def _walk_path(
        self,
        edge: Dict,
        all_cisco: List[Dict],
        options: DiagnosticOptions,
    ) -> List[Hop]:
        """
        Walk the network path starting from the edge (access) switch toward the
        FortiGate, one hop at a time.  Handles unknown intermediate devices
        (e.g. Ruckus switches) by looking at what the neighbouring Cisco switch
        reports as its CDP/LLDP peer.

        Display order: core-most switch first (order=1) so that the rendered
        path reads  FG → core → … → access → device.
        """
        fg_ip = self.config.fortigate.host
        hops_raw: List[Dict] = []   # accumulated in edge→core order
        visited: set = set()

        current = edge
        coming_from_port: Optional[str] = None   # port on current device that the previous hop used

        for _ in range(8):
            sw_name = current.get("hostname") or current.get("switch", "")
            if sw_name in visited:
                break
            visited.add(sw_name)

            # Access port = port where the end-device MAC was seen (only for edge)
            is_edge = len(hops_raw) == 0
            access_port: Optional[str] = None
            if is_edge and current.get("mac_entry"):
                access_port = current["mac_entry"].port

            # Collect all CDP + LLDP neighbors, deduped by remote device
            all_neighbors = _dedup_neighbors(
                current.get("all_cdp", []) + current.get("all_lldp", [])
            )

            # Uplink candidates = all neighbors NOT on the access port
            uplink_candidates = [
                n for n in all_neighbors
                if access_port is None or n.local_port != access_port
            ] or all_neighbors

            uplink = self._pick_uplink(uplink_candidates, fg_ip, visited)

            hops_raw.append({
                "raw": current,
                "is_edge": is_edge,
                "ingress_port": coming_from_port,   # port on THIS device from previous hop
                "egress_port": uplink.local_port if uplink else None,
                "access_port": access_port,
            })

            if not uplink:
                break

            neighbor_ip   = getattr(uplink, "remote_ip", None)
            neighbor_name = getattr(uplink, "remote_device", "")

            # Reached FortiGate?
            if neighbor_ip == fg_ip or "forti" in neighbor_name.lower():
                break

            # Known Cisco switch?
            next_cisco = (
                self._result_by_hostname(neighbor_name, all_cisco)
                or self._result_by_ip(neighbor_ip, all_cisco)
            )
            if next_cisco:
                coming_from_port = getattr(uplink, "remote_port", None)
                current = next_cisco
                continue

            # ── Unknown intermediate device (Ruckus switch, etc.) ──
            # Find which other Cisco switch has this device as its CDP/LLDP peer.
            beyond = self._cisco_beyond(neighbor_name, neighbor_ip, sw_name, all_cisco)

            # Determine the intermediate device's egress port (toward beyond switch)
            inter_egress: Optional[str] = None
            inter_ingress = getattr(uplink, "remote_port", None)  # port on Ruckus facing current
            if beyond:
                # Look at beyond switch's CDP/LLDP for the intermediate device
                for n in _dedup_neighbors(beyond.get("all_cdp", []) + beyond.get("all_lldp", [])):
                    if (getattr(n, "remote_device", "") == neighbor_name
                            or (neighbor_ip and getattr(n, "remote_ip", None) == neighbor_ip)):
                        inter_egress = getattr(n, "remote_port", None)
                        coming_from_port = n.local_port   # port on beyond switch facing intermediate
                        break

            # Enrich intermediate hop with R1 data (model, ports) when CDP/LLDP is incomplete
            r1_sw = await self.r1.get_switch_by_name_or_ip(name=neighbor_name, ip=neighbor_ip or "")
            if r1_sw and (not inter_ingress or not inter_egress):
                sw_id = r1_sw.get("id") or r1_sw.get("switchId")
                if sw_id:
                    ports = await self.r1.get_switch_ports(str(sw_id))
                    uplink_ports = [
                        p for p in ports
                        if str(p.get("portType", "")).upper() in ("TRUNK", "UPLINK")
                        or p.get("isUplink")
                    ]
                    access_ports = [
                        p for p in ports
                        if str(p.get("portType", "")).upper() == "ACCESS"
                    ]
                    if not inter_egress and uplink_ports:
                        inter_egress = str(uplink_ports[0].get("portName") or uplink_ports[0].get("name") or "")
                    if not inter_ingress and access_ports:
                        inter_ingress = str(access_ports[0].get("portName") or access_ports[0].get("name") or "")

            inter_hop = self._build_intermediate_hop(
                uplink, len(hops_raw) + 1,
                ingress_port=inter_ingress,
                egress_port=inter_egress,
                r1_data=r1_sw,
            )
            hops_raw.append({
                "hop": inter_hop,
                "is_intermediate": True,
            })
            visited.add(neighbor_name)

            if beyond:
                current = beyond
            else:
                break

        # ── Dead-end branch exclusion ──────────────────────────────────────────
        # If the edge switch's access port connects to a network device (another
        # switch) that already appears elsewhere in the hop chain, then the edge
        # switch is a side branch — not the real traffic path.  Remove it.
        #
        # Classic case: Ruckus ICX is multi-homed to switch-fortigate AND to
        # TV-Switch.  TV-Switch sees the wireless client MAC (via ICX) and gets
        # chosen as edge, but the true path is: FG → switch-fortigate → ICX → AP.
        # TV-Switch's access port (Gi0/4) has ICX as its CDP/LLDP neighbor, and
        # ICX is already in the hop chain as an intermediate hop → exclude TV-Switch.
        if len(hops_raw) > 1:
            first = hops_raw[0]
            if not first.get("is_intermediate") and first.get("is_edge"):
                edge_raw    = first["raw"]
                edge_name   = edge_raw.get("hostname") or edge_raw.get("switch", "")
                access_port = first.get("access_port")
                if access_port:
                    all_nbrs = _dedup_neighbors(
                        edge_raw.get("all_cdp", []) + edge_raw.get("all_lldp", [])
                    )
                    access_port_nbr_names = {
                        getattr(n, "remote_device", "")
                        for n in all_nbrs
                        if getattr(n, "local_port", "") == access_port
                        and getattr(n, "remote_device", "")
                    }
                    if access_port_nbr_names:
                        in_path: set = set()
                        for entry in hops_raw[1:]:
                            if entry.get("is_intermediate"):
                                hop = entry.get("hop")
                                if hop:
                                    in_path.add(hop.device_name)
                            else:
                                r = entry.get("raw", {})
                                in_path.add(r.get("hostname") or r.get("switch", ""))
                        in_path.discard("")
                        if access_port_nbr_names.issubset(in_path):
                            logger.info(
                                "[walk_path] Excluding dead-end edge %s — access port %s "
                                "neighbor(s) %s already in path %s",
                                edge_name, access_port, access_port_nbr_names, in_path,
                            )
                            hops_raw = hops_raw[1:]

        # Reverse so path reads FG → core → access (hops_raw is edge → core)
        hops_raw.reverse()

        result_hops: List[Hop] = []
        for i, entry in enumerate(hops_raw):
            order = i + 1
            if entry.get("is_intermediate"):
                hop = entry["hop"]
                hop.order = order
                result_hops.append(hop)
            else:
                hop = self._build_cisco_hop(
                    raw=entry["raw"],
                    order=order,
                    is_edge=entry["is_edge"],
                    access_port=entry["access_port"],
                    ingress_port=entry["ingress_port"],
                    egress_port=entry["egress_port"],
                )
                result_hops.append(hop)

        return result_hops

    def _pick_uplink(self, neighbors: List, fg_ip: str, visited: set) -> Optional[Any]:
        """Return the best uplink neighbor candidate (toward FortiGate)."""
        known_ips = {sw.host for sw in self.cisco_switches}

        # Priority 1 — FortiGate
        for n in neighbors:
            if getattr(n, "remote_ip", None) == fg_ip:
                return n
            if "forti" in getattr(n, "remote_device", "").lower():
                return n

        # Priority 2 — Known Cisco switch not yet visited
        for n in neighbors:
            ip   = getattr(n, "remote_ip", None)
            name = getattr(n, "remote_device", "")
            if ip in known_ips and name not in visited:
                return n

        # Priority 3 — Any switch (by CDP capabilities or name pattern)
        for n in neighbors:
            name = getattr(n, "remote_device", "")
            caps = getattr(n, "capabilities", [])
            if name not in visited and any("switch" in c.lower() or "router" in c.lower() for c in caps):
                return n

        # Priority 4 — Anything not yet visited
        for n in neighbors:
            if getattr(n, "remote_device", "") not in visited:
                return n

        return None

    def _cisco_beyond(
        self,
        device_name: str,
        device_ip: Optional[str],
        exclude_sw: str,
        all_cisco: List[Dict],
    ) -> Optional[Dict]:
        """Find a Cisco switch (other than exclude_sw) that has device_name as CDP/LLDP neighbor."""
        for raw in all_cisco:
            sw = raw.get("hostname") or raw.get("switch", "")
            if sw == exclude_sw or not raw.get("reachable"):
                continue
            for n in _dedup_neighbors(raw.get("all_cdp", []) + raw.get("all_lldp", [])):
                if (getattr(n, "remote_device", "") == device_name
                        or (device_ip and getattr(n, "remote_ip", None) == device_ip)):
                    return raw
        return None

    def _result_by_hostname(self, name: str, cisco_results: List[Dict]) -> Optional[Dict]:
        for raw in cisco_results:
            if raw.get("hostname") == name or raw.get("switch") == name:
                return raw
        return None

    def _result_by_ip(self, ip: Optional[str], cisco_results: List[Dict]) -> Optional[Dict]:
        if not ip:
            return None
        for raw in cisco_results:
            if raw.get("host") == ip:
                return raw
        return None

    def _find_edge(self, cisco_results: List[Dict]) -> Optional[Dict]:
        """Return the switch most likely to be directly connected to the end device.

        Priority tiers (highest → lowest):
          1. Non-trunk, non-portchannel  — ideal access port
          2. Non-trunk, portchannel      — unusual but possible
          3. Trunk, non-portchannel      — AP/device port in trunk mode (multi-SSID)
          4. Trunk, portchannel          — MAC came through an uplink; last resort
        """
        candidates = [
            (raw, raw["mac_entry"].port if raw.get("mac_entry") else "")
            for raw in cisco_results if raw.get("mac_entry")
        ]
        logger.info(
            "[find_edge] candidates: %s",
            [(r.get("hostname", r.get("switch", "?")), p, r.get("is_trunk", "?"))
             for r, p in candidates]
        )

        def _is_po(port: str) -> bool:
            return port.upper().startswith("PO")

        # Tier 1 — non-trunk, non-portchannel
        for raw, port in candidates:
            if raw.get("reachable") and not raw.get("is_trunk", True) and not _is_po(port):
                logger.info("[find_edge] tier1 → %s port %s", raw.get("hostname", "?"), port)
                return raw
        # Tier 2 — non-trunk, portchannel
        for raw, port in candidates:
            if raw.get("reachable") and not raw.get("is_trunk", True):
                logger.info("[find_edge] tier2 → %s port %s", raw.get("hostname", "?"), port)
                return raw
        # Tier 3 — trunk on a regular port (AP trunk, direct attachment)
        for raw, port in candidates:
            if not _is_po(port):
                logger.info("[find_edge] tier3 → %s port %s", raw.get("hostname", "?"), port)
                return raw
        # Tier 4 — trunk on portchannel (MAC arrived via uplink, last resort)
        for raw, port in candidates:
            logger.info("[find_edge] tier4 → %s port %s", raw.get("hostname", "?"), port)
            return raw
        return None

    # ──────────────────────────────────────────────────────────────
    # Hop builders
    # ──────────────────────────────────────────────────────────────

    async def _build_fg_hop(self, mac: str, ip: Optional[str]) -> Hop:
        hostname = "FortiGate"
        fg_interface = ""
        vendor = "Fortinet"
        model = ""
        version = ""
        interface_stats = {}
        try:
            hostname = await self.fg.get_hostname()
            arp_entry = await self.fg.get_arp_entry(mac=mac)
            fg_interface = arp_entry.get("interface", "") if arp_entry else ""

            # SSH gives richer platform info and egress interface error counters
            ssh_data = await self.fg_ssh.gather(fg_interface)
            model   = ssh_data.get("model", "")
            version = ssh_data.get("version", "")
            if ssh_data.get("hostname"):
                hostname = ssh_data["hostname"]
            interface_stats = ssh_data.get("interface_stats", {})

            # Fall back to REST API for model/version if SSH didn't return them
            if not model:
                platform = await self.fg.get_platform_info()
                model   = platform.get("model", "")
                version = version or platform.get("version", "")
        except Exception:
            pass

        return Hop(
            order=0,
            device_type=DeviceType.FIREWALL,
            device_name=hostname,
            device_ip=self.config.fortigate.host,
            vendor=vendor,
            model=model,
            software_version=version,
            egress_port=fg_interface or None,
            raw_data={"arp_interface": fg_interface, "interface_stats": interface_stats},
        )

    def _build_cisco_hop(
        self,
        raw: Dict,
        order: int,
        is_edge: bool,
        access_port: Optional[str],
        ingress_port: Optional[str],
        egress_port: Optional[str],
    ) -> Hop:
        hostname = raw.get("hostname") or raw.get("switch", "Unknown Switch")
        host_ip  = raw.get("host", "")
        ver      = raw.get("version", {})
        vendor   = "Cisco"
        model    = ver.get("model", "")
        ios_ver  = ver.get("ios_version", "")

        # SNMP can supplement model/version when SSH parsing came up empty
        snmp_sys = raw.get("snmp_system") or {}
        if not model:
            model = snmp_sys.get("model", "")
        if not ios_ver:
            ios_ver = snmp_sys.get("ios_version", "")
        if hostname in ("Unknown Switch", raw.get("switch", "")) and snmp_sys.get("hostname"):
            hostname = snmp_sys["hostname"]

        mac_entry = raw.get("mac_entry")
        vlan = mac_entry.vlan if (is_edge and mac_entry) else None

        # For the edge switch, ingress = port facing device (access_port)
        if is_edge and access_port:
            ingress_port = access_port

        # CDP/LLDP neighbor on the ingress port (device-facing) only for edge
        cdp_n  = raw.get("cdp_neighbor")  if is_edge else None
        lldp_n = raw.get("lldp_neighbor") if is_edge else None

        return Hop(
            order=order,
            device_type=DeviceType.CISCO_SWITCH,
            device_name=hostname,
            device_ip=host_ip,
            vendor=vendor,
            model=model,
            software_version=ios_ver,
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
                "version": ver,
                "is_trunk": raw.get("is_trunk", False),
                "error": raw.get("error"),
                "etherchannel_members": raw.get("etherchannel_members", []),
                "uplink_details": raw.get("uplink_details", {}),
                "system_mtu": raw.get("system_mtu", {}),
                # SNMP supplemental data (present only when snmp_community is configured)
                "snmp_source": raw.get("snmp_source", False),
                "snmp_system": raw.get("snmp_system"),
                "snmp_mac": raw.get("snmp_mac"),
                "snmp_int_stats": raw.get("snmp_int_stats"),
            },
        )

    def _build_intermediate_hop(
        self,
        neighbor: Any,
        order: int,
        ingress_port: Optional[str] = None,
        egress_port: Optional[str] = None,
        r1_data: Optional[Dict] = None,
    ) -> Hop:
        """Build a hop for a device we can't SSH into (identified via CDP/LLDP and/or R1)."""
        name     = getattr(neighbor, "remote_device", "Unknown")
        ip       = getattr(neighbor, "remote_ip", None)
        platform = getattr(neighbor, "platform", "") or getattr(neighbor, "system_description", "")

        vendor, model = _parse_vendor_model(name, platform)
        device_type = DeviceType.RUCKUS_SWITCH if "ruckus" in vendor.lower() else DeviceType.UNKNOWN
        if "icx" in platform.lower() or "icx" in name.lower():
            device_type = DeviceType.RUCKUS_SWITCH
            if not vendor:
                vendor = "Ruckus"

        # Enrich from R1 if available
        if r1_data:
            if not model:
                model = r1_data.get("model") or r1_data.get("modelName") or ""
            if not ip:
                ip = r1_data.get("ip") or r1_data.get("ipAddress")
            device_type = DeviceType.RUCKUS_SWITCH
            if not vendor:
                vendor = "Ruckus"

        return Hop(
            order=order,
            device_type=device_type,
            device_name=name,
            device_ip=ip,
            vendor=vendor,
            model=model,
            ingress_port=ingress_port,
            egress_port=egress_port,
            raw_data={"platform": platform, "source": "cdp_lldp", "r1_data": r1_data or {}},
        )

    def _build_r1_switch_hop(self, r1_switch_info: Dict, order: int) -> Hop:
        sw   = r1_switch_info.get("switch", {})
        port = r1_switch_info.get("port", {})
        name = sw.get("name") or sw.get("switchName") or "Ruckus Switch"
        ip   = sw.get("ip") or sw.get("ipAddress")
        port_name = str(port.get("portName") or port.get("name") or port.get("id", ""))
        model = sw.get("model") or sw.get("modelName") or ""
        return Hop(
            order=order,
            device_type=DeviceType.RUCKUS_SWITCH,
            device_name=name,
            device_ip=ip,
            vendor="Ruckus",
            model=model,
            ingress_port=port_name or None,
            raw_data={"r1_data": r1_switch_info},
        )

    async def _build_ap_hop(self, ap_id: str, order: int) -> Optional[Hop]:
        try:
            ap = await self.r1.get_ap_by_id(ap_id)
            logger.info(f"[ap_hop] get_ap_by_id({ap_id!r}) → {ap}")
            if not ap:
                return None
            name  = ap.get("name") or ap.get("apName") or f"AP-{ap_id}"
            ip    = ap.get("ip") or ap.get("ipAddress")
            model = ap.get("model") or ap.get("modelName") or ""

            # Try to find the wired uplink port from R1 AP data.
            # R1 One uses various field names depending on firmware version.
            uplink_port = (
                ap.get("uplinkPort")
                or ap.get("connectedSwitchPort")
                or ap.get("uplinkIfName")
                or ap.get("wiredPort")
                or ap.get("switchPort")
                or ap.get("connectedPort")
            )
            if uplink_port:
                uplink_port = str(uplink_port).strip() or None

            # Redact sensitive fields before storing in raw_data
            _REDACT = {"loginPassword", "password", "secret", "apiKey", "api_key"}
            safe_ap = {k: "***" if k in _REDACT else v for k, v in ap.items()}
            return Hop(
                order=order,
                device_type=DeviceType.RUCKUS_AP,
                device_name=name,
                device_ip=ip,
                vendor="Ruckus",
                model=model,
                ingress_port=uplink_port,   # wired uplink port (if R1 provides it)
                raw_data={"ap_id": ap_id, "r1_data": safe_ap},
            )
        except Exception as e:
            logger.warning(f"R1 AP hop failed: {e}")
        return None

    def _end_hop_wired(self, mac: str, ip: Optional[str], order: int) -> Hop:
        return Hop(
            order=order,
            device_type=DeviceType.WIRED_CLIENT,
            device_name=ip or mac,
            device_ip=ip,
            raw_data={"mac": mac},
        )

    def _end_hop_wireless(self, r1_client: Optional[Dict], mac: str, ip: Optional[str], order: int) -> Hop:
        name = ip or mac
        ssid = ""
        rssi = None
        if r1_client:
            name = r1_client.get("hostname") or r1_client.get("clientName") or name
            ssid = r1_client.get("ssid") or r1_client.get("wlanName") or ""
            rssi = r1_client.get("rssi") or r1_client.get("signal")
        issues = []
        if rssi:
            try:
                if int(rssi) < -75:
                    issues.append(Issue(
                        severity=IssueSeverity.WARNING, category="wireless",
                        message=f"Weak RSSI: {rssi} dBm",
                        detail="Poor signal — client may experience packet loss",
                    ))
            except (ValueError, TypeError):
                pass
        return Hop(
            order=order,
            device_type=DeviceType.WIRELESS_CLIENT,
            device_name=name,
            device_ip=ip,
            issues=issues,
            raw_data={"mac": mac, "ssid": ssid, "rssi": rssi, "r1_data": r1_client or {}},
        )

    def _resolve_access_neighbors(self, edge: Dict) -> List:
        """
        Return CDP/LLDP neighbors on the edge switch's access port (the port where
        the end-device MAC was learned).

        Port-channel (Po*) handling:
          CDP/LLDP neighbors are advertised on the physical member ports (Gi1/0/22),
          NOT on the virtual Po interface.  When the access port is a port-channel,
          we look up its member ports from etherchannel_members and return neighbors
          on those physical ports.

        Falls back to per-port cdp_neighbor / lldp_neighbor if all_cdp/all_lldp
        didn't capture the access port directly.
        """
        access_port = edge["mac_entry"].port if edge.get("mac_entry") else None
        all_nbrs = _dedup_neighbors(edge.get("all_cdp", []) + edge.get("all_lldp", []))

        # Direct match
        if access_port:
            nbrs = [n for n in all_nbrs if getattr(n, "local_port", "") == access_port]
        else:
            nbrs = list(all_nbrs)

        # Port-channel: neighbors are on member physical ports, not on the Po interface
        if not nbrs and access_port and access_port.upper().startswith("PO"):
            members = {
                m["port"] for m in edge.get("etherchannel_members", [])
                if isinstance(m, dict) and m.get("port")
            }
            logger.info(
                "[resolve_nbrs] access_port=%s is port-channel, members=%s", access_port, members
            )
            if members:
                nbrs = [n for n in all_nbrs if getattr(n, "local_port", "") in members]

        # Per-port fallback (neighbor_info diagnostic option)
        if not nbrs:
            nbrs = [n for n in [edge.get("cdp_neighbor"), edge.get("lldp_neighbor")] if n]

        return nbrs

    async def _build_ruckus_sw_from_edge(self, edge: Dict, order: int) -> Optional[Hop]:
        """
        Inspect the device-facing port of the edge Cisco switch.
        If a Ruckus ICX switch is there (not an AP), build and return a hop for it.
        Used to surface the ICX in wireless paths: Cisco → ICX → AP → client.
        Handles port-channel access ports by resolving physical member ports first.
        """
        if not edge.get("mac_entry"):
            return None

        access_nbrs = self._resolve_access_neighbors(edge)
        access_port = edge["mac_entry"].port
        logger.info(
            "[ruckus_sw] access_port=%s, resolved neighbors: %s",
            access_port,
            [(getattr(n, "local_port", ""), getattr(n, "remote_device", ""),
              (getattr(n, "platform", "") or getattr(n, "system_description", ""))[:50])
             for n in access_nbrs],
        )
        access_nbr = access_nbrs[0] if access_nbrs else None
        logger.info(
            "[ruckus_sw] access_nbr: device=%r platform=%r",
            getattr(access_nbr, "remote_device", "None"),
            (getattr(access_nbr, "platform", "") or getattr(access_nbr, "system_description", ""))[:50],
        )
        if not access_nbr:
            return None

        name     = getattr(access_nbr, "remote_device", "")
        ip       = getattr(access_nbr, "remote_ip", None)
        platform = getattr(access_nbr, "platform", "") or getattr(access_nbr, "system_description", "")
        combined = (name + " " + platform).lower()

        # Must be a switch (ICX), not a Ruckus AP
        is_ruckus_switch = (
            "icx" in combined
            or ("ruckus" in combined and not any(
                m in combined for m in ("r350", "r450", "r510", "r550", "r650", "r670", "r750", "r770", "t310", "t610", "t750", "h320", "h510", "h550")
            ))
        )
        if not is_ruckus_switch:
            return None

        r1_sw = await self.r1.get_switch_by_name_or_ip(name=name, ip=ip or "")
        ingress_port = getattr(access_nbr, "remote_port", None)  # port on ICX facing the Cisco switch

        return self._build_intermediate_hop(
            access_nbr, order,
            ingress_port=ingress_port,
            egress_port=None,  # egress toward AP not known from Cisco CDP/LLDP
            r1_data=r1_sw,
        )

    async def _check_if_ap(
        self,
        last_sw_hop: Optional[Hop],
        edge: Dict,
        cisco_results: List[Dict],
    ) -> Optional[Hop]:
        """
        Check if the device-facing port on the edge switch connects directly to a Ruckus AP.
        Uses all_cdp/all_lldp (always collected) filtered to the access port, so this works
        regardless of whether the neighbor_info diagnostic option is enabled.
        Handles port-channel access ports by resolving physical member ports.
        """
        access_port = edge["mac_entry"].port if edge.get("mac_entry") else None
        access_nbrs = self._resolve_access_neighbors(edge)

        for nbr in access_nbrs:
            combined = (
                getattr(nbr, "remote_device", "") + " "
                + getattr(nbr, "platform", "")
                + " " + getattr(nbr, "system_description", "")
            ).lower()

            logger.info(
                "[check_if_ap] neighbor=%r combined=%r",
                getattr(nbr, "remote_device", ""),
                combined[:120],
            )

            is_ruckus = any(kw in combined for kw in (
                "ruckus",
                # Indoor APs
                "r350", "r450", "r510", "r550",
                "r650", "r660", "r670",
                "r750", "r760", "r770",
                # Outdoor APs
                "t310", "t610", "t750",
                # Wall-plate APs
                "h320", "h510", "h550",
            ))
            is_icx    = "icx" in combined  # ICX = switch, not AP

            if not is_ruckus or is_icx:
                logger.info("[check_if_ap] skipping %r — is_ruckus=%s is_icx=%s", getattr(nbr, "remote_device", ""), is_ruckus, is_icx)
                continue  # not a Ruckus AP

            nbr_ip  = getattr(nbr, "remote_ip", None)
            nbr_mac = normalize_mac(nbr.remote_device) if _looks_like_mac(nbr.remote_device) else None
            order = (last_sw_hop.order + 1) if last_sw_hop else 10
            ap = None
            if nbr_mac:
                ap = await self.r1.get_ap_by_mac(nbr_mac)
            if not ap and nbr_ip:
                for candidate in await self.r1.get_all_aps():
                    if candidate.get("ip") == nbr_ip or candidate.get("ipAddress") == nbr_ip:
                        ap = candidate
                        break

            if ap:
                ap_id = ap.get("id") or ap.get("apId")
                return await self._build_ap_hop(str(ap_id), order)

            # R1 unavailable or AP not found there — build hop from CDP/LLDP data alone.
            # We already confirmed it's a Ruckus AP from the system_description.
            name     = getattr(nbr, "remote_device", "Ruckus AP")
            sys_desc = getattr(nbr, "system_description", "") or getattr(nbr, "platform", "")
            # Extract model from system_description: "Ruckus R670 Multimedia Hotzone..."
            model = name  # default to CDP/LLDP device name (e.g. "R670")
            m = re.search(r'\b(R\d{3}[\w-]*|T\d{3}[\w-]*|H\d{3}[\w-]*)', sys_desc, re.IGNORECASE)
            if m:
                model = m.group(1)
            logger.info(f"[check_if_ap] R1 unavailable — building AP hop from LLDP: name={name!r} model={model!r} ip={nbr_ip!r}")

            # AP's own LLDP port ID — Ruckus often uses dot-notation MAC (0033.5835.fbf0)
            # as port ID; filter those out since they're meaningless as a port label.
            ap_own_port = getattr(nbr, "remote_port", "") or ""
            if re.match(r'^[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}$', ap_own_port, re.IGNORECASE):
                ap_own_port = ""

            # Forward the connecting switch port's interface data so the UI can show
            # link status, error counters, and PoE without SSH access to the AP itself.
            sw_int_status  = edge.get("int_status")
            sw_int_details = edge.get("int_details")
            sw_poe         = edge.get("poe_status")

            return Hop(
                order=order,
                device_type=DeviceType.RUCKUS_AP,
                device_name=name,
                device_ip=nbr_ip,
                vendor="Ruckus",
                model=model,
                ingress_port=ap_own_port or None,
                raw_data={
                    "source": "lldp",
                    "system_description": sys_desc,
                    "switch_port":        access_port,
                    "switch_int_status":  sw_int_status.model_dump()  if sw_int_status  else None,
                    "switch_int_details": sw_int_details.model_dump() if sw_int_details else None,
                    "switch_poe":         sw_poe.model_dump()         if sw_poe         else None,
                },
            )
        return None


# ──────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────

def _dedup_neighbors(neighbors: List) -> List:
    """Remove duplicate CDP/LLDP entries for the same remote device."""
    seen: set = set()
    result = []
    for n in neighbors:
        key = getattr(n, "remote_device", "") or getattr(n, "remote_ip", "")
        if key and key not in seen:
            seen.add(key)
            result.append(n)
        elif not key:
            result.append(n)
    return result


def _parse_vendor_model(device_name: str, platform: str) -> tuple:
    """Extract (vendor, model) from CDP/LLDP platform string or device name."""
    combined = (platform + " " + device_name).lower()
    if "ruckus" in combined or "icx" in combined or "brocade" in combined:
        vendor = "Ruckus"
        # Extract model: look for ICX\d+ or R\d+ patterns
        m = re.search(r"\b(ICX\s*\d+[\w-]*|R\d{3}[\w-]*|T\d{3}[\w-]*)", platform, re.IGNORECASE)
        model = m.group(1) if m else ""
        return vendor, model
    if "cisco" in combined:
        vendor = "Cisco"
        m = re.search(r"\b(WS-C\w+|C\d{4}[\w-]*|N\d{4}[\w-]*)", platform, re.IGNORECASE)
        model = m.group(1) if m else ""
        return vendor, model
    if "hp" in combined or "aruba" in combined or "procurve" in combined:
        return "HP/Aruba", ""
    if "juniper" in combined:
        return "Juniper", ""
    return "", ""


def _looks_like_mac(s: str) -> bool:
    return bool(re.match(r"^([0-9a-f]{2}[:\-.]){5}[0-9a-f]{2}$", s, re.IGNORECASE))
