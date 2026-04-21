import yaml
import os
from typing import List, Optional
from pydantic import BaseModel


class FortiGateConfig(BaseModel):
    host: str
    port: int = 443
    access_token: str
    verify_ssl: bool = False


class CiscoSwitchConfig(BaseModel):
    name: str
    host: str
    username: str
    password: str
    device_type: str = "cisco_ios"
    timeout: int = 30


class RuckusR1Config(BaseModel):
    base_url: str
    api_key: str


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080


class AppConfig(BaseModel):
    fortigate: FortiGateConfig
    cisco_switches: List[CiscoSwitchConfig]
    ruckus_r1: RuckusR1Config
    server: ServerConfig = ServerConfig()


_config: Optional[AppConfig] = None


def load_config(path: str = "config.yaml") -> AppConfig:
    global _config
    if _config is not None:
        return _config
    config_path = path if os.path.isabs(path) else os.path.join(os.getcwd(), path)
    with open(config_path, "r") as f:
        data = yaml.safe_load(f)
    _config = AppConfig(**data)
    return _config


def get_config() -> AppConfig:
    if _config is None:
        return load_config()
    return _config
