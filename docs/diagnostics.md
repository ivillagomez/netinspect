# Supported Checks & Diagnostics

Each check can be individually enabled or disabled from the **Diagnostics options panel** in the UI (gear icon below the search bar).

---

## Per-hop checks — Cisco switches

| Check | What it detects | Severity |
|---|---|---|
| **Interface Status** | Port err-disabled, down, inactive | Critical |
| **Duplex** | Half-duplex (causes collisions and retransmits) | Warning |
| **Speed** | 10 Mbps (auto-negotiation failure) | Warning |
| **Error Counters** | CRC errors, input/output errors, runts, giants | Critical / Warning |
| **MTU** | Non-standard per-interface MTU; shows whether value is global default or per-interface override | Warning |
| **MTU Consistency** | Mismatch across path (causes fragmentation / silent drops) | Critical |
| **Spanning Tree** | Port in Blocking or transitional state | Warning |
| **PoE Status** | Power denied, fault, or near budget limit (>90%) | Critical / Warning |

---

## Per-hop checks — Aruba switches

| Check | What it detects | Severity |
|---|---|---|
| **Interface Status** | Port down or disabled | Critical |
| **Error Counters** | RX/TX errors on the client port | Warning |

---

## Uplink port counters

For every switch hop, error counters are also collected on the **uplink-facing port** toward upstream devices. This surfaces physical-layer errors on inter-switch links even when the upstream device is not SSH-accessible.

---

## Port-channel / LAG

When a MAC address is found on a **Port-channel** interface (`Po1`, `lag1`, etc.), the individual member link states are reported — showing which physical ports are bundled, down, or suspended.

### FortiGate LAG detection

When the FortiGate's egress port is itself a member of a Link Aggregation Group, the tool queries the parent aggregate interface for statistics. The UI displays the connection as **port → aggN (LAG)** in the interface stats section.

---

## FortiGate egress interface

When SSH credentials are configured for the FortiGate, the egress interface (the port where the traced device's traffic enters the firewall) is checked for RX/TX/error/drop counters via `diagnose netlink interface list`.

---

## Wireless checks — Ruckus R1 / Aruba Central

| Check | What it detects | Severity |
|---|---|---|
| **RSSI** | Signal below −75 dBm (poor wireless link) | Warning |
