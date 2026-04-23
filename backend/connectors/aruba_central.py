"""
Aruba Central cloud API connector.

Auth: OAuth2 Client Credentials flow.
POST {base_url}/oauth2/token
  Form body: grant_type=client_credentials, client_id, client_secret, customer_id

Client lookup:
  GET {base_url}/monitoring/v2/clients?macaddr={mac}&client_type=WIRED
  GET {base_url}/monitoring/v2/clients?macaddr={mac}&client_type=WIRELESS
"""
import logging
import time
from typing import Optional, Dict, Any

import httpx

from backend.config import ArubaCentralConfig

logger = logging.getLogger(__name__)


class ArubaCentralClient:
    def __init__(self, config: ArubaCentralConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self._token: Optional[str] = None
        self._token_exp: float = 0.0

    async def _get_token(self) -> Optional[str]:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.post(
                    f"{self.base_url}/oauth2/token",
                    data={
                        "grant_type":    "client_credentials",
                        "client_id":     self.config.client_id,
                        "client_secret": self.config.client_secret,
                        "customer_id":   self.config.customer_id,
                    },
                )
                r.raise_for_status()
                body = r.json()
                self._token     = body.get("access_token")
                expires_in      = int(body.get("expires_in", 7200))
                self._token_exp = time.time() + expires_in
                return self._token
        except Exception as e:
            logger.warning("Aruba Central token exchange failed: %s", type(e).__name__)
            return None

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Optional[Any]:
        token = await self._get_token()
        if not token:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0) as c:
                r = await c.get(
                    f"{self.base_url}{path}",
                    params=params or {},
                    headers={"Authorization": f"Bearer {token}"},
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.debug("Aruba Central GET %s failed: %s", path, type(e).__name__)
            return None

    async def find_wired_client(self, norm_mac: str) -> Optional[Dict]:
        """Look up a wired client by normalized MAC (no separators).

        Returns the first matching client dict, or None.
        Key fields: name, ip_address, macaddr, associated_device,
                    associated_device_mac, interface_mac, vlan_id, connection_type
        """
        # Aruba Central expects colon-format MAC
        mac = ":".join(norm_mac[i:i+2] for i in range(0, 12, 2))
        data = await self._get("/monitoring/v2/clients", {"macaddr": mac, "client_type": "WIRED"})
        if not data:
            return None
        clients = data.get("clients") or data.get("result") or []
        return clients[0] if clients else None

    async def find_wireless_client(self, norm_mac: str) -> Optional[Dict]:
        """Look up a wireless client by normalized MAC.

        Key fields: name, ip_address, macaddr, associated_device (AP name),
                    network (SSID), radio_type, connection_type, vlan_id
        """
        mac = ":".join(norm_mac[i:i+2] for i in range(0, 12, 2))
        data = await self._get("/monitoring/v2/clients", {"macaddr": mac, "client_type": "WIRELESS"})
        if not data:
            return None
        clients = data.get("clients") or data.get("result") or []
        return clients[0] if clients else None
