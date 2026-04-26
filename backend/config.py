import yaml
import os
import logging
from typing import List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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
    access_token: Optional[str] = None   # None = SSH-only mode (no REST API)
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
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    customer_id: Optional[str] = None    # tenant ID — required for token scope


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
        # No config file found — start with all defaults.
        # User can configure via the Settings UI; first Save will create the file.
        logger.info(
            "No config.yaml found — starting with default configuration. "
            "Open the Settings UI to configure your devices and credentials."
        )
        _config = AppConfig()
        return _config
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}   # empty file → empty dict → all defaults
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
    """Persist an AppConfig back to the YAML file it was loaded from.
    If no config.yaml exists yet, creates one at the NETWORK_TRACER_CONFIG path
    (if set) or at the project root.

    Writes atomically (temp file → fsync → rename) and enforces 0600 permissions
    so the credential-bearing file is never world- or group-readable.
    """
    import tempfile
    import stat

    config_path = _find_config_path(path)
    if not config_path:
        # First save — respect env var (e.g. Docker named-volume path) before
        # falling back to the project root next to backend/.
        env_path = os.environ.get("NETWORK_TRACER_CONFIG")
        if env_path:
            config_path = env_path
            parent = os.path.dirname(config_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        else:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(project_root, path)
        logger.info("Creating new config.yaml at %s", config_path)

    # Exclude None optional sections so the YAML stays clean
    data = cfg.model_dump(exclude_none=True)
    content = yaml.dump(data, default_flow_style=False, allow_unicode=True,
                        sort_keys=False)

    # Atomic write: write to a temp file in the same directory, fsync, then
    # rename so readers never see a partial file.
    config_dir = os.path.dirname(os.path.abspath(config_path)) or "."
    try:
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)   # 0600
            os.replace(tmp_path, config_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError:
        # Fallback for platforms where mkstemp/replace is not atomic (e.g. cross-device)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(config_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass


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


def _get_profiles_dir() -> str:
    """Return the profiles directory (sibling to config.yaml), creating it if needed.

    Profiles are YAML snapshots of AppConfig stored in  <config_dir>/profiles/
    Each file is named  <profile_name>.yaml  and written with 0600 permissions.
    """
    config_path = _find_config_path()
    if config_path:
        config_dir = os.path.dirname(os.path.abspath(config_path))
    else:
        # No config.yaml yet — mirror the logic in save_config() so profiles end
        # up next to wherever the first save will create config.yaml.
        env_path = os.environ.get("NETWORK_TRACER_CONFIG")
        if env_path:
            config_dir = os.path.dirname(os.path.abspath(env_path))
        else:
            config_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    profiles_dir = os.path.join(config_dir, "profiles")
    os.makedirs(profiles_dir, exist_ok=True)
    return profiles_dir
