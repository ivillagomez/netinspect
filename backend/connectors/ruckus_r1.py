"""
Ruckus One REST API connector.

Auth:   OAuth2 Client Credentials  →  Authorization: Bearer <JWT>
        Client ID + Secret from portal: Administration → Settings → Application Tokens
        Token exchange: POST {base_url}/oauth2/token  (form-encoded)
Paths:  All paths start at /venues/...  (no /v1/ prefix)
Docs:   RUCKUS_One_Consolidated_API_04212026.json
"""

import time
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
        # OAuth2 token cache
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # OAuth2 Client Credentials token exchange
    # ------------------------------------------------------------------

    async def _try_token_url(self, token_url: str, cfg) -> tuple:
        """
        POST to token_url for a client-credentials token, manually chasing any
        HTTP redirects so the method stays POST (httpx converts POST→GET on 302
        when follow_redirects=True, causing infinite redirect loops).

        Tries three credential styles in order:
          1. form body  — RFC 6749 §2.3.1 body params (most providers)
          2. Basic Auth — creds in Authorization header (AWS Cognito style)
          3. JSON body  — non-standard fallback

        Returns (token_or_None, final_http_status, response_snippet).
        """
        credential_styles = [
            # Style 1: standard form-encoded body
            ("form", {
                "data": {
                    "grant_type":    "client_credentials",
                    "client_id":     cfg.client_id,
                    "client_secret": cfg.client_secret,
                }
            }),
            # Style 2: AWS Cognito — Basic Auth header, minimal body
            ("basic+form", {
                "data": {"grant_type": "client_credentials"},
                "auth": (cfg.client_id, cfg.client_secret),
            }),
            # Style 3: JSON body
            ("json", {
                "json": {
                    "grant_type":    "client_credentials",
                    "client_id":     cfg.client_id,
                    "client_secret": cfg.client_secret,
                }
            }),
        ]

        last_error = "no styles attempted"
        for style, post_kwargs in credential_styles:
            url = token_url
            try:
                for _hop in range(6):   # allow up to 5 redirect hops
                    async with httpx.AsyncClient(
                        timeout=15.0,
                        verify=True,
                        follow_redirects=False,   # manual chase keeps POST method
                        headers={"Accept": "application/json"},
                    ) as c:
                        r = await c.post(url, **post_kwargs)

                    if r.status_code in (301, 302, 303, 307, 308):
                        location = r.headers.get("location", "")
                        logger.info("R1 token [%s]: HTTP %s %s → %s",
                                    style, r.status_code, url, location)
                        if not location:
                            last_error = f"{style}: {r.status_code} redirect with no Location"
                            break
                        # SSO / authorization-code initiation redirect — NOT a token endpoint.
                        # (Spring Security pattern: /oauth2/authorization/{registrationId})
                        # Return a sentinel so callers can see this URL is wrong.
                        if "/oauth2/authorization" in location or "/login" in location:
                            logger.info(
                                "R1 token [%s]: SSO redirect detected → %s — "
                                "this URL is not the token endpoint",
                                style, location,
                            )
                            last_error = f"{style}: SSO redirect → {location}"
                            break   # try next credential style
                        url = location
                        continue        # POST again to Location

                    # Non-redirect response — evaluate
                    logger.info("R1 token [%s]: HTTP %s url=%s — %s",
                                style, r.status_code, url, r.text[:300])
                    if r.is_success:
                        data  = r.json()
                        token = data.get("access_token")
                        if token:
                            expires_in = int(data.get("expires_in", 3600))
                            self._token_expires_at = time.time() + expires_in - 60
                            logger.info("R1 token obtained via %s (url=%s, expires_in=%ds)",
                                        style, url, expires_in)
                            return token, r.status_code, r.text[:200]
                    # Non-success from a real endpoint — stop trying, report
                    return None, r.status_code, r.text[:300]

            except Exception as e:
                last_error = f"{style}: exception — {e}"
                logger.warning("R1 token [%s %s] error: %s", style, token_url, e)
                # Fall through to next credential style

        return None, 0, last_error

    async def _fetch_token(self) -> Optional[str]:
        """
        Exchange client_id + client_secret for a JWT access token.
        Tries multiple candidate token endpoint URLs in order.
        """
        cfg = self.config
        if not cfg.client_id or not cfg.client_secret:
            return cfg.api_key  # legacy static JWT / api_key fallback

        # Derive the auth-server base URL by stripping the "api." subdomain.
        # api.asia.ruckus.cloud/oauth2/token → 302 to asia.ruckus.cloud/oauth2/authorization/idm
        # The actual token endpoint lives on asia.ruckus.cloud, not api.asia.ruckus.cloud.
        import re as _re
        auth_base = _re.sub(r"^(https?://)api\.", r"\1", self.base_url)

        # Candidate token endpoint URLs (tried in order)
        candidates = [
            f"{auth_base}/oauth2/token",         # https://asia.ruckus.cloud/oauth2/token  ← likely winner
            f"{self.base_url}/oauth2/token",     # api.asia.ruckus.cloud (redirects to SSO — skipped)
            f"{self.base_url}/token",
            f"{self.base_url}/v1/oauth/token",
        ]
        for url in candidates:
            token, status, snippet = await self._try_token_url(url, cfg)
            if token:
                return token
            if status not in (0, 404, 405):
                # Got a real response (401, 400, etc.) — this is the right URL, wrong creds
                logger.error(
                    "R1 token exchange at %s → HTTP %s: %s", url, status, snippet
                )
                return None
            # 404/405/0 = wrong endpoint, try next
        logger.error("R1 token exchange: no working endpoint found among %s", candidates)
        return None

    async def _get_token(self) -> Optional[str]:
        """Return a valid access token, refreshing if expired."""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        self._access_token = await self._fetch_token()
        return self._access_token

    async def _auth_headers(self) -> Dict[str, str]:
        token = await self._get_token()
        if not token:
            return {}
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP helpers  (token fetched fresh per request group)
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Dict = None) -> Any:
        url = f"{self.base_url}{path}"
        hdrs = await self._auth_headers()
        try:
            async with httpx.AsyncClient(headers=hdrs, timeout=20.0, verify=True) as c:
                r = await c.get(url, params=params or {})
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
        hdrs = await self._auth_headers()
        try:
            async with httpx.AsyncClient(headers=hdrs, timeout=20.0, verify=True) as c:
                r = await c.post(url, json=body or {})
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
        """
        Test the OAuth2 token exchange then probe GET /venues and POST /venues/aps/query.
        """
        base   = self.base_url
        cfg    = self.config
        result: Dict = {
            "base_url":    base,
            "client_id":   (cfg.client_id or "")[:8] + "…" if cfg.client_id else None,
            "auth_mode":   "oauth2_client_credentials" if cfg.client_id else "static_bearer",
        }

        cfg = self.config
        import re as _re
        auth_base = _re.sub(r"^(https?://)api\.", r"\1", base)

        # ── Step 0: raw no-follow probes to reveal redirect chains ────────────
        async def _raw_probe(url: str, use_get: bool = False) -> dict:
            try:
                form_data = {
                    "grant_type":    "client_credentials",
                    "client_id":     cfg.client_id,
                    "client_secret": cfg.client_secret,
                }
                async with httpx.AsyncClient(
                    timeout=10.0, verify=True,
                    follow_redirects=False,
                    headers={"Accept": "application/json"},
                ) as c:
                    r = await c.get(url) if use_get else await c.post(url, data=form_data)
                return {
                    "status":   r.status_code,
                    "location": r.headers.get("location"),
                    "snippet":  r.text[:400],
                }
            except Exception as e:
                return {"error": str(e)}

        result["probes"] = {
            f"{base}/oauth2/token (POST)":       await _raw_probe(f"{base}/oauth2/token"),
            f"{auth_base}/oauth2/token (POST)":  await _raw_probe(f"{auth_base}/oauth2/token"),
            f"{auth_base}/.well-known/openid-configuration (GET)":
                await _raw_probe(f"{auth_base}/.well-known/openid-configuration", use_get=True),
            f"{base}/.well-known/openid-configuration (GET)":
                await _raw_probe(f"{base}/.well-known/openid-configuration", use_get=True),
        }
        # legacy key for backward compat
        result["oauth2_redirect_probe"] = result["probes"][f"{base}/oauth2/token (POST)"]

        # Step 1: token exchange — probe each candidate URL directly
        candidates = [
            f"{auth_base}/oauth2/token",
            f"{base}/oauth2/token",
            f"{base}/token",
            f"{base}/v1/oauth/token",
        ]
        token_probes = {}
        token = None
        for url in candidates:
            t, status, snippet = await self._try_token_url(url, cfg)
            token_probes[url] = {"status": status, "snippet": snippet[:200]}
            if t:
                token = t
                self._access_token = t
                break
        result["token_probes"]  = token_probes
        result["token_obtained"] = bool(token)
        result["token_prefix"]   = token[:20] + "…" if token else None

        if not token:
            result["error"] = "Token exchange failed on all candidate URLs — see token_probes"
            return result

        hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Step 2: GET /venues
        try:
            async with httpx.AsyncClient(headers=hdrs, timeout=10.0, verify=True) as c:
                r = await c.get(f"{base}/venues")
            result["GET /venues"] = {"status": r.status_code, "snippet": r.text[:400]}
        except Exception as e:
            result["GET /venues"] = {"error": str(e)}

        # Step 3: POST /venues/aps/query
        try:
            async with httpx.AsyncClient(headers=hdrs, timeout=10.0, verify=True) as c:
                r = await c.post(f"{base}/venues/aps/query", json={"pageSize": 1})
            result["POST /venues/aps/query"] = {"status": r.status_code, "snippet": r.text[:400]}
        except Exception as e:
            result["POST /venues/aps/query"] = {"error": str(e)}

        return result

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
