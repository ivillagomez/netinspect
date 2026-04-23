from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from enum import Enum


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class TestStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"
    NA = "na"


class DeviceType(str, Enum):
    FIREWALL = "firewall"
    CISCO_SWITCH = "cisco_switch"
    RUCKUS_SWITCH = "ruckus_switch"
    RUCKUS_AP = "ruckus_ap"
    ARUBA_SWITCH = "aruba_switch"
    ARUBA_AP = "aruba_ap"
    EXTREME_SWITCH = "extreme_switch"
    EXTREME_AP = "extreme_ap"
    WIRELESS_CLIENT = "wireless_client"
    WIRED_CLIENT = "wired_client"
    UNKNOWN = "unknown"


class DiagnosticOptions(BaseModel):
    interface_status: bool = True
    error_counters: bool = True
    mtu_check: bool = True
    stp: bool = True
    poe: bool = True
    neighbor_info: bool = True
    wireless_info: bool = True
    system_logs: bool = True    # collect & display recent syslog entries per device


class Issue(BaseModel):
    severity: IssueSeverity
    category: str
    message: str
    detail: Optional[str] = None
    device: Optional[str] = None


class TestResult(BaseModel):
    name: str
    status: TestStatus
    value: Optional[str] = None
    message: str = ""
    detail: Optional[str] = None


class InterfaceStatus(BaseModel):
    name: str
    status: str = ""
    vlan: str = ""
    duplex: str = ""
    speed: str = ""
    port_type: str = ""


class InterfaceDetails(BaseModel):
    name: str
    description: str = ""
    mtu: int = 0
    duplex: str = ""
    speed: str = ""
    bandwidth_kbps: int = 0
    input_errors: int = 0
    output_errors: int = 0
    crc_errors: int = 0
    runts: int = 0
    giants: int = 0
    input_rate_bps: int = 0
    output_rate_bps: int = 0
    is_up: bool = False
    err_disabled: bool = False


class CDPNeighbor(BaseModel):
    local_port: str
    remote_device: str
    remote_port: str
    remote_ip: Optional[str] = None
    platform: str = ""
    capabilities: List[str] = []


class LLDPNeighbor(BaseModel):
    local_port: str
    remote_device: str
    remote_port: str
    remote_ip: Optional[str] = None
    system_description: str = ""


class STPPortInfo(BaseModel):
    vlan: int
    role: str
    state: str
    cost: int


class PoEStatus(BaseModel):
    admin: str = ""
    operational: str = ""
    power_watts: float = 0.0
    device: str = ""
    poe_class: str = ""
    max_watts: float = 0.0


class MACEntry(BaseModel):
    mac: str
    vlan: int
    port: str
    entry_type: str = ""


class Hop(BaseModel):
    order: int
    device_type: DeviceType
    device_name: str
    device_ip: Optional[str] = None
    vendor: str = ""
    model: str = ""
    software_version: str = ""
    # ingress = port where previous hop connects TO this device
    # egress  = port where this device connects TO next hop
    ingress_port: Optional[str] = None
    egress_port: Optional[str] = None
    vlan: Optional[int] = None
    interface_status: Optional[InterfaceStatus] = None
    interface_details: Optional[InterfaceDetails] = None
    cdp_neighbor: Optional[CDPNeighbor] = None
    lldp_neighbor: Optional[LLDPNeighbor] = None
    stp_info: Optional[List[STPPortInfo]] = None
    poe_status: Optional[PoEStatus] = None
    raw_data: Dict[str, Any] = {}
    issues: List[Issue] = []
    tests: List[TestResult] = []
    system_logs: List[Dict[str, str]] = []   # [{"severity": "CRIT|ERR|WARN", "message": "..."}]
    reachable: bool = True


class TraceResult(BaseModel):
    query: str
    resolved_mac: Optional[str] = None
    resolved_ip: Optional[str] = None
    resolved_fg_name: Optional[str] = None
    status: str = "success"
    path: List[Hop] = []
    all_issues: List[Issue] = []
    test_summary: List[TestResult] = []
    trace_time_ms: int = 0
    error: Optional[str] = None


class TraceRequest(BaseModel):
    query: str
    options: DiagnosticOptions = DiagnosticOptions()
