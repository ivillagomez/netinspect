import httpx
import logging
import re
from typing import Optional, List, Dict, Any

from backend.config import FortiGateConfig

logger = logging.getLogger(__name__)


def normalize_mac(mac: str) -> str:
    """Normalize MAC to lowercase, no separators: aabbccddeeff"""
    return re.sub(r"[.:\-]", "", mac).lower()


def mac_to_colon(mac: str) -> str:
    m = normalize_mac(mac)
    return ":".join(m[i : i + 2] for i in range(0, 12, 2))


class FortiGateClient:
    def __init__(self, config: FortiGateConfig):
        self.config = config
        self.base_url = f"https://{config.host}:{config.port}/api/v2"
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                verify=self.config.verify_ssl,
                timeout=15.0,
                headers={"Authorization": f"Bearer {self.config.access_token}"},
            )
        return self._client

    async def _get(self, path: str, params: Dict[str, Any] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            r = await self._get_client().get(url, params=params or {})
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"FortiGate GET {path} failed: {e}")
            return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # --- Address resolution ---

    async def resolve_address_name(self, name: str) -> Optional[str]:
        """Resolve a FortiGate address object name to its IP/subnet."""
        data = await self._get(f"/cmdb/firewall/address/{name}")
        if not data:
            return None
        result = data.get("results", [])
        if not result:
            return None
        obj = result[0] if isinstance(result, list) else result
        subnet = obj.get("subnet", "")
        if subnet:
            ip = subnet.split()[0].strip()
            return ip if ip != "0.0.0.0" else None
        fqdn = obj.get("fqdn", "")
        return fqdn if fqdn else None

    async def search_address_names(self, query: str) -> List[Dict]:
        """Search address objects by name prefix."""
        data = await self._get("/cmdb/firewall/address", {"filter": f"name=@{query}"})
        if not data:
            return []
        return data.get("results", [])

    # --- ARP table ---

    async def get_arp_table(self) -> List[Dict]:
        data = await self._get("/monitor/network/arp")
        if not data:
            return []
        return data.get("results", [])

    async def get_ip_for_mac(self, mac: str) -> Optional[str]:
        norm = normalize_mac(mac)
        for entry in await self.get_arp_table():
            entry_mac = normalize_mac(entry.get("mac", ""))
            if entry_mac == norm:
                return entry.get("ip")
        return None

    async def get_mac_for_ip(self, ip: str) -> Optional[str]:
        for entry in await self.get_arp_table():
            if entry.get("ip") == ip:
                raw = entry.get("mac", "")
                return mac_to_colon(raw) if raw else None
        return None

    async def get_arp_entry(self, mac: str = None, ip: str = None) -> Optional[Dict]:
        """Return full ARP entry matching MAC or IP."""
        norm_mac = normalize_mac(mac) if mac else None
        for entry in await self.get_arp_table():
            if norm_mac and normalize_mac(entry.get("mac", "")) == norm_mac:
                return entry
            if ip and entry.get("ip") == ip:
                return entry
        return None

    # --- Interfaces ---

    async def get_interfaces(self) -> List[Dict]:
        data = await self._get("/monitor/system/interface")
        if not data:
            return []
        return data.get("results", {}).values() if isinstance(data.get("results"), dict) else data.get("results", [])

    async def get_interface_for_ip(self, ip: str) -> Optional[str]:
        """Find which FG interface the IP belongs to (for ARP entry context)."""
        for entry in await self.get_arp_table():
            if entry.get("ip") == ip:
                return entry.get("interface")
        return None

    # --- Policies ---

    async def get_policies(self) -> List[Dict]:
        data = await self._get("/cmdb/firewall/policy")
        if not data:
            return []
        return data.get("results", [])

    async def get_policies_for_ip(self, ip: str) -> List[Dict]:
        """Find firewall policies where the IP appears as source or destination."""
        matching = []
        for policy in await self.get_policies():
            src_addrs = [a.get("name", "") for a in policy.get("srcaddr", [])]
            dst_addrs = [a.get("name", "") for a in policy.get("dstaddr", [])]
            if any(ip in a for a in src_addrs + dst_addrs):
                matching.append(policy)
        return matching

    # --- System info ---

    async def get_system_status(self) -> Optional[Dict]:
        data = await self._get("/monitor/system/status")
        return data.get("results") if data else None

    async def get_hostname(self) -> str:
        status = await self.get_system_status()
        if status:
            return status.get("hostname", "FortiGate")
        return "FortiGate"

    async def get_platform_info(self) -> Dict:
        """Return {model, version, serial} from system status."""
        status = await self.get_system_status()
        if not status:
            return {}
        return {
            "model": status.get("model_name") or status.get("model") or "",
            "version": status.get("version") or status.get("branch_pt") or "",
            "serial": status.get("serial") or status.get("serial_number") or "",
        }
