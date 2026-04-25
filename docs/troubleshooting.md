# Troubleshooting

## Device not found

### "Could not resolve to a MAC address"
- Device may be offline — no ARP entry on any configured device
- If using an IP without FortiGate: ping the device first to refresh ARP caches, then trace
- If using a FortiGate address name: verify the name is exact and matches an address object in FortiGate

### "Device not located on any switch"
- Device may be behind an **unmanaged switch** not in the tool's list
- MAC may have aged out — check `show mac address-table aging-time` on Cisco switches
- Device may be on a VLAN not trunked to any configured switch

---

## Switch connectivity

### Cisco switch shows as "Unreachable"
- Verify SSH is enabled on the switch: `show ip ssh`
- Test connectivity from the server: `ssh <username>@<switch-ip>`
- Check no ACL is blocking SSH from the tool's IP
- Confirm credentials in Settings are correct (or that global `switch_credentials` is set)

### Aruba switch shows as "Unreachable"
- Confirm `os_type` matches your switch series (`aruba_os` for 2930/2930F/2930M, `aruba_osix` for 6000/6100)
- Test SSH from the server: `ssh <username>@<switch-ip>`
- Verify the account has read access to run `show` commands

### RESTCONF returns no data (Cisco)
- Confirm RESTCONF is enabled: `show restconf`
- Verify the switch is running IOS-XE 16.6 or later: `show version`
- Test manually: `curl -k -u <user>:<pass> https://<switch>/restconf/data/Cisco-IOS-XE-native:native/hostname`
- Ensure `restconf_verify_ssl: false` is set if the switch uses a self-signed certificate
- If RESTCONF is unreachable, the tool falls back silently to SSH data

### AOS-CX REST API returns no data (Aruba)
- Confirm the REST API is enabled: `show rest-api server` (should show running)
- Test manually: `curl -k -c cookies.txt -X POST https://<switch>/rest/v10.10/login -d '{"username":"...","password":"..."}'`
- Ensure `rest_verify_ssl: false` is set for self-signed certificates
- AOS-CX REST API requires firmware 10.08 or later
- If REST login fails, the tool falls back silently to SSH data

---

## FortiGate issues

### FortiGate API errors
- Verify `access_token` is correct and not expired
- Confirm the token's **Trusted Hosts** includes the tool server's IP
- Set `verify_ssl: false` if the FortiGate uses a self-signed certificate

### FortiGate SSH not working
- Confirm `ssh_username` and `ssh_password` are set in Settings
- Test manually: `ssh <username>@<fortigate-ip>`
- If SSH works but model info is missing, check logs — `get system status` output format may vary by firmware version

### FortiGate shows LAG port as "unknown"
- SSH credentials are required for LAG parent lookup (`diagnose netlink interface list`)
- The REST API alone does not expose LAG membership

---

## Cloud API issues

### Ruckus R1 returns no data
- Confirm `client_id` and `client_secret` are correct (from **Administration → Settings → Application Tokens**)
- Confirm `tenant_id` is set — find it in the portal URL after login: `asia.ruckus.cloud/<tenantId>/...`
- Verify the correct **Region** is selected in Settings (North America / Europe / Asia Pacific)

### Ruckus AP shows no wired uplink port
- Shown as `ETH0` (the universal Ruckus AP port) when the R1 API does not return an explicit port field. This is expected behavior.

### Aruba Central returns no data
- Verify `client_id`, `client_secret`, and `customer_id` are correct and that the token has read access
- Regenerate the token in **Account Home → API Gateway → System Apps & Tokens** if credentials have changed

### ExtremeCloud IQ returns no data
- Verify the `api_key` is correct — tokens can expire; regenerate from **Global Settings → API Token Management**
- Ensure the account has Operator role or higher (insufficient permissions return empty results)

---

## Settings and config

### Settings not saving
- Click **Save** and check for an error message below the Save button — if it says "Internal Server Error", check the server logs
- If running via Python directly: confirm the process has write permission to the project folder
- If running via Docker: the named volume (`netinspect_data`) is managed automatically — no manual config needed

### Port 8080 already in use
Open Settings → **Server** section → change the port to another value (e.g. `8090`) → Save → restart the server.

---

## Rate limits

### "429 Too Many Requests"
- The backend enforces rate limits: 30 traces/minute and 10 discovery requests/minute per IP
- Wait a moment before retrying — the rate-limit window slides every 60 seconds
