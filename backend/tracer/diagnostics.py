from typing import List, Tuple
from backend.models import (
    Issue, IssueSeverity, TestResult, TestStatus, DiagnosticOptions,
    InterfaceDetails, InterfaceStatus, STPPortInfo, PoEStatus, Hop,
)


def _pass(name: str, value: str = "", msg: str = "") -> TestResult:
    return TestResult(name=name, status=TestStatus.PASS, value=value, message=msg)


def _fail(name: str, value: str = "", msg: str = "", detail: str = None) -> TestResult:
    return TestResult(name=name, status=TestStatus.FAIL, value=value, message=msg, detail=detail)


def _warn(name: str, value: str = "", msg: str = "", detail: str = None) -> TestResult:
    return TestResult(name=name, status=TestStatus.WARNING, value=value, message=msg, detail=detail)


def _skip(name: str) -> TestResult:
    return TestResult(name=name, status=TestStatus.SKIP, message="Skipped (disabled in options)")


# ------------------------------------------------------------------
# Per-check functions  →  (issues, tests)
# ------------------------------------------------------------------

def check_port_state(details: InterfaceDetails) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []
    if details.err_disabled:
        iss = Issue(
            severity=IssueSeverity.CRITICAL, category="port_state",
            message=f"Port {details.name} is err-disabled",
            detail="Check for port-security violations, BPDU guard, or storm control triggers",
        )
        issues.append(iss)
        tests.append(_fail("Port State", "err-disabled", iss.message, iss.detail))
    elif not details.is_up:
        iss = Issue(severity=IssueSeverity.CRITICAL, category="port_state",
                    message=f"Port {details.name} is down")
        issues.append(iss)
        tests.append(_fail("Port State", "down", iss.message))
    else:
        tests.append(_pass("Port State", "up"))
    return issues, tests


def check_error_counters(details: InterfaceDetails) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []

    if details.crc_errors > 100:
        iss = Issue(severity=IssueSeverity.CRITICAL, category="errors",
                    message=f"High CRC errors: {details.crc_errors}",
                    detail="Usually caused by a bad cable, faulty SFP, or duplex mismatch")
        issues.append(iss)
        tests.append(_fail("CRC Errors", str(details.crc_errors), iss.message, iss.detail))
    elif details.crc_errors > 0:
        iss = Issue(severity=IssueSeverity.WARNING, category="errors",
                    message=f"CRC errors present: {details.crc_errors}")
        issues.append(iss)
        tests.append(_warn("CRC Errors", str(details.crc_errors), iss.message))
    else:
        tests.append(_pass("CRC Errors", "0"))

    if details.input_errors > 1000:
        iss = Issue(severity=IssueSeverity.WARNING, category="errors",
                    message=f"High input errors: {details.input_errors}")
        issues.append(iss)
        tests.append(_warn("Input Errors", str(details.input_errors), iss.message))
    else:
        tests.append(_pass("Input Errors", str(details.input_errors)))

    if details.output_errors > 100:
        iss = Issue(severity=IssueSeverity.WARNING, category="errors",
                    message=f"Output errors: {details.output_errors}",
                    detail="May indicate congestion or duplex mismatch")
        issues.append(iss)
        tests.append(_warn("Output Errors", str(details.output_errors), iss.message, iss.detail))
    else:
        tests.append(_pass("Output Errors", str(details.output_errors)))

    if details.runts > 50:
        iss = Issue(severity=IssueSeverity.WARNING, category="errors",
                    message=f"Runts: {details.runts}",
                    detail="Short frames — often caused by duplex mismatch or bad NIC")
        issues.append(iss)
        tests.append(_warn("Runts", str(details.runts), iss.message, iss.detail))
    else:
        tests.append(_pass("Runts", str(details.runts)))

    if details.giants > 10:
        iss = Issue(severity=IssueSeverity.WARNING, category="errors",
                    message=f"Giants: {details.giants}",
                    detail="Oversized frames — possible MTU misconfiguration")
        issues.append(iss)
        tests.append(_warn("Giants", str(details.giants), iss.message, iss.detail))
    else:
        tests.append(_pass("Giants", str(details.giants)))

    return issues, tests


def check_mtu(details: InterfaceDetails) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []
    if details.mtu and details.mtu not in (0, 1500):
        iss = Issue(severity=IssueSeverity.WARNING, category="mtu",
                    message=f"Non-standard MTU: {details.mtu} bytes",
                    detail="Expected 1500 (or 9000/9216 for jumbo frames). Verify MTU consistency across path.")
        issues.append(iss)
        tests.append(_warn("MTU", str(details.mtu), iss.message, iss.detail))
    else:
        tests.append(_pass("MTU", f"{details.mtu} bytes" if details.mtu else "1500 bytes"))
    return issues, tests


