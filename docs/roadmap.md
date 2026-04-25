# Roadmap

## Done

| Feature |
|---|
| FortiGate + Cisco + Ruckus R1 path trace |
| Chain-walk topology (handles non-SSH intermediate switches) |
| Vendor / model / software version per hop |
| MTU / duplex / error / STP / PoE diagnostics |
| Selectable diagnostic options per trace |
| Per-test pass/fail summary panel |
| Physical port connections between hops |
| FortiGate SSH egress interface stats |
| FortiGate LAG (aggregate) member detection |
| Port-channel / LAG member link status (Cisco) |
| Ruckus switch port enrichment from R1 |
| Ruckus AP ETH0 uplink fallback + firmware field variants |
| `show ip arp` + `show mac address-table` for richer discovery |
| Issues panel with source device attribution |
| Docker / Unraid deployment |
| Optional SNMP fast path for Cisco switches (MAC + IF-MIB stats) |
| Aruba switch support — AOS-S (2930/2930F/2930M) and AOS-CX (6000/6100) |
| Aruba Central cloud API integration (wired + wireless) |
| ExtremeCloud IQ cloud API integration |
| Fully modular / vendor-agnostic config (all sections optional) |
| Two-pass ARP resolution from switches (no FortiGate required) |
| `/api/capabilities` endpoint for UI adaptation |
| Dark/light theme toggle with localStorage persistence |
| System Logs diagnostic option (`show logging`) |
| Dynamic versioning via VERSION file + `/api/ui-config` |
| Web-based Settings UI (gear icon, accordion sections, save to config.yaml) |
| Global switch credentials (`switch_credentials`) with per-switch override |
| CDP/LLDP Auto-Discovery (BFS walk, SSE progress stream, add to inventory) |
| Security hardening (XSS, timing-safe key compare, SSH injection, CSP headers) |
| Vendor path chips in summary bar (color-coded, deduplicated) |
| SSH connection pooling (reuse connections across concurrent traces) |
| RESTCONF fast-path for Cisco IOS-XE 16.6+ (parallel with SSH) |
| AOS-CX REST API fast-path for Aruba 6000/6100 (parallel with SSH) |
| Rate limiting (30/min trace, 10/min discover, per IP, sliding window) |
| IP input validation + request body size limit (SSRF / DoS prevention) |
| Config file permission warning at startup |
| Export trace to CSV (per-hop rows + issues appendix) |
| Print / PDF via browser print stylesheet |
| Trace history (localStorage, up to 20 entries, instant reload) |
| "No devices configured" banner with direct link to Settings |

## Planned

| Feature |
|---|
| Saved trace history — comparison / diff between two traces |
| FortiAnalyzer log correlation |
| Email / Teams alert on critical issues |
| Palo Alto firewall support |
