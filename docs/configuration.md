# Configuration Reference

The easiest way to configure the tool is via the **Settings UI** (gear icon, top right) — credentials are written to `config.yaml` automatically on Save. Alternatively, edit `config.yaml` directly (copy `config.yaml.example` as a starting point).

`config.yaml` is **excluded from git** (see [security notes](security.md)).

All top-level sections except `server` are optional. The tool starts and functions correctly with an empty or absent `config.yaml`.

---

## Full Example

```yaml
# ── Global Switch Credentials (optional) ─────────────────────────────────────
switch_credentials:
  username: "svc-netinspect"
  password: "YOUR_TACACS_PASSWORD"
  device_type: "cisco_ios"   # default Netmiko driver for discovered switches
  timeout: 30

# ── FortiGate (optional) ─────────────────────────────────────────────────────
fortigate:
  host: "192.168.1.1"
  port: 443
  access_token: "YOUR_API_TOKEN"
  verify_ssl: false
  ssh_username: "YOUR_SSH_USERNAME"
  ssh_password: "YOUR_SSH_PASSWORD"
  ssh_port: 22

# ── Cisco Switches (optional) ─────────────────────────────────────────────────
cisco_switches:
  - name: "SW-Core"
    host: "192.168.1.x"
    device_type: "cisco_ios"
    timeout: 30
    # snmp_community: "public"           # optional SNMP fast-path
    # restconf_enabled: true             # enable RESTCONF for IOS-XE 16.6+

# ── Aruba Switches (optional) ─────────────────────────────────────────────────
aruba_switches:
  - name: "Aruba-Core"
    host: "192.168.1.x"
    os_type: "aruba_os"    # "aruba_os" (2930/2930F/2930M) or "aruba_osix" (6000/6100)
    timeout: 30
    # rest_enabled: true                 # enable AOS-CX REST API

# ── Ruckus One (optional) ─────────────────────────────────────────────────────
ruckus_r1:
  # base_url is set automatically by the Region selector in the Settings UI.
  # If editing config.yaml directly, use one of:
  #   https://api.ruckus.cloud          (North America)
  #   https://api.eu.ruckus.cloud       (Europe)
  #   https://api.asia.ruckus.cloud     (Asia Pacific)
  base_url: "https://api.ruckus.cloud"
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  tenant_id: "YOUR_TENANT_ID"

# ── Aruba Central (optional) ──────────────────────────────────────────────────
aruba_central:
  # base_url is fixed — set automatically by the Settings UI.
  base_url: "https://apigw-prod2.central.arubanetworks.com"
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  customer_id: "YOUR_CUSTOMER_ID"

# ── ExtremeCloud IQ (optional) ────────────────────────────────────────────────
extreme_iq:
  # base_url is fixed — set automatically by the Settings UI.
  base_url: "https://extremecloudiq.com"
  api_key: "YOUR_API_KEY"

# ── Web Server ────────────────────────────────────────────────────────────────
server:
  host: "0.0.0.0"
  port: 8080
  api_key: ""             # optional: require X-API-Key header on all API calls
  allowed_origins: []     # blank = allow all; restrict for non-LAN deployments
```

---

## Global Switch Credentials

The `switch_credentials` section defines a single username and password shared across all SSH switches. Any switch that does **not** have its own `username`/`password` set will use these at runtime.

When RESTCONF or AOS-CX REST API are enabled without dedicated credentials, the global `switch_credentials` are also used for those HTTP API connections automatically.

This is the recommended pattern when all switches share a single TACACS service account.

---

## FortiGate

| Field | Required | Description |
|---|---|---|
| `host` | Yes | IP or hostname of the FortiGate |
| `port` | No (default 443) | HTTPS API port |
| `access_token` | No | REST API token (required for ARP/address lookups) |
| `verify_ssl` | No (default true) | Set `false` for self-signed certificates |
| `ssh_username` | No | SSH username (required for error counters + platform info) |
| `ssh_password` | No | SSH password |
| `ssh_port` | No (default 22) | SSH port |

### Getting a FortiGate API token

1. Log in to FortiGate web UI
2. Go to **System → Administrators → Create New → REST API Admin**
3. Name it `netinspect`, PKI Group: none
4. Under **Trusted Hosts**, add the IP of the machine running this tool
5. Copy the generated token → paste as `access_token`

The token only needs **read-only** access (Monitor, Network, Firewall).

### FortiGate SSH

When SSH credentials are set, the tool also retrieves:
- Device model, version, and serial number
- RX/TX/error/drop counters on the egress interface (including LAG parent aggregates)

If left blank, the tool falls back to REST API data (less detail, no error counters).

