# Security Notes

## config.yaml is gitignored

`config.yaml` is listed in `.gitignore` and **must never be committed with real credentials**.
The `config.yaml.example` file in the repository contains only placeholder values.

When deploying:
1. Clone the repo
2. Start the server — it runs with all defaults if `config.yaml` is empty or absent
3. Open the Settings UI (top right) to enter credentials — they are saved automatically
4. `config.yaml` is never tracked by git

---

## Credential exposure in git history

> **Action required if making this repository public.**

If earlier development commits included real credentials before `.gitignore` was applied, and you intend to make this repo public:

1. **Rotate all credentials immediately:**
   - Generate a new FortiGate API token (System → Administrators)
   - Change the FortiGate SSH password
   - Change all switch SSH passwords
   - Regenerate Ruckus R1, Aruba Central, and ExtremeCloud IQ API keys

2. **Clean git history** with [BFG Repo Cleaner](https://rtyley.github.io/bfg-repo-cleaner/) or `git filter-repo`:
   ```bash
   bfg --replace-text passwords.txt netinspect.git
   git reflog expire --expire=now --all
   git gc --prune=now --aggressive
   git push --force
   ```

---

## Before exposing publicly (internet-facing)

If you plan to expose NetInspect outside a trusted private LAN, take these steps first:

1. **Set an API key** — Settings → Server → `api_key`. All API calls will require `X-API-Key: <your-key>`.
2. **Lock down CORS** — Settings → Server → `allowed_origins`, e.g. `["https://netinspect.mycompany.com"]`. The default `"*"` is safe on a private LAN but allows any website to make API requests when internet-facing. **Note: CORS changes require a process restart to take effect** (the middleware is initialised at startup).
3. **Put it behind a reverse proxy (nginx / Caddy / Traefik)** with TLS so credentials are encrypted in transit.
4. **Restrict the firewall** — only allow HTTPS inbound from your intended users.

---

## Optional API key for the web UI

Set `server.api_key` in Settings (→ **Server** section) to require an `X-API-Key` header on all backend API calls. Useful when the tool is exposed beyond a trusted LAN segment.

The `/api/capabilities`, `/api/health`, and `/api/ui-config` endpoints are always unauthenticated (they contain no credentials or sensitive data).

---

## Security hardening (active by default)

| Control | Description |
|---|---|
| XSS prevention | All dynamic HTML rendered via `esc()` escaping in the frontend |
| Timing-safe API key comparison | `hmac.compare_digest` prevents timing-based enumeration |
| SSH injection prevention | `_safe_port()` validates port values in all SSH connectors |
| Masked secrets in Settings API | Credentials returned as `••••••••`; masked values never written back to disk |
| Generic error messages | Exception handlers return generic messages with no credential context |
| Security response headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` |
| CORS lockdown | Set `server.allowed_origins` in Settings to restrict cross-origin access |
| Rate limiting | Sliding-window per IP: 30 traces/min, 10 discover/min; returns HTTP 429 |
| IP input validation | `seed_ip` validated with `ipaddress.ip_address()` (prevents SSRF) |
| Request body size limit | `PUT /api/settings` rejects bodies larger than 64 KB |
| Config file permissions check | Warns at startup if `config.yaml` is group- or world-readable |

---

## MFA / TACACS

Automated SSH via Netmiko is incompatible with interactive MFA (Duo push, TOTP, RSA token). MFA requires a human to respond mid-handshake; automated sessions hang waiting for a second factor.

**Recommended approach:** Create a dedicated service account (`svc-netinspect`) in your TACACS server that is MFA-exempt. Apply compensating controls:

- Read-only privilege level (`privilege 1` on Cisco, Operator on Aruba)
- Source IP restriction to the NetInspect server only
- Session logging enabled in TACACS for all connections from this account
- Quarterly access review

This is standard practice for all network automation tools (Ansible, NSO, SolarWinds, PRTG). The `switch_credentials` section is designed for exactly this service account pattern.

If your organization cannot exempt any account from MFA, alternatives include SNMP v3 (partially implemented via the optional SNMP fast-path) or per-switch REST APIs on modern IOS-XE and Aruba CX platforms.

---

## Minimum required permissions

| Device | Required access |
|---|---|
| FortiGate REST API | Read-only: Monitor, Network, Firewall |
| FortiGate SSH | Read-only admin (no config write needed) |
| Cisco switches (SSH) | Read-only SSH user (`privilege 1` is sufficient) |
| Cisco switches (RESTCONF) | Same account as SSH, or a dedicated HTTP-only account |
| Aruba switches (AOS-S, SSH) | Operator-level account (read-only show commands) |
| Aruba switches (AOS-CX, SSH) | Read-only role |
| Aruba switches (AOS-CX, REST) | Same account as SSH, or a dedicated REST-only account |
| Ruckus R1 | Read-only API token scoped to your venues |
| Aruba Central | Read-only API token (client and device read) |
| ExtremeCloud IQ | Read-only API key |

---

## Network access requirements

The server running NetInspect needs outbound access to:

| Destination | Port | When needed |
|---|---|---|
| FortiGate | 443 (HTTPS) | If FortiGate is configured |
| FortiGate | 22 (SSH) | If FortiGate SSH credentials are set |
| All Cisco/Aruba switches | 22 (SSH) | For configured switches |
| Cisco switches (RESTCONF) | 443 (HTTPS) | If `restconf_enabled: true` |
| Aruba switches (AOS-CX REST) | 443 (HTTPS) | If `rest_enabled: true` |
| `api.*.ruckus.cloud` | 443 (HTTPS) | If Ruckus R1 is configured |
| Aruba Central gateway | 443 (HTTPS) | If Aruba Central is configured |
| `extremecloudiq.com` | 443 (HTTPS) | If ExtremeCloud IQ is configured |

No inbound ports are needed other than `8080` for the web UI.
