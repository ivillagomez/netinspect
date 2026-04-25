# Deployment Options

> All options result in the same outcome: a web server on your LAN at `http://<server-ip>:8080`.
> Windows users just open a browser — no install needed on their machines.

---

## Option A — Windows (local)

Run directly on a Windows PC. Suitable for single-user or testing.

**Prerequisites:** [Python 3.11+](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install.

```cmd
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
pip install -r requirements.txt
python run.py
```

Open: **http://localhost:8080**

Click the **Settings** button (top right) to enter your device credentials. Changes are saved to `config.yaml` automatically.

To share with others on the LAN: `http://<your-windows-ip>:8080` — find your IP with `ipconfig`.

---

## Option B — Docker Compose (any platform)

```bash
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
docker compose up -d --build     # start
docker compose down              # stop
```

Open **http://localhost:8080** and use the Settings UI to configure credentials.

Config is stored in a named Docker volume (`netinspect_data`) — no manual file creation needed.

**PowerShell note:** Use `;` instead of `&&`:
```powershell
docker compose down; docker compose up -d --build
```

---

## Option C — Unraid Docker

24/7 access for everyone on the LAN.

**Prerequisites:** Unraid 6.9+ with Docker enabled.

```bash
# 1. Open Unraid Terminal (Tools → Terminal) or SSH in

# 2. Clone the repo
cd /mnt/user/appdata
git clone https://github.com/ivillagomez/netinspect.git

# 3. Build and start
cd netinspect
docker compose up -d --build

# 4. Verify it's running
docker ps | grep netinspect
```

Open from any LAN machine: **http://\<unraid-ip\>:8080**

#### Managing via Unraid Docker UI

After the image is built, you can manage it through the Unraid web UI (Docker tab → Add Container):

| Field | Value |
|---|---|
| Name | `netinspect` |
| Repository | `netinspect-tool:latest` |
| Network Type | `Bridge` |
| Port | Host `8080` → Container `8080` |
| Restart Policy | `Unless Stopped` |

---

## Option D — Linux VM with Docker

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh

# 2. Clone and start
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
docker compose up -d --build
```

Open **http://\<vm-ip\>:8080** and use the Settings UI to configure credentials.

---

## Updating

```bash
git pull
docker compose down; docker compose up -d --build
```

## Backing up config

Config lives in a Docker named volume. To export it:

```bash
docker exec netinspect-tool cat /app/data/config.yaml > config-backup.yaml
```

To restore on a new machine:

```bash
docker cp config-backup.yaml netinspect-tool:/app/data/config.yaml
docker restart netinspect-tool
```
