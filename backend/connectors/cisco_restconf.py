"""
Cisco IOS-XE RESTCONF connector.
Tested against IOS-XE 16.6+ / Catalyst 9000 / Catalyst 3650/3850 series.

RESTCONF base : https://<host>:<port>/restconf/data/
Auth          : HTTP Basic (Authorization: Basic <base64(user:pass)>)
Media type    : application/yang-data+json

When restconf_enabled is True in CiscoSwitchConfig, CiscoSwitch.gather_all()
runs RESTCONF in parallel with SSH.  RESTCONF results take precedence for the
queries it covers; SSH supplies the rest (STP, PoE, system MTU, logs).
"""
import re
import ssl
import logging
import base64
import ipaddress
from typing import Optional, List, Dict, Any
from urllib.parse import quote

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from backend.config import CiscoSwitchConfig
from backend.models import (
    MACEntry, InterfaceStatus, InterfaceDetails,
    CDPNeighbor, LLDPNeighbor,
)

logger = logging.getLogger(__name__)

# ── IOS-XE YANG model paths (stable across 16.x / 17.x) ──────────────────────
_P_HOSTNAME    = "Cisco-IOS-XE-native:native/hostname"
_P_MAC_TABLE   = "Cisco-IOS-XE-matm:matm-operational/matm-table/matm-mac-entry"
_P_ARP         = "Cisco-IOS-XE-arp:arp-data/arp-vrf"
_P_CDP         = "Cisco-IOS-XE-cdp:cdp-neighbor-details/cdp-neighbor-detail"
_P_LLDP        = "Cisco-IOS-XE-lldp:lldp-entries/lldp-intf-details"
_P_IFACE_OPR   = "Cisco-IOS-XE-interfaces-oper:interfaces/interface"
_P_INVENTORY   = "Cisco-IOS-XE-device-hardware-oper:device-hardware-data/device-hardware/device-inventory"


