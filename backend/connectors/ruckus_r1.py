"""
Ruckus One REST API connector.

Auth:   Authorization: Bearer <api_key>
Paths:  All paths start at /venues/...  (no /v1/ prefix)
Docs:   RUCKUS_One_Consolidated_API_04212026.json
"""

import httpx
import logging
import re
from typing import Optional, List, Dict, Any

from backend.config import RuckusR1Config

logger = logging.getLogger(__name__)


def normalize_mac(mac: str) -> str:
    return re.sub(r"[.:\-]", "", mac).lower()


def _colon_mac(mac: str) -> str:
    norm = normalize_mac(mac)
    return ":".join(norm[i:i + 2] for i in range(0, 12, 2))


class RuckusR1Client:
    def __init__(self, config: RuckusR1Config):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._venue_id: Optional[str] = None   # cached after first venues call

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

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
                logger.error("R1: 401 Unauthorized on GET %s — %s", path, r.text[:200])
                return None
            if not r.is_success:
                logger.warning("R1: HTTP %s on GET %s — %s", r.status_code, url, r.text[:300])
                return None
            return r.json()
        except Exception as e:
            logger.warning("R1 GET %s failed: %s", path, e)
            return None

    async def _post(self, path: str, body: Dict = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            r = await self._get_client().post(url, json=body or {})
            if r.status_code == 401:
                logger.error("R1: 401 Unauthorized on POST %s — %s", path, r.text[:200])
                return None
            if not r.is_success:
                logger.warning("R1: HTTP %s on POST %s — %s", r.status_code, url, r.text[:300])
                return None
            return r.json()
        except Exception as e:
            logger.warning("R1 POST %s failed: %s", path, e)
            return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _extract_list(self, data: Any) -> List[Dict]:
        """R1 wraps lists in a 'data' key — unwrap it."""
        if data is None:
            return []
        if isinstance(data, list):
            return data
        for key in ("data", "result", "results", "list", "items"):
            if isinstance(data, dict) and key in data:
                val = data[key]
                if isinstance(val, list):
                    return val
        return []

    # ------------------------------------------------------------------
    # Venues  —  GET /venues
    # ------------------------------------------------------------------

    async def get_venues(self) -> List[Dict]:
        data = await self._get("/venues")
        return self._extract_list(data)

    async def _get_venue_id(self) -> Optional[str]:
        """Return the cached venue ID, fetching from API on first call."""
        if self._venue_id:
            return self._venue_id
        venues = await self.get_venues()
        if not venues:
            logger.warning("R1: no venues found — check API key and base_url")
            return None
        logger.info(
            "R1: %d venue(s) found: %s",
            len(venues),
            [(v.get("name", "?"), v.get("id") or v.get("venueId")) for v in venues],
        )
        for v in venues:
            vid = str(v.get("id") or v.get("venueId") or "").strip()
            if vid:
                self._venue_id = vid
                logger.info("R1: using venue '%s' (id=%s)", v.get("name", "?"), vid)
                return vid
        return None

    async def get_venue_ids(self) -> List[str]:
        """Legacy compat — returns list with the one venue ID."""
        vid = await self._get_venue_id()
        return [vid] if vid else []

    # ------------------------------------------------------------------
    # Access Points
    #   List:       POST /venues/aps/query
    #   By serial:  GET  /venues/{venueId}/aps/{serialNumber}
    # ------------------------------------------------------------------

    async def get_all_aps(self) -> List[Dict]:
        """POST /venues/aps/query — returns all APs for the tenant."""
        data = await self._post("/venues/aps/query", {"pageSize": 1000})
        return self._extract_list(data)

    async def get_ap_by_mac(self, mac: str) -> Optional[Dict]:
        cm = _colon_mac(mac)
        data = await self._post("/venues/aps/query", {
            "filters": {"macAddress": [cm]},
            "pageSize": 5,
        })
        items = self._extract_list(data)
        if items:
            return items[0]
        # Fallback: scan all (handles format mismatches)
        norm = normalize_mac(mac)
        for ap in await self.get_all_aps():
            ap_mac = normalize_mac(ap.get("macAddress", ap.get("mac", "")))
            if ap_mac == norm:
                return ap
        return None

    async def get_ap_by_id(self, ap_id: str) -> Optional[Dict]:
        """
        ap_id is the AP serial number (Ruckus One identifies APs by serial).
        Tries GET /venues/{venueId}/aps/{serialNumber} first, then falls
        back to a POST query filtered by serialNumber.
        """
        venue_id = await self._get_venue_id()
        if venue_id:
            data = await self._get(f"/venues/{venue_id}/aps/{ap_id}")
            if data:
                items = self._extract_list(data)
                if items:
                    return items[0]
                if isinstance(data, dict) and (data.get("serialNumber") or data.get("name")):
                    return data

        # Fallback: query by serialNumber
        data = await self._post("/venues/aps/query", {
            "filters": {"serialNumber": [ap_id]},
            "pageSize": 5,
        })
        items = self._extract_list(data)
        return items[0] if items else None

    # ------------------------------------------------------------------
    # Switches
    #   List:   GET  /venues/{venueId}/switches
    #   Ports:  POST /venues/switches/switchPorts/query
    # ------------------------------------------------------------------

    async def get_all_switches(self) -> List[Dict]:
        venue_id = await self._get_venue_id()
        if not venue_id:
            return []
        data = await self._get(f"/venues/{venue_id}/switches")
        return self._extract_list(data)

    async def get_switch_by_mac(self, mac: str) -> Optional[Dict]:
        norm = normalize_mac(mac)
        for sw in await self.get_all_switches():
            sw_mac = normalize_mac(sw.get("mac", sw.get("macAddress", "")))
            if sw_mac == norm:
                return sw
        return None

    async def get_switch_by_name_or_ip(self, name: str = "", ip: str = "") -> Optional[Dict]:
        name_lower = name.lower()
        for sw in await self.get_all_switches():
            sw_name = (sw.get("name") or sw.get("switchName") or "").lower()
            sw_ip   = sw.get("ip") or sw.get("ipAddress") or ""
            if name_lower and name_lower in sw_name:
                return sw
            if ip and ip == sw_ip:
                return sw
        return None

    async def get_switch_ports(self, switch_id: str) -> List[Dict]:
        """
        POST /venues/switches/switchPorts/query filtered by switchId.
        Returns normalized list compatible with old code that expects
        portName, portType, isUplink.
        """
        data = await self._post("/venues/switches/switchPorts/query", {
            "filters": {"switchId": [switch_id]},
            "pageSize": 200,
        })
        items = self._extract_list(data)
        result = []
        for p in items:
            # Derive uplink/access from LLDP neighbor presence or LAG membership
            has_neighbor = bool(p.get("neighborName") or p.get("neighborMacAddress"))
            in_lag       = bool(p.get("lagId"))
            is_uplink    = has_neighbor or in_lag
            port_type    = "UPLINK" if is_uplink else "ACCESS"
            result.append({
                "portName": p.get("portIdentifier") or p.get("port") or p.get("name") or "",
                "name":     p.get("name") or p.get("portIdentifier") or "",
                "portType": port_type,
                "isUplink": is_uplink,
                "status":   p.get("status", ""),
                "neighborName": p.get("neighborName"),
                "poeEnabled":   p.get("poeEnabled"),
                "poeUsed":      p.get("poeUsed"),
                "_raw":     p,
            })
        return result

    async def find_switch_port_for_mac(self, mac: str) -> Optional[Dict]:
        """
        POST /venues/switches/clients/query — find a MAC address on a switch port.
        Returns normalized {switch: {...}, port: {...}} for _build_r1_switch_hop.
        """
        cm = _colon_mac(mac)
        data = await self._post("/venues/switches/clients/query", {
            "filters": {"clientMac": [cm]},
            "pageSize": 5,
        })
        items = self._extract_list(data)
        if not items:
            return None
        c = items[0]
        return {
            "switch": {
                "name":         c.get("switchName", ""),
                "id":           c.get("switchId", ""),
                "switchId":     c.get("switchId", ""),
                "mac":          c.get("switchMac", ""),
                "serialNumber": c.get("switchSerialNumber", ""),
            },
            "port": {
                "portName":   c.get("switchPort", ""),
                "name":       c.get("switchPort", ""),
                "id":         c.get("switchPortId", ""),
                "isRuckusAP": c.get("isRuckusAP", False),
                "vlan":       c.get("clientVlan", ""),
                "venueName":  c.get("venueName", ""),
            },
        }

    # ------------------------------------------------------------------
    # Wireless Clients
    #   POST /venues/aps/clients/query
    # ------------------------------------------------------------------

    async def find_client_by_mac(self, mac: str) -> Optional[Dict]:
        """
        POST /venues/aps/clients/query filtered by macAddress.
        Normalizes the response to the flat dict shape mac_tracer expects:
          apId, hostname, ssid, rssi, ipAddress, apName, apMac.
        """
        cm = _colon_mac(mac)
        data = await self._post("/venues/aps/clients/query", {
            "filters": {"macAddress": [cm]},
            "pageSize": 5,
        })
        items = self._extract_list(data)
        if not items:
            logger.info("R1: client %s not found in AP client list", cm)
            return None

        client   = items[0]
        ap_info  = client.get("apInformation")  or {}
        net_info = client.get("networkInformation") or {}
        signal   = client.get("signalStatus")   or {}

        logger.info("R1: found client %s — apInformation keys: %s", cm, list(ap_info.keys()))

        # AP serial number is the identifier in Ruckus One (used as apId)
        ap_serial = (
            ap_info.get("apSerialNumber")
            or ap_info.get("serialNumber")
            or ap_info.get("apId")
            or ap_info.get("id")
        )
        ap_name = (
            ap_info.get("apName")
            or ap_info.get("name")
            or ""
        )
        ap_mac = (
            ap_info.get("apMacAddress")
            or ap_info.get("macAddress")
            or ap_info.get("bssid")
            or ""
        )
        ssid = (
            net_info.get("ssid")
            or net_info.get("wlanName")
            or net_info.get("networkName")
            or ""
        )
        rssi = signal.get("rssi") or signal.get("signal")

        return {
            # Identification
            "macAddress": client.get("macAddress", ""),
            "hostname":   client.get("hostname") or client.get("alias") or "",
            "ipAddress":  client.get("ipAddress") or "",
            # AP — both key names checked by mac_tracer
            "apId":          ap_serial,
            "connectedApId": ap_serial,
            "apName":        ap_name,
            "apMac":         ap_mac,
            # Network / signal
            "ssid": ssid,
            "rssi": rssi,
            # Raw for debugging
            "_raw": client,
        }

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    async def test_connection(self) -> Dict:
        """Probe GET /venues and return raw HTTP result for the /api/r1/test endpoint."""
        url = f"{self.base_url}/venues"
        try:
            r = await self._get_client().get(url)
            return {
                "url":              url,
                "status_code":      r.status_code,
                "ok":               r.is_success,
                "response_snippet": r.text[:500],
            }
        except Exception as e:
            return {"url": url, "error": str(e), "ok": False}

    async def get_ap_uplink_info(self, ap_id: str) -> Optional[Dict]:
        """Stub kept for interface compatibility — not implemented in R1 v1 spec."""
        return None

    async def get_client_count_per_ap(self) -> Dict[str, int]:
        """Returns {ap_serial: client_count} for all currently connected clients."""
        counts: Dict[str, int] = {}
        data = await self._post("/venues/aps/clients/query", {"pageSize": 2000})
        for client in self._extract_list(data):
            ap_info = client.get("apInformation") or {}
            ap_id = (
                ap_info.get("apSerialNumber")
                or ap_info.get("serialNumber")
                or ap_info.get("apId")
            )
            if ap_id:
                counts[str(ap_id)] = counts.get(str(ap_id), 0) + 1
        return counts
