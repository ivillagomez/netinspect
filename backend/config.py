import yaml
import os
from typing import List, Optional
from pydantic import BaseModel


class SwitchCredentials(BaseModel):
    """Global SSH credentials shared across all switches (e.g. a TACACS service account).
    Per-switch username / password override these when explicitly set."""
    username: str = ""
    password: str = ""
    device_type: str = "cisco_ios"   # default Netmiko driver for new discovered switches
    timeout: int = 30


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
    # username / password may be omitted when switch_credentials provides a global fallback
    username: Optional[str] = None
    password: Optional[str] = None
    device_type: str = "cisco_ios"
    timeout: int = 30
    # SNMP — optional fast path (replaces SSH for MAC lookup + interface stats)
    snmp_community: Optional[str] = None   # None = SNMP disabled
    snmp_port: int = 161
    snmp_version: str = "2c"               # "1" or "2c"
    # RESTCONF — REST alternative to SSH for IOS-XE 16.6+ / Catalyst 9000 series
    restconf_enabled: bool = False
    restconf_port: int = 443
    restconf_verify_ssl: bool = True
    restconf_username: Optional[str] = None   # None → use username / global creds
    restconf_password: Optional[str] = None   # None → use password / global creds


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
    # Restrict CORS to specific origins for non-LAN deployments.
    # Empty list (default) = allow all origins ("*") — fine for a trusted LAN.
    # Example: ["http://192.168.1.50:8080", "http://netinspect.internal"]
    allowed_origins: List[str] = []


class ArubaSwitchConfig(BaseModel):
    name: str
    host: str
    # username / password may be omitted when switch_credentials provides a global fallback
    username: Optional[str] = None
    password: Optional[str] = None
    os_type: str = "aruba_os"   # "aruba_os" (2930/2930F/2930M) | "aruba_osix" (6000/6100)
    timeout: int = 30
    # REST API — alternative to SSH for Aruba CX (AOS-CX 10.x)
    rest_enabled: bool = False
    rest_port: int = 443
    rest_verify_ssl: bool = True
    rest_username: Optional[str] = None
    rest_password: Optional[str] = None


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
    fortigate:          Optional[FortiGateConfig]    = None   # None = no firewall / switch-only mode
    switch_credentials: Optional[SwitchCredentials] = None   # shared TACACS / global SSH creds
    cisco_switches:     List[CiscoSwitchConfig]      = []     # SSH-managed Cisco IOS/IOS-XE switches
    aruba_switches:     List[ArubaSwitchConfig]      = []     # SSH-managed Aruba AOS-S/CX switches
    ruckus_r1:          Optional[RuckusR1Config]     = None   # Ruckus One cloud API
    aruba_central:      Optional[ArubaCentralConfig] = None   # Aruba Central cloud API
    extreme_iq:         Optional[ExtremeIQConfig]    = None   # ExtremeCloud IQ cloud API
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


def _find_config_path(path: str = "config.yaml") -> Optional[str]:
    """Return the resolved path to config.yaml, or None if not found."""
    env_path = os.environ.get("NETWORK_TRACER_CONFIG")
    if env_path:
        return env_path if os.path.isfile(env_path) else None
    candidates = [path] if os.path.isabs(path) else [
        os.path.join(os.getcwd(), path),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), path),
        os.path.join("/app", path),
    ]
    return next((p for p in candidates if os.path.isfile(p)), None)


def save_config(cfg: AppConfig, path: str = "config.yaml") -> None:
    """Persist an AppConfig back to the YAML file it was loaded from."""
    config_path = _find_config_path(path)
    if not config_path:
        raise FileNotFoundError(
            "config.yaml not found — cannot save. "
            "Ensure the file exists at the project root."
        )
    # Exclude None optional sections so the YAML stays clean
    data = cfg.model_dump(exclude_none=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                  sort_keys=False)


T = type  # used by fill_switch_creds below


def fill_switch_creds(sw_cfg, global_creds: Optional[SwitchCredentials]):
    """Return sw_cfg with username/password back-filled from global_creds where blank.

    Fills both the SSH fields (username/password) and any API fields
    (restconf_username/password for Cisco, rest_username/password for Aruba)
    that are not already set.

    Does NOT mutate the original; returns a new model instance only when changes
    are needed so callers can detect whether override happened.
    """
    if not global_creds:
        return sw_cfg
    data = sw_cfg.model_dump()
    changed = False

    # SSH credentials
    if not data.get("username"):
        data["username"] = global_creds.username
        changed = True
    if not data.get("password"):
        data["password"] = global_creds.password
        changed = True

    # RESTCONF credentials (Cisco only — ArubaSwitchConfig doesn't have these keys)
    if "restconf_username" in data and not data.get("restconf_username"):
        data["restconf_username"] = global_creds.username
        changed = True
    if "restconf_password" in data and not data.get("restconf_password"):
        data["restconf_password"] = global_creds.password
        changed = True

    # REST credentials (Aruba only)
    if "rest_username" in data and not data.get("rest_username"):
        data["rest_username"] = global_creds.username
        changed = True
    if "rest_password" in data and not data.get("rest_password"):
        data["rest_password"] = global_creds.password
        changed = True

    if not changed:
        return sw_cfg
    return type(sw_cfg)(**data)


def reset_config() -> None:
    """Clear the cached singleton. Next call to load_config() re-reads from disk."""
    global _config
    _config = None
