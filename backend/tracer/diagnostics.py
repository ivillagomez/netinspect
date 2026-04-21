from typing import List
from backend.models import Issue, IssueSeverity, InterfaceDetails, InterfaceStatus, STPPortInfo, PoEStatus, Hop


def check_interface_details(details: InterfaceDetails) -> List[Issue]:
    issues = []

    if details.err_disabled:
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="port_state",
            message=f"Port {details.name} is err-disabled",
            detail="Check for port-security violations, BPDU guard, or storm control triggers",
        ))
    elif not details.is_up:
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="port_state",
            message=f"Port {details.name} is down",
        ))

    if details.mtu and details.mtu not in (0, 1500):
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="mtu",
            message=f"Non-standard MTU: {details.mtu} bytes",
            detail="Expected 1500 (or 9000/9216 for jumbo frames). Verify MTU consistency across path.",
        ))

    if details.crc_errors > 100:
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="errors",
            message=f"High CRC errors: {details.crc_errors}",
            detail="Usually caused by a bad cable, faulty SFP, or duplex mismatch",
        ))
    elif details.crc_errors > 0:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="errors",
            message=f"CRC errors present: {details.crc_errors}",
        ))

    if details.input_errors > 1000:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="errors",
            message=f"High input errors: {details.input_errors}",
        ))

    if details.output_errors > 100:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="errors",
            message=f"Output errors: {details.output_errors}",
            detail="May indicate congestion or duplex mismatch",
        ))

    if details.runts > 50:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="errors",
            message=f"Runts: {details.runts}",
            detail="Short frames — often caused by duplex mismatch or bad NIC",
        ))

    if details.giants > 10:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="errors",
            message=f"Giants: {details.giants}",
            detail="Oversized frames — possible MTU misconfiguration",
        ))

    return issues


def check_interface_status(status: InterfaceStatus) -> List[Issue]:
    issues = []

    if status.status == "err-disabled":
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="port_state",
            message=f"Port {status.name} is err-disabled",
        ))
    elif status.status in ("notconnect", "disabled", "inactive"):
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="port_state",
            message=f"Port {status.name} is {status.status}",
        ))

    if status.duplex and "half" in status.duplex.lower():
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="duplex",
            message=f"Port {status.name} is half-duplex",
            detail="Half-duplex on modern networks causes collisions and high error rates",
        ))

    if status.duplex and "a-" not in status.duplex.lower() and status.speed and "a-" not in status.speed.lower():
        if "10m" in status.speed.lower() or status.speed in ("10", "10M"):
            issues.append(Issue(
                severity=IssueSeverity.WARNING,
                category="speed",
                message=f"Port {status.name} operating at 10 Mbps",
                detail="Possible negotiation failure or very old NIC",
            ))

    return issues


def check_stp(port: str, stp_list: List[STPPortInfo]) -> List[Issue]:
    issues = []
    for stp in stp_list:
        if stp.state.lower() in ("blk", "blocking"):
            issues.append(Issue(
                severity=IssueSeverity.WARNING,
                category="stp",
                message=f"VLAN {stp.vlan} port {port} is STP Blocking",
                detail="Traffic blocked by Spanning Tree — expected on redundant links but investigate if this is the primary path",
            ))
        if stp.state.lower() in ("lis", "listening", "lrn", "learning"):
            issues.append(Issue(
                severity=IssueSeverity.INFO,
                category="stp",
                message=f"VLAN {stp.vlan} port {port} is STP {stp.state.upper()} — transitioning",
            ))
    return issues


def check_poe(port: str, poe: PoEStatus) -> List[Issue]:
    issues = []
    if poe.operational.lower() in ("power-deny", "deny", "fault"):
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="poe",
            message=f"PoE denied/fault on {port}: {poe.operational}",
            detail="Device may not have power — check PSU budget or force PoE class",
        ))
    if poe.max_watts and poe.power_watts and poe.power_watts >= poe.max_watts * 0.9:
        issues.append(Issue(
            severity=IssueSeverity.WARNING,
            category="poe",
            message=f"PoE near limit on {port}: {poe.power_watts}W / {poe.max_watts}W",
        ))
    return issues


def check_mtu_consistency(hops: List[Hop]) -> List[Issue]:
    """Cross-hop MTU mismatch check."""
    issues = []
    mtus = [
        (h.device_name, h.interface_details.mtu)
        for h in hops
        if h.interface_details and h.interface_details.mtu > 0
    ]
    if len(mtus) < 2:
        return issues
    values = set(m for _, m in mtus)
    if len(values) > 1:
        detail = ", ".join(f"{name}={mtu}" for name, mtu in mtus)
        issues.append(Issue(
            severity=IssueSeverity.CRITICAL,
            category="mtu",
            message="MTU mismatch across path",
            detail=detail,
        ))
    return issues


def run_all_checks(hops: List[Hop]) -> List[Issue]:
    all_issues: List[Issue] = []
    for hop in hops:
        if hop.interface_status:
            hop.issues.extend(check_interface_status(hop.interface_status))
        if hop.interface_details:
            hop.issues.extend(check_interface_details(hop.interface_details))
        if hop.stp_info and hop.ingress_port:
            hop.issues.extend(check_stp(hop.ingress_port, hop.stp_info))
        if hop.poe_status and hop.ingress_port:
            hop.issues.extend(check_poe(hop.ingress_port, hop.poe_status))
        all_issues.extend(hop.issues)

    all_issues.extend(check_mtu_consistency(hops))
    return all_issues
