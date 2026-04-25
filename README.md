# NetInspect

Vendor-agnostic network path tracer and diagnostics platform. Enter a **MAC address**, **IP address**, or **FortiGate address object name** and get full end-to-end inspection across your firewall, switches, and wireless infrastructure — in your browser, no client install required.

![NetInspect](docs/screenshot.png)

---

## Quick Start

### Docker Compose _(recommended)_

```bash
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
docker compose up -d --build
```

Open **http://localhost:8080** → click **Settings** (top right) → add your devices → **Save**.

### Python (Windows / Linux)

```cmd
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
pip install -r requirements.txt
python run.py
```

> See [Deployment options](docs/deployment.md) for Unraid, Linux VM, and other setups.

---

## What It Does

- Resolves MAC / IP / FortiGate address name → full network path in a single query
- Traces **Firewall → Core Switch → Access Switch → AP → Device**, hop by hop
- Automated diagnostics: MTU, duplex, error counters, STP state, PoE, system logs
- Flags issues with **Critical / Warning** severity and pinpoints the source device
- All integrations are **optional** — configure only the vendors you have

---

## Supported Integrations

| Integration | Type | Protocol |
|---|---|---|
| **FortiGate** | Firewall | HTTPS REST + SSH |
| **Cisco** IOS / IOS-XE / NX-OS | Switch | SSH · SNMP (optional) · RESTCONF (optional) |
| **Aruba** AOS-S / AOS-CX | Switch | SSH · REST API (optional) |
| **Ruckus One** | Wireless cloud | HTTPS REST (OAuth2) |
| **Aruba Central** | Wireless + wired cloud | HTTPS REST (OAuth2) |
| **ExtremeCloud IQ** | Wireless cloud | HTTPS REST |

---

## Documentation

| Topic | Link |
|---|---|
| Deployment options | [docs/deployment.md](docs/deployment.md) |
| Configuration reference | [docs/configuration.md](docs/configuration.md) |
| Usage guide | [docs/usage.md](docs/usage.md) |
| Supported checks & diagnostics | [docs/diagnostics.md](docs/diagnostics.md) |
| Architecture & API reference | [docs/architecture.md](docs/architecture.md) |
| Troubleshooting | [docs/troubleshooting.md](docs/troubleshooting.md) |
| Security notes | [docs/security.md](docs/security.md) |
| Roadmap | [docs/roadmap.md](docs/roadmap.md) |

---

## License

[MIT](LICENSE) — © 2026 ivillagomez
