import yaml
import os
from typing import List, Optional
from pydantic import BaseModel


class FortiGateConfig(BaseModel):
    host: str
    port: int = 443
    access_token: str
    verify_ssl: bool = True
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: int = 22


class CiscoSwitchConfig(BaseModel):
    name: str
    host: str
    username: str
    password: str
    device_type: str = "cisco_ios"
    timeout: int = 30
    # SNMP — optional fast path (replaces SSH for MAC lookup + interface stats)
    snmp_community: Optional[str] = None   # None = SNMP disabled
    snmp_port: int = 161
    snmp_version: str = "2c"               # "1" or "2c"


class RuckusR1Config(BaseModel):
    base_url: str
    # OAuth2 client credentials (from portal: Administration → Settings → Application Tokens)
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    # Tenant ID — visible in the portal URL after login: asia.ruckus.cloud/<tenantId>/...
    # Required for token exchange: POST https://asia.ruckus.cloud/oauth2/token/{tenantId}
    tenant_id: Optional[str] = None
    # Legacy: static Bearer token / direct JWT (used if client_id not set)
    api_key: Optional[str] = None


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    api_key: Optional[str] = None


class ArubaSwitchConfig(BaseModel):
    name: str
    host: str
    username: str
    password: str
    os_type: str = "aruba_os"   # "aruba_os" (2930/2930F/2930M) | "aruba_osix" (6000/6100)
    timeout: int = 30


class ArubaCentralConfig(BaseModel):
    base_url: str = "https://apigw-prod2.central.arubanetworks.com"
    client_id: str
    client_secret: str
    customer_id: str             # tenant ID — required for token scope


class ExtremeIQConfig(BaseModel):
    base_url: str = "https://extremecloudiq.com"
    api_key: Optional[str] = None        # static API key via X-Auth-Token header
    client_id: Optional[str] = None      # OAuth2 alternative
    client_secret: Optional[str] = None  # OAuth2 alternative


class AppConfig(BaseModel):
    # All sections are optional — only configure what you have
    fortigate:      Optional[FortiGateConfig]    = None   # None = no firewall / switch-only mode
    cisco_switches: List[CiscoSwitchConfig]      = []     # SSH-managed Cisco IOS/IOS-XE switches
    aruba_switches: List[ArubaSwitchConfig]      = []     # SSH-managed Aruba AOS-S/CX switches
    ruckus_r1:      Optional[RuckusR1Config]     = None   # Ruckus One cloud API
    aruba_central:  Optional[ArubaCentralConfig] = None   # Aruba Central cloud API
    extreme_iq:     Optional[ExtremeIQConfig]    = None   # ExtremeCloud IQ cloud API
    server: ServerConfig = ServerConfig()


_config: Optional[AppConfig] = None


def load_config(path: str = "config.yaml") -> AppConfig:
    global _config
    if _config is not None:
        return _config
    # Allow override via environment variable (useful for Docker / CI)
    env_path = os.environ.get("NETWORK_TRACER_CONFIG")
    if env_path:
        path = env_path
    # Search order: absolute path → cwd → script directory → /app (Docker)
    candidates = [path] if os.path.isabs(path) else [
        os.path.join(os.getcwd(), path),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), path),
        os.path.join("/app", path),
    ]
    config_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not config_path:
        raise FileNotFoundError(
            f"config.yaml not found. Searched: {candidates}\n"
            "Copy config.yaml to the project root and fill in your credentials."
        )
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _config = AppConfig(**data)
    return _config


def get_config() -> AppConfig:
    if _config is None:
        return load_config()
    return _config
