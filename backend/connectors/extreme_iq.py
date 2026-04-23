"""
ExtremeCloud IQ (XIQ) cloud API connector.

Auth options (in priority order):
  1. Static API key via X-Auth-Token header (simplest — generate in XIQ portal)
  2. Username/password login: POST /login → access_token

Client lookup:
  GET /xapi/v1/monitor/clients?macAddress={mac}
  GET /client/macaddr/{mac}          (alternative endpoint)

Reference: https://extremecloudiq.com/api-docs/api-reference.html
"""
import logging
import time
from typing import Optional, Dict, Any

import httpx

from backend.config import ExtremeIQConfig

logger = logging.getLogger(__name__)


class ExtremeIQClient:
    def __init__(self, config: ExtremeIQConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    def _auth_headers(self) -> Dict[str, str]:
        if self.config.api_key:
            return {"Authorization": f"Bearer {self.config.api_key}"}
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    async def _get_token(self) -> Optional[str]:
        """OAuth2 client_credentials or API key — skip if static key configured."""
        if self.config.api_key:
            return self.config.api_key
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        if self.config.client_id and self.config.client_secret:
            try:
                async with httpx.AsyncClient(timeout=15.0) as c:
                    r = await c.post(
                        f"{self.base_url}/oauth2/token",
                        data={
                            "grant_type":    "client_credentials",
                            "client_id":     self.config.client_id,
                            "client_secret": self.config.client_secret,
                        },
                    )
                    r.raise_for_status()
                    body = r.json()
                    self._token     = body.get("access_token")
                    expires_in      = int(body.get("expires_in", 86400))
                    self._token_exp = time.time() + expires_in
                    return self._token
            except Exception as e:
                logger.warning("ExtremeCloud IQ token exchange failed: %s", type(e).__name__)
        return None

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Optional[Any]:
        token = await self._get_token()
        if not token:
            return None
        try:
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(
                    f"{self.base_url}{path}",
                    params=params or {},
                    headers=headers,
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.debug("ExtremeCloud IQ GET %s failed: %s", path, type(e).__name__)
            return None

    async def find_client(self, norm_mac: str) -> Optional[Dict]:
        """Look up a client by normalized MAC.

        Tries two common XIQ endpoint patterns and returns the first match.
        Key response fields: hostname, macAddress, ip_address,
                             connection_type (WIRELESS/WIRED),
                             connected_ap_id, connected_switch_id,
                             connected_switch_port, vlan_id, ssid
        """
        # Format: xx:xx:xx:xx:xx:xx
        mac_colon = ":".join(norm_mac[i:i+2] for i in range(0, 12, 2))

        # Try primary monitoring endpoint
        data = await self._get("/xapi/v1/monitor/clients", {"macAddress": mac_colon})
        if data:
            items = data.get("data") or data.get("clients") or []
            if items:
                return items[0]

        # Try legacy per-MAC endpoint
        data = await self._get(f"/client/macaddr/{mac_colon}")
        if data:
            if isinstance(data, list):
                return data[0] if data else None
            return data

        return None
