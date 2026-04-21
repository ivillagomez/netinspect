import re
import logging
from dataclasses import dataclass
from typing import Optional

from backend.connectors.fortigate import FortiGateClient, normalize_mac, mac_to_colon

logger = logging.getLogger(__name__)

MAC_RE = re.compile(
    r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$"          # aa:bb:cc:dd:ee:ff  or aa-bb-...
    r"|^([0-9a-f]{4}\.){2}[0-9a-f]{4}$"             # aaaa.bbbb.cccc
    r"|^[0-9a-f]{12}$",                              # aabbccddeeff
    re.IGNORECASE,
)
IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


@dataclass
class Resolution:
    mac: Optional[str] = None          # normalized aa:bb:cc:dd:ee:ff
    ip: Optional[str] = None
    fg_name: Optional[str] = None
    input_type: str = "unknown"        # mac | ip | fg_name


async def resolve(query: str, fg: FortiGateClient) -> Resolution:
    query = query.strip()
    res = Resolution()

    if MAC_RE.match(query):
        res.input_type = "mac"
        res.mac = mac_to_colon(query)
        res.ip = await fg.get_ip_for_mac(res.mac)
        return res

    if IP_RE.match(query):
        res.input_type = "ip"
        res.ip = query
        res.mac = await fg.get_mac_for_ip(query)
        if res.mac:
            res.mac = mac_to_colon(res.mac)
        return res

    # Treat as FortiGate address name
    res.input_type = "fg_name"
    res.fg_name = query
    ip = await fg.resolve_address_name(query)
    if ip:
        res.ip = ip
        res.mac = await fg.get_mac_for_ip(ip)
        if res.mac:
            res.mac = mac_to_colon(res.mac)
    else:
        # Try searching address objects
        candidates = await fg.search_address_names(query)
        if candidates:
            obj = candidates[0]
            subnet = obj.get("subnet", "")
            if subnet:
                res.ip = subnet.split()[0].strip()
                res.mac = await fg.get_mac_for_ip(res.ip)
                if res.mac:
                    res.mac = mac_to_colon(res.mac)

    return res
