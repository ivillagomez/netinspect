# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| v1.3.x (latest) | ✅ |
| v1.2.x | ⚠️ Security fixes only |
| < v1.2.0 | ❌ |

## Reporting a Vulnerability

**Please do not report security vulnerabilities via public GitHub issues.**

If you discover a security vulnerability, please report it privately:

1. Go to the [Security tab](https://github.com/ivillagomez/netinspect/security) → **"Report a vulnerability"**
2. Or email **ivanvt@hotmail.com** with the subject line `[NetInspect] Security Vulnerability`

Please include:
- A description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Any suggested mitigations (optional)

You will receive a response within **48 hours**. Once the issue is confirmed, a fix will be prioritized and a patched release published. You will be credited in the release notes unless you prefer to remain anonymous.

## Scope

The following are in scope:
- Authentication bypass or API key enumeration
- XSS, CSRF, or injection vulnerabilities in the web UI
- Path traversal or arbitrary file read/write via the API
- Credential leakage (config, logs, API responses)
- SSRF via the trace or discovery endpoints
- Docker image privilege escalation

The following are out of scope:
- Vulnerabilities requiring physical access to the host
- Vulnerabilities in third-party dependencies (report to the dependency maintainer directly; we track these via `pip-audit`)
- Social engineering or phishing

## Security Hardening

For details on the built-in security controls and hardening recommendations, see [docs/security.md](docs/security.md).