def _norm(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def _to_cisco_mac(norm: str) -> str:
    return f"{norm[0:4]}.{norm[4:8]}.{norm[8:12]}"


def _shorten(name: str) -> str:
    for long, short in [
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("TenGigabitEthernet", "Te"),
        ("TwentyFiveGigE", "Twe"),
        ("HundredGigE", "Hu"),
        ("Port-channel", "Po"),
        ("Vlan", "Vl"),
    ]:
        if name.startswith(long):
            return name.replace(long, short, 1)
    return name


class CiscoRestconf:
    """Async RESTCONF client for a single IOS-XE switch."""

    def __init__(self, config: CiscoSwitchConfig):
        self.config = config
        self.name   = config.name

        # Prefer dedicated RESTCONF creds; fall back to SSH creds
        user = config.restconf_username or config.username or ""
        pwd  = config.restconf_password or config.password or ""
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()

        self._base  = f"https://{config.host}:{config.restconf_port}/restconf/data/"
        self._headers = {
            "Accept":       "application/yang-data+json",
            "Content-Type": "application/yang-data+json",
            "Authorization": f"Basic {token}",
        }
        self._ssl: Any = None if config.restconf_verify_ssl else False

    # ── Internal HTTP helper ──────────────────────────────────────────────────

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        """GET /restconf/data/<path>; return parsed JSON dict/list or None."""
        if not HAS_AIOHTTP:
            return None
        url = self._base + path
        try:
            async with aiohttp.ClientSession(headers=self._headers) as session:
                async with session.get(url, params=params, ssl=self._ssl, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 204:
                        return {}   # no content (empty table)
                    if resp.status == 404:
                        logger.debug("[%s] RESTCONF 404: %s", self.name, path)
                        return None
                    logger.warning("[%s] RESTCONF %d: %s", self.name, resp.status, path)
                    return None
        except aiohttp.ClientConnectorError:
            logger.debug("[%s] RESTCONF unreachable (%s)", self.name, self.config.host)
            return None
        except Exception as e:
            logger.debug("[%s] RESTCONF error on %s: %s", self.name, path, type(e).__name__)
            return None

    # ── Public query methods ──────────────────────────────────────────────────

    async def test_connection(self) -> bool:
        """Return True if RESTCONF is reachable and responds to a basic query."""
        if not HAS_AIOHTTP:
            return False
        data = await self._get(_P_HOSTNAME)
        return data is not None

    async def get_hostname(self) -> str:
        data = await self._get(_P_HOSTNAME)
        if data:
            return data.get("Cisco-IOS-XE-native:hostname", self.config.name)
        return self.config.name

    async def get_version(self) -> Dict:
        """Return dict with model/ios_version/serial — same shape as SSH _get_version_summary()."""
        data = await self._get(_P_INVENTORY)
        if not data:
            return {}
        items = (
            data.get("Cisco-IOS-XE-device-hardware-oper:device-inventory") or
            data.get("device-inventory") or []
        )
        model = serial = ios_ver = ""
        for item in items if isinstance(items, list) else []:
            hw_type = item.get("hw-type", "")
            if hw_type in ("hw-type-chassis", "hw-type-module") and not model:
                model = item.get("part-number", "")
            if hw_type == "hw-type-chassis":
                serial = item.get("serial-number", "")
            ver = item.get("version", "")
            if ver and not ios_ver:
                ios_ver = ver
        return {"model": model, "ios_version": ios_ver, "serial": serial}

    async def get_mac_entry(self, norm_mac: str) -> Optional[MACEntry]:
        """Look up a MAC in the forwarding table."""
        cisco_mac = _to_cisco_mac(norm_mac)
        data = await self._get(_P_MAC_TABLE)
        if not data:
            return None
        entries = (
            data.get("Cisco-IOS-XE-matm:matm-mac-entry") or
            data.get("matm-mac-entry") or []
        )
        for e in (entries if isinstance(entries, list) else []):
            addr = e.get("address") or e.get("mac-address") or ""
            if _norm(addr) == norm_mac:
                port = e.get("input-interface") or e.get("interface") or ""
                vlan = e.get("vlan") or 0
                etype = e.get("type") or "dynamic"
                return MACEntry(
                    mac=addr,
                    vlan=int(vlan) if str(vlan).isdigit() else 0,
                    port=_shorten(port),
                    entry_type=str(etype).lower(),
                )
        return None

    async def get_arp_table(self) -> List[Dict]:
        data = await self._get(_P_ARP)
        if not data:
            return []
        vrfs = (
            data.get("Cisco-IOS-XE-arp:arp-vrf") or
            data.get("arp-vrf") or []
        )
        result = []
        for vrf in (vrfs if isinstance(vrfs, list) else []):
            for entry in (vrf.get("arp-entry") or []):
                ip  = entry.get("address") or entry.get("ip") or ""
                mac = entry.get("hardware") or entry.get("mac") or ""
                iface = entry.get("interface") or entry.get("vrf-interface") or ""
                if ip and mac:
                    result.append({"ip": ip, "mac": mac, "interface": _shorten(iface)})
        return result

    async def get_cdp_neighbors(self) -> List[CDPNeighbor]:
        data = await self._get(_P_CDP)
        if not data:
            return []
        items = (
            data.get("Cisco-IOS-XE-cdp:cdp-neighbor-detail") or
            data.get("cdp-neighbor-detail") or []
        )
        result = []
        for n in (items if isinstance(items, list) else []):
            device_id  = n.get("device-id") or ""
            local_port = _shorten(n.get("local-intf-name") or "")
            remote_port = _shorten(n.get("port-id") or "")
            platform   = n.get("platform") or ""
            # IP address may be nested in ipv4-addresses list
            ip = None
            addrs = n.get("ip-addresses") or {}
            if isinstance(addrs, dict):
                ipv4 = addrs.get("ipv4-address")
                if isinstance(ipv4, list):
                    ip = ipv4[0] if ipv4 else None
                elif isinstance(ipv4, str):
                    ip = ipv4
            caps_raw = n.get("capability-codes") or ""
            caps = [c.strip() for c in re.split(r"[,\s]+", caps_raw) if c.strip()]
            if device_id or local_port:
                result.append(CDPNeighbor(
                    local_port=local_port,
                    remote_device=device_id,
                    remote_port=remote_port,
                    remote_ip=ip,
                    platform=platform,
                    capabilities=caps,
                ))
        return result

    async def get_lldp_neighbors(self) -> List[LLDPNeighbor]:
        data = await self._get(_P_LLDP)
        if not data:
            return []
        ifaces = (
            data.get("Cisco-IOS-XE-lldp:lldp-intf-details") or
            data.get("lldp-intf-details") or []
        )
        result = []
        for iface_entry in (ifaces if isinstance(ifaces, list) else []):
            local_port = _shorten(iface_entry.get("if-name") or "")
            neighbors  = iface_entry.get("lldp-neighbor-details") or {}
            nbr_list   = neighbors.get("lldp-neighbor-detail") or []
            for n in (nbr_list if isinstance(nbr_list, list) else [nbr_list]):
                name   = n.get("system-name") or ""
                port   = _shorten(n.get("port-id") or "")
                sys_d  = (n.get("system-description") or "")[:120]
                mgmt   = None
                mgmt_data = n.get("management-address") or {}
                if isinstance(mgmt_data, dict):
                    mgmt = mgmt_data.get("address")
                elif isinstance(mgmt_data, list) and mgmt_data:
                    mgmt = mgmt_data[0].get("address")
                if name or local_port:
                    result.append(LLDPNeighbor(
                        local_port=local_port,
                        remote_device=name,
                        remote_port=port,
                        remote_ip=mgmt,
                        system_description=sys_d,
                    ))
        return result

    async def _get_interface_oper(self, port: str) -> Optional[Dict]:
        """Fetch operational state for a single interface."""
        # IOS-XE RESTCONF uses full interface names in the key
        expansions = [
            ("Gi", "GigabitEthernet"),
            ("Fa", "FastEthernet"),
            ("Te", "TenGigabitEthernet"),
            ("Twe", "TwentyFiveGigE"),
            ("Hu", "HundredGigE"),
            ("Po", "Port-channel"),
            ("Vl", "Vlan"),
        ]
        long_port = port
        for short, long in expansions:
            if port.startswith(short) and not port.startswith(long):
                long_port = long + port[len(short):]
                break
        encoded = quote(long_port, safe="")
        data = await self._get(f"{_P_IFACE_OPR}={encoded}")
        if not data:
            return None
        return (
            data.get("Cisco-IOS-XE-interfaces-oper:interface") or
            data.get("interface") or
            (data if isinstance(data, dict) else None)
        )

    async def get_interface_status(self, port: str) -> Optional[InterfaceStatus]:
        d = await self._get_interface_oper(port)
        if not d:
            return None
        oper_status = (d.get("oper-status") or "").lower()
        status = "connected" if oper_status == "if-oper-state-ready" else (
            "err-disabled" if "err" in oper_status else "notconnect"
        )
        speed_val = d.get("speed") or d.get("negotiated-speed") or ""
        stats = d.get("statistics") or {}
        return InterfaceStatus(
            name=port,
            status=status,
            speed=str(speed_val),
        )

    async def get_interface_details(self, port: str) -> Optional[InterfaceDetails]:
        d = await self._get_interface_oper(port)
        if not d:
            return None
        stats = d.get("statistics") or {}
        oper  = (d.get("oper-status") or "").lower()
        is_up = oper == "if-oper-state-ready"

        def _i(key: str) -> int:
            try:
                return int(stats.get(key, 0) or 0)
            except (ValueError, TypeError):
                return 0

        return InterfaceDetails(
            name=port,
            is_up=is_up,
            mtu=int(d.get("mtu") or 0),
            input_errors=_i("in-errors"),
            output_errors=_i("out-errors"),
            crc_errors=_i("in-crc-errors"),
            input_rate_bps=_i("in-octets") * 8,   # octets/sample → rough bps
            output_rate_bps=_i("out-octets") * 8,
        )
