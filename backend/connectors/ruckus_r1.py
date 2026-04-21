import httpx
import logging
import re
from typing import Optional, List, Dict, Any

from backend.config import RuckusR1Config

logger = logging.getLogger(__name__)


def normalize_mac(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


class RuckusR1Client:
    def __init__(self, config: RuckusR1Config):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._venues: Optional[List[Dict]] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=20.0,
                verify=True,
            )
        return self._client

    async def _get(self, path: str, params: Dict = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            r = await self._get_client().get(url, params=params or {})
            if r.status_code == 401:
                logger.error("R1 API: Unauthorized — check API key")
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"R1 GET {path} failed: {e}")
            return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _extract_list(self, data: Any) -> List[Dict]:
        """R1 API can wrap results in various shapes."""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        for key in ("data", "result", "results", "list", "items"):
            if isinstance(data, dict) and key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
                if isinstance(val, dict):
                    return list(val.values())
        return []

    # ------------------------------------------------------------------
    # Venues
    # ------------------------------------------------------------------

    async def get_venues(self) -> List[Dict]:
        if self._venues is not None:
            return self._venues
        data = await self._get("/v1/venues")
        self._venues = self._extract_list(data)
        return self._venues

    async def get_venue_ids(self) -> List[str]:
        venues = await self.get_venues()
        ids = []
        for v in venues:
            vid = v.get("id") or v.get("venueId") or v.get("venue_id")
            if vid:
                ids.append(str(vid))
        return ids

    # ------------------------------------------------------------------
    # Access Points
    # ------------------------------------------------------------------

    async def get_all_aps(self) -> List[Dict]:
        venue_ids = await self.get_venue_ids()
        if not venue_ids:
            data = await self._get("/v1/aps")
            return self._extract_list(data)
        all_aps = []
        for vid in venue_ids:
            data = await self._get("/v1/aps", {"venueId": vid})
            all_aps.extend(self._extract_list(data))
        return all_aps

    async def get_ap_by_mac(self, mac: str) -> Optional[Dict]:
        norm = normalize_mac(mac)
        for ap in await self.get_all_aps():
            ap_mac = normalize_mac(ap.get("mac", ap.get("macAddress", ap.get("apMac", ""))))
            if ap_mac == norm:
                return ap
        return None

    async def get_ap_by_id(self, ap_id: str) -> Optional[Dict]:
        data = await self._get(f"/v1/aps/{ap_id}")
        if data:
            items = self._extract_list(data)
            return items[0] if items else (data if isinstance(data, dict) else None)
        return None

    # ------------------------------------------------------------------
    # Switches (R1-managed)
    # ------------------------------------------------------------------

    async def get_all_switches(self) -> List[Dict]:
        venue_ids = await self.get_venue_ids()
        if not venue_ids:
            data = await self._get("/v1/switches")
            return self._extract_list(data)
        all_sw = []
        for vid in venue_ids:
            data = await self._get("/v1/switches", {"venueId": vid})
            all_sw.extend(self._extract_list(data))
        return all_sw

    async def get_switch_by_mac(self, mac: str) -> Optional[Dict]:
        norm = normalize_mac(mac)
        for sw in await self.get_all_switches():
            sw_mac = normalize_mac(sw.get("mac", sw.get("macAddress", "")))
            if sw_mac == norm:
                return sw
        return None

    async def get_switch_ports(self, switch_id: str) -> List[Dict]:
        data = await self._get(f"/v1/switches/{switch_id}/ports")
        return self._extract_list(data)

    async def find_switch_port_for_mac(self, mac: str) -> Optional[Dict]:
        """Search all R1-managed switch ports for a given MAC."""
        norm = normalize_mac(mac)
        for sw in await self.get_all_switches():
            sw_id = sw.get("id") or sw.get("switchId")
            if not sw_id:
                continue
            ports = await self.get_switch_ports(str(sw_id))
            for port in ports:
                connected_macs = port.get("connectedMacs", port.get("macAddresses", []))
                for m in connected_macs:
                    if normalize_mac(str(m)) == norm:
                        return {"switch": sw, "port": port}
        return None

    # ------------------------------------------------------------------
    # Wireless Clients
    # ------------------------------------------------------------------

    async def find_client_by_mac(self, mac: str) -> Optional[Dict]:
        norm = normalize_mac(mac)
        # Try direct query first
        colon_mac = ":".join(norm[i:i+2] for i in range(0, 12, 2))
        data = await self._get("/v1/clients", {"mac": colon_mac})
        items = self._extract_list(data)
        if items:
            return items[0]

        # Also try dash format
        dash_mac = "-".join(norm[i:i+2] for i in range(0, 12, 2))
        data = await self._get("/v1/clients", {"mac": dash_mac})
        items = self._extract_list(data)
        if items:
            return items[0]

        # Fallback: list all clients and search
        venue_ids = await self.get_venue_ids()
        for vid in venue_ids:
            data = await self._get("/v1/clients", {"venueId": vid})
            for client in self._extract_list(data):
                client_mac = normalize_mac(client.get("mac", client.get("macAddress", "")))
                if client_mac == norm:
                    return client
        return None

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    async def get_ap_uplink_info(self, ap_id: str) -> Optional[Dict]:
        """Get the wired uplink port info for an AP."""
        data = await self._get(f"/v1/aps/{ap_id}/uplink")
        if data:
            return data if isinstance(data, dict) else self._extract_list(data)[0] if self._extract_list(data) else None
        # Some APIs embed wired uplink in AP object itself
        ap = await self.get_ap_by_id(ap_id)
        if ap:
            return ap.get("uplinkInfo") or ap.get("wiredUplink")
        return None

    async def get_client_count_per_ap(self) -> Dict[str, int]:
        """Returns {ap_id: client_count} for dashboard use."""
        counts: Dict[str, int] = {}
        venue_ids = await self.get_venue_ids()
        for vid in venue_ids:
            data = await self._get("/v1/clients", {"venueId": vid})
            for client in self._extract_list(data):
                ap_id = client.get("apId") or client.get("connectedApId")
                if ap_id:
                    counts[str(ap_id)] = counts.get(str(ap_id), 0) + 1
        return counts