---

## Cisco Switches

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Display name |
| `host` | Yes | IP or hostname |
| `username` | No | SSH username (inherits from `switch_credentials` if omitted) |
| `password` | No | SSH password (inherits from `switch_credentials` if omitted) |
| `device_type` | No (default `cisco_ios`) | Netmiko driver |
| `timeout` | No (default 30) | SSH command timeout in seconds |
| `snmp_community` | No | Enables SNMP fast-path for MAC table + IF-MIB stats |
| `restconf_enabled` | No (default false) | Enables RESTCONF parallel queries (IOS-XE 16.6+) |

### `device_type` values

| Platform | device_type |
|---|---|
| Catalyst 2960, 3650, 3850, 9200, 9300 | `cisco_ios` |
| Catalyst 9000 with IOS-XE | `cisco_xe` |
| Nexus switches | `cisco_nxos` |

### SNMP fast-path (optional)

When `snmp_community` is set, the tool uses SNMP to collect MAC table entries and interface statistics concurrently with SSH, reducing trace time on larger environments.

### RESTCONF fast-path (optional)

When `restconf_enabled: true` is set, RESTCONF queries run **in parallel with SSH**. RESTCONF results take precedence for: hostname, software version, MAC table, ARP, CDP/LLDP, interface stats. SSH still handles STP, PoE, MTU, etherchannel, and logs.

**Requirements:** IOS-XE 16.6+, `restconf` global config enabled on the switch, HTTPS reachable on port 443.

```yaml
cisco_switches:
  - name: "SW-Core-XE"
    host: "192.168.1.x"
    device_type: "cisco_xe"
    timeout: 30
    restconf_enabled: true
    restconf_port: 443
    restconf_verify_ssl: false
```

---

## Aruba Switches

| Field | Required | Description |
|---|---|---|
| `name` | Yes | Display name |
| `host` | Yes | IP or hostname |
| `username` | No | SSH username (inherits from `switch_credentials` if omitted) |
| `password` | No | SSH password (inherits from `switch_credentials` if omitted) |
| `os_type` | No (default `aruba_os`) | Switch series |
| `timeout` | No (default 30) | SSH command timeout in seconds |
| `rest_enabled` | No (default false) | Enables AOS-CX REST API (6000/6100 only) |

### `os_type` values

| Aruba Series | os_type |
|---|---|
| 2930F, 2930M (ArubaOS-S) | `aruba_os` |
| 6000, 6100 (ArubaOS-CX) | `aruba_osix` |

### AOS-CX REST API (optional)

When `rest_enabled: true` is set, REST queries run **in parallel with SSH**. REST results take precedence for: hostname, MAC table, ARP, LLDP neighbors, interface stats.

**Requirements:** AOS-CX 10.08+, REST API enabled (default on AOS-CX), HTTPS reachable on port 443.

```yaml
aruba_switches:
  - name: "Aruba-6100"
    host: "192.168.1.x"
    os_type: "aruba_osix"
    rest_enabled: true
    rest_verify_ssl: false
```

---

## Ruckus One

1. Log in to the Ruckus One portal (`asia.ruckus.cloud` or your regional URL)
2. Go to **Administration → Settings → Application Tokens**
3. Create a new token → copy the **Client ID** and **Client Secret**
4. Your **Tenant ID** is in the portal URL after login: `asia.ruckus.cloud/<tenantId>/...`
5. In Settings, select your **Region** (North America / Europe / Asia Pacific) — the API URL is set automatically.

Tokens are fetched automatically via OAuth2 and cached for ~2 hours.

---

## Aruba Central

1. Log in to Aruba Central (`central.arubanetworks.com` or your regional URL)
2. Go to **Account Home → API Gateway → System Apps & Tokens**
3. Create a new token → copy the **Client ID** and **Client Secret**
4. Your **Customer ID** is under **Account Settings → Customer ID** or visible in the portal URL
Tokens are fetched and refreshed automatically via OAuth2. The API endpoint is fixed and set automatically by the Settings UI.

---

## ExtremeCloud IQ

1. Log in to ExtremeCloud IQ (`extremecloudiq.com`)
2. Go to **Global Settings → API Token Management**
3. Generate a new API Key → copy it as `api_key`

Tokens can expire — regenerate from Global Settings if the integration stops returning data.

---

## Server

| Field | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Bind address (0.0.0.0 = all interfaces) |
| `port` | `8080` | HTTP port |
| `api_key` | _(none)_ | Optional: require `X-API-Key` header on all API calls |
| `allowed_origins` | `[]` (allow all) | Restrict CORS for non-LAN deployments |
