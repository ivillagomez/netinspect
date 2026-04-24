"""
Aruba CX (AOS-CX) REST API connector.
Tested against AOS-CX 10.08 / 10.10 — Aruba 6000 / 6100 series.

REST base : https://<host>:<port>/rest/v10.10/
Auth      : Cookie-based — POST /rest/v10.10/login  {"username":..., "password":...}
            The server returns a Set-Cookie header; include that cookie on all
            subsequent requests.  Call logout() when done.

When rest_enabled is True in ArubaSwitchConfig, ArubaSwitch.gather_all()
runs this client in parallel with SSH.  REST results take precedence for the
queries it covers; SSH supplies system logs.
"""
import re
import logging
from typing import Optional, List, Dict, Any

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from backend.config import ArubaSwitchConfig
from backend.models import MACEntry, InterfaceStatus, InterfaceDetails, LLDPNeighbor

logger = logging.getLogger(__name__)

_API = "/rest/v10.10"


def _norm(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def _shorten(name: str) -> str:
    """AOS-CX uses port names like 1/1/5 — leave as-is; shorten GE variants."""
    for long, short in [
        ("GigabitEthernet", "GE"),
        ("TenGigabitEthernet", "10GE"),
        ("FortyGigabitEthernet", "40GE"),
        ("HundredGigabitEthernet", "100GE"),
        ("management", "mgmt"),
    ]:
        if name.lower().startswith(long.lower()):
            return short + name[len(long):]
    return name


class ArubaCxRest:
    """Async REST client for a single Aruba CX switch.

    Usage (per-gather_all call):
        client = ArubaCxRest(config)
        ok = await client.login()
        if ok:
            mac_entry = await client.get_mac_entry(norm_mac)
            ...
        await client.logout()
    """

    def __init__(self, config: ArubaSwitchConfig):
        self.config  = config
        self.name    = config.name
        self._base   = f"https://{config.host}:{config.rest_port}{_API}"
        self._ssl    = None if config.rest_verify_ssl else False
        self._cookies: Optional[aiohttp.CookieJar] = None
        self._session: Optional[aiohttp.ClientSession] = None

        # Prefer dedicated REST creds; fall back to SSH creds
        self._user = config.rest_username or config.username or ""
        self._pass = config.rest_password or config.password or ""

    # ── Session lifecycle ─────────────────────────────────────────────────────

    async def login(self) -> bool:
        """Open a session and authenticate.  Returns True on success."""
        if not HAS_AIOHTTP:
            return False
        try:
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(
                cookie_jar=jar,
                timeout=aiohttp.ClientTimeout(total=10),
            )
            resp = await self._session.post(
                f"{self._base}/login",
                json={"username": self._user, "password": self._pass},
                ssl=self._ssl,
            )
            if resp.status == 200:
                logger.debug("[%s] ArubaOS-CX REST login OK", self.name)
                return True
            logger.warning("[%s] ArubaOS-CX REST login failed (HTTP %d)", self.name, resp.status)
            await self._close_session()
            return False
        except Exception as e:
            logger.debug("[%s] ArubaOS-CX REST login error: %s", self.name, type(e).__name__)
            await self._close_session()
            return False

    async def logout(self) -> None:
        if self._session:
            try:
                await self._session.post(f"{self._base}/logout", ssl=self._ssl)
            except Exception:
                pass
        await self._close_session()

    async def _close_session(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    # ── Internal HTTP helper ──────────────────────────────────────────────────

    async def _get(self, path: str, params: Optional[Dict] = None) -> Optional[Any]:
        if not self._session:
            return None
        url = self._base + path
        try:
            async with self._session.get(url, params=params, ssl=self._ssl) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                if resp.status in (204, 404):
                    return None
                logger.debug("[%s] ArubaOS-CX REST %d: %s", self.name, resp.status, path)
                return None
        except Exception as e:
            logger.debug("[%s] ArubaOS-CX REST error on %s: %s", self.name, path, type(e).__name__)
            return None

    # ── Query methods ─────────────────────────────────────────────────────────

    async def test_connection(self) -> bool:
        """Attempt a login/logout cycle to verify REST API is reachable."""
        ok = await self.login()
        if ok:
            await self.logout()
        return ok

    async def get_hostname(self) -> str:
        data = await self._get("/system", params={"attributes": "hostname"})
        if data and isinstance(data, dict):
            return data.get("hostname", self.config.name)
        return self.config.name

    async def get_mac_entry(self, norm_mac: str) -> Optional[MACEntry]:
        """Search the MAC address table across all VLANs."""
        # Get VLAN list
        vlans_data = await self._get("/system/vlans")
        if not vlans_data or not isinstance(vlans_data, dict):
            return None

        for vlan_uri, _ in vlans_data.items():
            # vlan_uri is like "/rest/v10.10/system/vlans/10"
            vlan_id = vlan_uri.rstrip("/").split("/")[-1]
            if not vlan_id.isdigit():
                continue
            macs = await self._get(f"/system/vlans/{vlan_id}/macs", params={"depth": "2"})
            if not macs or not isinstance(macs, dict):
                continue
            for mac_key, mac_info in macs.items():
                # mac_key is like "aa:bb:cc:dd:ee:ff,dynamic,10"  or just the MAC in some versions
                if _norm(mac_key.split(",")[0]) == norm_mac:
                    # Port is a dict with a single URI key
                    port_dict = (mac_info or {}).get("port") or {}
                    port_name = ""
                    for port_uri in port_dict:
                        port_name = _shorten(port_uri.rstrip("/").split("/")[-1])
                        break
                    return MACEntry(
                        mac=mac_key.split(",")[0],
                        vlan=int(vlan_id),
                        port=port_name,
                        entry_type="dynamic",
                    )
        return None

    async def get_arp_table(self) -> List[Dict]:
        data = await self._get("/system/vrfs/default/neighbors", params={"depth": "2"})
        if not data or not isinstance(data, dict):
            return []
        result = []
        for ip, info in data.items():
            if not isinstance(info, dict):
                continue
            mac = info.get("mac_addr") or info.get("mac") or ""
            port_dict = info.get("port") or {}
            iface = ""
            for uri in port_dict:
                iface = _shorten(uri.rstrip("/").split("/")[-1])
                break
            if ip and mac:
                result.append({"ip": ip, "mac": mac, "interface": iface})
        return result

    async def get_lldp_neighbors(self) -> List[LLDPNeighbor]:
        """Collect LLDP neighbors from all interfaces."""
        # Get all interface names
        iface_data = await self._get("/system/interfaces", params={"depth": "1"})
        if not iface_data or not isinstance(iface_data, dict):
            return []

        result = []
        for iface_uri in iface_data:
            iface_name = _shorten(iface_uri.rstrip("/").split("/")[-1])
            encoded    = iface_uri.rstrip("/").split("/")[-1]
            nbrs = await self._get(f"/system/interfaces/{encoded}/lldp_neighbors", params={"depth": "2"})
            if not nbrs or not isinstance(nbrs, dict):
                continue
            for nbr_key, nbr_info in nbrs.items():
                if not isinstance(nbr_info, dict):
                    continue
                neighbor = nbr_info.get("neighbor_info") or nbr_info
                name     = neighbor.get("chassis_name") or neighbor.get("system_name") or ""
                port_id  = _shorten(neighbor.get("port_id") or "")
                sys_desc = (neighbor.get("sys_description") or neighbor.get("system_description") or "")[:120]
                mgmt_ips = neighbor.get("mgmt_ip_list") or []
                mgmt_ip  = mgmt_ips[0] if mgmt_ips else None
                if name:
                    result.append(LLDPNeighbor(
                        local_port=iface_name,
                        remote_device=name,
                        remote_port=port_id,
                        remote_ip=mgmt_ip,
                        system_description=sys_desc,
                    ))
        return result

    async def get_interface_status(self, port: str) -> Optional[InterfaceStatus]:
        data = await self._get(f"/system/interfaces/{port}",
                               params={"attributes": "link_state,admin_state,link_speed,description"})
        if not data or not isinstance(data, dict):
            return None
        link = (data.get("link_state") or "").lower()
        status = "connected" if link == "up" else "notconnect"
        speed  = str(data.get("link_speed") or "")
        return InterfaceStatus(name=port, status=status, speed=speed)

    async def get_interface_details(self, port: str) -> Optional[InterfaceDetails]:
        data = await self._get(f"/system/interfaces/{port}/statistics", params={"depth": "1"})
        if not data or not isinstance(data, dict):
            return None

        def _i(key: str) -> int:
            try:
                return int(data.get(key, 0) or 0)
            except (ValueError, TypeError):
                return 0

        return InterfaceDetails(
            name=port,
            is_up=True,   # status checked separately
            input_errors=_i("if_in_errors"),
            output_errors=_i("if_out_errors"),
            crc_errors=_i("if_in_crc_errors"),
            input_rate_bps=_i("if_in_octets") * 8,
            output_rate_bps=_i("if_out_octets") * 8,
        )