def check_interface_status(status: InterfaceStatus) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []

    if status.status == "err-disabled":
        iss = Issue(severity=IssueSeverity.CRITICAL, category="port_state",
                    message=f"Port {status.name} is err-disabled")
        issues.append(iss)
        tests.append(_fail("Interface Status", "err-disabled", iss.message))
    elif status.status in ("notconnect", "disabled", "inactive"):
        iss = Issue(severity=IssueSeverity.CRITICAL, category="port_state",
                    message=f"Port {status.name} is {status.status}")
        issues.append(iss)
        tests.append(_fail("Interface Status", status.status, iss.message))
    else:
        tests.append(_pass("Interface Status", status.status or "connected"))

    if status.duplex and "half" in status.duplex.lower():
        iss = Issue(severity=IssueSeverity.WARNING, category="duplex",
                    message=f"Port {status.name} is half-duplex",
                    detail="Half-duplex on modern networks causes collisions and high error rates")
        issues.append(iss)
        tests.append(_warn("Duplex", status.duplex, iss.message, iss.detail))
    else:
        tests.append(_pass("Duplex", status.duplex or "full"))

    if (status.duplex and "a-" not in status.duplex.lower()
            and status.speed and "a-" not in status.speed.lower()
            and ("10m" in status.speed.lower() or status.speed in ("10", "10M"))):
        iss = Issue(severity=IssueSeverity.WARNING, category="speed",
                    message=f"Port {status.name} operating at 10 Mbps",
                    detail="Possible negotiation failure or very old NIC")
        issues.append(iss)
        tests.append(_warn("Speed", status.speed, iss.message, iss.detail))
    else:
        tests.append(_pass("Speed", status.speed or "auto"))

    return issues, tests


def check_stp(port: str, stp_list: List[STPPortInfo]) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []
    for stp in stp_list:
        if stp.state.lower() in ("blk", "blocking"):
            iss = Issue(severity=IssueSeverity.WARNING, category="stp",
                        message=f"VLAN {stp.vlan} port {port} is STP Blocking",
                        detail="Traffic blocked by Spanning Tree — expected on redundant links but investigate if primary path")
            issues.append(iss)
            tests.append(_warn(f"STP VLAN {stp.vlan}", stp.state.upper(), iss.message, iss.detail))
        elif stp.state.lower() in ("lis", "listening", "lrn", "learning"):
            iss = Issue(severity=IssueSeverity.INFO, category="stp",
                        message=f"VLAN {stp.vlan} port {port} is STP {stp.state.upper()} — transitioning")
            issues.append(iss)
            tests.append(_warn(f"STP VLAN {stp.vlan}", stp.state.upper(), iss.message))
        else:
            tests.append(_pass(f"STP VLAN {stp.vlan}", stp.state.upper()))
    return issues, tests


def check_poe(port: str, poe: PoEStatus) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []
    if poe.operational.lower() in ("power-deny", "deny", "fault"):
        iss = Issue(severity=IssueSeverity.CRITICAL, category="poe",
                    message=f"PoE denied/fault on {port}: {poe.operational}",
                    detail="Device may not have power — check PSU budget or force PoE class")
        issues.append(iss)
        tests.append(_fail("PoE Status", poe.operational, iss.message, iss.detail))
    elif poe.max_watts and poe.power_watts and poe.power_watts >= poe.max_watts * 0.9:
        iss = Issue(severity=IssueSeverity.WARNING, category="poe",
                    message=f"PoE near limit on {port}: {poe.power_watts}W / {poe.max_watts}W")
        issues.append(iss)
        tests.append(_warn("PoE Power", f"{poe.power_watts}W", iss.message))
    else:
        tests.append(_pass("PoE Status", poe.operational or "on"))
    return issues, tests


def check_mtu_consistency(hops: List[Hop]) -> Tuple[List[Issue], List[TestResult]]:
    issues, tests = [], []
    mtus = [
        (h.device_name, h.interface_details.mtu)
        for h in hops
        if h.interface_details and h.interface_details.mtu > 0
    ]
    if len(mtus) < 2:
        return issues, tests
    values = set(m for _, m in mtus)
    if len(values) > 1:
        detail = ", ".join(f"{name}={mtu}" for name, mtu in mtus)
        iss = Issue(severity=IssueSeverity.CRITICAL, category="mtu",
                    message="MTU mismatch across path", detail=detail)
        issues.append(iss)
        tests.append(_fail("MTU Consistency", "MISMATCH", iss.message, detail))
    else:
        tests.append(_pass("MTU Consistency", f"{list(values)[0]} bytes"))
    return issues, tests


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def run_all_checks(
    hops: List[Hop],
    options: DiagnosticOptions = None,
) -> Tuple[List[Issue], List[TestResult]]:
    if options is None:
        options = DiagnosticOptions()

    all_issues: List[Issue] = []
    all_tests: List[TestResult] = []

    for hop in hops:
        hop_tests: List[TestResult] = []

        if options.interface_status:
            if hop.interface_status:
                iss, tsts = check_interface_status(hop.interface_status)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
            if hop.interface_details:
                iss, tsts = check_port_state(hop.interface_details)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
        else:
            hop_tests.append(_skip("Interface Status"))

        if options.error_counters:
            if hop.interface_details:
                iss, tsts = check_error_counters(hop.interface_details)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
        else:
            hop_tests.append(_skip("Error Counters"))

        if options.mtu_check:
            if hop.interface_details:
                iss, tsts = check_mtu(hop.interface_details)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
        else:
            hop_tests.append(_skip("MTU"))

        if options.stp:
            if hop.stp_info and hop.ingress_port:
                iss, tsts = check_stp(hop.ingress_port, hop.stp_info)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
        else:
            hop_tests.append(_skip("STP"))

        if options.poe:
            if hop.poe_status and hop.ingress_port:
                iss, tsts = check_poe(hop.ingress_port, hop.poe_status)
                hop.issues.extend(iss)
                hop_tests.extend(tsts)
        else:
            hop_tests.append(_skip("PoE"))

        all_issues.extend(hop.issues)
        hop.tests = hop_tests
        all_tests.extend(hop_tests)

    if options.mtu_check:
        iss, tsts = check_mtu_consistency(hops)
        all_issues.extend(iss)
        all_tests.extend(tsts)

    return all_issues, all_tests
