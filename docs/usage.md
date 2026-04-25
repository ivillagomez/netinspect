# Usage Guide

## Searching

Type any of the following in the search bar and press **Enter** or click **Trace**:

```
aa:bb:cc:dd:ee:ff       MAC — colon-separated
aa-bb-cc-dd-ee-ff       MAC — dash-separated
aabb.ccdd.eeff          MAC — Cisco/Ruckus dotted format
192.168.1.55            IP address
Server-Web-01           FortiGate address object name (only when FortiGate is configured)
```

Results appear in 5–20 seconds depending on the number of switches and their response times. SSH connections are pooled and reused across traces, significantly reducing latency on back-to-back queries.

### IP address lookup without FortiGate

When no FortiGate is configured and an IP address is entered, the tool performs a **two-pass ARP resolution**:

1. All configured switches are queried to collect their full ARP tables
2. The ARP tables are searched for the entered IP to resolve it to a MAC
3. All switches are re-queried with the discovered MAC to locate the device
4. If no switch ARP table contains the IP, the result is "not found"

---

## Diagnostics Options

Click the **gear icon** below the search bar to expand the diagnostics panel. Toggle individual checks on or off before running a trace:

| Option | What it runs |
|---|---|
| **Interface Status** | Port up/down, duplex, speed |
| **Error Counters** | CRC, input/output errors, runts, giants |
| **MTU Check** | Per-interface MTU vs. global; cross-hop consistency |
| **Spanning Tree** | Role and state per port |
| **PoE Status** | Power delivery and budget |
| **Neighbor Info** | Per-port CDP/LLDP connected device name and port |
| **System Logs** | Recent error/warning syslog entries (`show logging`) |

Disabling options speeds up traces and reduces SSH commands sent to switches.

---

## Settings UI

Click the **Settings** button in the top-right header to open the Settings modal. Settings are organized into accordion sections:

| Section | What you can configure |
|---|---|
| **Switch Authentication** | Global TACACS username and password shared across all SSH switches |
| **Discover from Seed** | Start a CDP/LLDP BFS walk from a seed IP to auto-find switches |
| **Cisco Switches** | Add, edit, or remove Cisco switch inventory rows |
| **Aruba Switches** | Add, edit, or remove Aruba switch inventory rows |
| **FortiGate** | Host, API token, optional SSH credentials |
| **Cloud APIs** | Ruckus One, Aruba Central, and ExtremeCloud IQ credentials |
| **Server** | Port, optional API key, allowed CORS origins |

Click **Save** to write all changes immediately. Masked credential fields (shown as `••••••••`) are preserved from disk — they are never overwritten with the placeholder.

### CDP/LLDP Auto-Discovery

1. Open Settings → **Discover from Seed**
2. Enter a seed IP (typically your core switch), scope CIDR (e.g. `10.0.0.0/8`), and max depth
3. Click **Start Discovery** — the panel streams live progress with depth-indented device names
4. Use the **Stop** button to cancel at any time
5. Discovered devices appear in a checklist — select the ones you want and click **Add selected to inventory**
6. Selected switches are added to the Cisco or Aruba lists without duplicates
7. Click **Save** to write the updated inventory

The discovery engine walks CDP neighbors first, falls back to LLDP, and skips APs, routers, and firewalls from recursion. It uses `switch_credentials` for all SSH connections during the walk.

---

## Reading Results

**Path visualization** — left to right: Firewall → switches → (AP) → device
- Port labels between nodes show the physical connection (e.g. `Gi1/0/24 → Gi0/1`)
- When a FortiGate port is a LAG member, the label shows `port → aggN (LAG)`
- A colored dot on a node = problems found (red = critical, amber = warning)

**Issues Found** — each issue shows:
- Severity badge (Critical / Warning / Info)
- **Device name** where the issue was found
- Message and detail with recommended action

**Diagnostic Tests** — pass/fail/warning summary across all hops.

**Hop detail cards** — expand any card for:
- Vendor, model, software version, IP
- Ingress and egress physical ports, interface status, error counters, MTU
- CDP/LLDP neighbor, STP state, PoE power
- Port-channel member link states
- FortiGate egress interface statistics (when SSH is configured)
- Data source indicator (SSH / RESTCONF / REST API) per hop

---

## Export CSV

Click **Export CSV** in the export bar (below the summary bar) to download a spreadsheet.

The CSV contains:
- **One row per hop** — device name, type, IP, vendor, model, software version, VLAN, ingress/egress ports, reachable status, semicolon-joined issues, and per-hop test counts
- **Issues appendix** — all issues listed with severity, device, message, and detail

File is saved as `netinspect_<query>_<timestamp>.csv` with a UTF-8 BOM so Excel opens it directly.

---

## Print / PDF

Click **Print / PDF** in the export bar to open the browser print dialog. Choose **Save as PDF**.

The print stylesheet removes UI chrome, forces all hop detail cards open, and applies print-safe colours. Chrome's "Save as PDF" produces the cleanest output.

---

## Trace History

The **Recent Traces** panel stores up to 20 traces in `localStorage` — no server required.

| Control | Action |
|---|---|
| Click panel header | Expand / collapse the list |
| **↩ Load** | Re-render a past trace instantly (no network query) |
| **Clear** | Remove all stored history |

Each entry shows a status icon, the original query, hop count, resolved IP and MAC, and timestamp. History persists across browser sessions and is local to the browser — not shared across LAN users.

---

## Theme

Click the **sun/moon button in the footer** to toggle between dark and light themes. The preference persists across sessions via `localStorage`.

---

## Vendor Chips

The header shows chips for each configured integration (FortiGate, Cisco, Aruba, Ruckus, etc.). If an integration is not configured, its chip does not appear.

After a trace completes, the **summary bar** shows a **vendor path** — color-coded chips representing the sequence of vendors traversed (e.g. **Fortinet → Cisco → Ruckus ICX → Cisco**). Consecutive hops from the same vendor are collapsed into a single chip.
