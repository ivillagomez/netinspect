import asyncio
import collections
import hmac
import ipaddress
import json
import logging
import os
import stat
import time as _time
from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.config import (
    load_config, save_config, reset_config, _find_config_path,
    AppConfig, FortiGateConfig, CiscoSwitchConfig, ArubaSwitchConfig,
    RuckusR1Config, ArubaCentralConfig, ExtremeIQConfig,
    ServerConfig, SwitchCredentials,
)
from backend.discovery.cdp_lldp import discover_from_seed
from backend.models import TraceRequest, TraceResult
from backend.tracer.mac_tracer import NetworkTracer

# ── Settings helpers ───────────────────────────────────────────────────────────

_MASKED = "••••••••"   # placeholder returned by GET /api/settings for set secrets


def _mask(val) -> str | None:
    """Return the mask sentinel if val is set, else None."""
    return _MASKED if val else None


def _merge_secret(submitted, current):
    """Resolve a secret field coming from PUT /api/settings.
    - If user sent back the mask  → keep current (unchanged)
    - If user sent empty / None   → clear (delete)
    - Otherwise                   → use the new value
    """
    if submitted == _MASKED:
        return current
    if not submitted:
        return None
    return submitted

# ── Rate limiter ───────────────────────────────────────────────────────────────

class _RateLimiter:
    """Sliding-window per-IP rate limiter (no external dependencies).

    Default: 30 requests per 60-second window.
    Returns True if the request is allowed, False if over limit.
    """
    def __init__(self, max_calls: int = 30, window: int = 60):
        self._max  = max_calls
        self._win  = window
        self._calls: dict = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> bool:
        async with self._lock:
            now = _time.monotonic()
            q   = self._calls.setdefault(key, collections.deque())
            while q and q[0] < now - self._win:
                q.popleft()
            if len(q) >= self._max:
                return False
            q.append(now)
            return True


_trace_limiter    = _RateLimiter(max_calls=30, window=60)   # /api/trace
_discover_limiter = _RateLimiter(max_calls=10, window=60)   # /api/discover


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="NetInspect", version="1.0.0")

_config = None
_tracer: NetworkTracer = None
_trace_semaphore = asyncio.Semaphore(5)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
_index_html   = os.path.join(_frontend_dir, "index.html")


# ── SPA middleware ─────────────────────────────────────────────────────────────
# For GET requests that aren't API or static-file paths, serve index.html so the
# React/JS router can handle client-side navigation.  This replaces the greedy
# /{full_path:path} catch-all route which Starlette would match before specific
# API routes.
class SPAMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (
            response.status_code == 404
            and request.method == "GET"
            and not path.startswith("/api/")
            and not path.startswith("/static/")
            and os.path.isfile(_index_html)
        ):
            logger.debug("SPA fallback: %s → index.html", path)
            return FileResponse(_index_html)
        return response

app.add_middleware(SPAMiddleware)


# ── Security headers ───────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Self-hosted SPA: allow inline styles/scripts (no CDN deps needed)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "object-src 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Default: allow all origins ("*") — safe for a trusted private LAN.
# Set server.allowed_origins in config.yaml to lock down before exposing publicly.
try:
    _cors_origins: list = load_config().server.allowed_origins or ["*"]
except Exception:
    _cors_origins = ["*"]   # config not yet present at build time (Docker, CI)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_tracer() -> NetworkTracer:
    global _config, _tracer
    if _tracer is None:
        _config = load_config()
        _tracer = NetworkTracer(_config)
    return _tracer


async def verify_api_key(key: str = Security(_api_key_header)):
    """If server.api_key is configured, require it via X-API-Key header.
    Uses hmac.compare_digest() for constant-time comparison to prevent timing attacks.
    """
    cfg = load_config()
    if not cfg.server.api_key:
        return  # auth disabled — open access
    # key may be None if header is absent; treat as empty string for safe comparison
    provided = key or ""
    if not hmac.compare_digest(provided, cfg.server.api_key):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")


@app.on_event("startup")
async def startup():
    logger.info("NetInspect starting up...")
    try:
        get_tracer()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Startup config error: {e}")

    # ── Config file permission check ───────────────────────────────────────────
    try:
        cfg_path = _find_config_path()
        if cfg_path and os.path.isfile(cfg_path):
            mode = os.stat(cfg_path).st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                logger.warning(
                    "SECURITY: config.yaml at %s is readable by group/other "
                    "(permissions: %s).  Run: chmod 600 %s",
                    cfg_path, oct(mode & 0o777), cfg_path,
                )
    except Exception as e:
        logger.debug("Permission check skipped: %s", e)


@app.on_event("shutdown")
async def shutdown():
    try:
        from backend.connectors.ssh_pool import _pool
        _pool.close_all()
    except Exception:
        pass
    logger.info("NetInspect shut down")


# ── API routes ─────────────────────────────────────────────────────────────────

@app.post("/api/trace", response_model=TraceResult, dependencies=[Depends(verify_api_key)])
async def trace(http_request: Request, request: TraceRequest):
    # Rate limiting — per client IP
    client_ip = http_request.client.host if http_request.client else "unknown"
    if not await _trace_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — max 30 traces per minute")

    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    if len(request.query) > 256:
        raise HTTPException(status_code=400, detail="Query too long")
    tracer = get_tracer()
    try:
        async with _trace_semaphore:
            result = await tracer.trace(request.query.strip(), request.options)
        return result
    except Exception as e:
        logger.error(f"Trace error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Trace failed — check server logs")


@app.get("/api/devices", dependencies=[Depends(verify_api_key)])
async def list_devices():
    """Return configured device names for status overview."""
    try:
        cfg = load_config()
        return {
            "fortigate":      {"name": "FortiGate"} if cfg.fortigate else None,
            "cisco_switches": [{"name": sw.name} for sw in cfg.cisco_switches],
            "aruba_switches": [{"name": sw.name} for sw in cfg.aruba_switches],
            "ruckus_r1":      {"name": "Ruckus One"} if cfg.ruckus_r1 else None,
        }
    except Exception as e:
        logger.error(f"Devices listing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load device list")


@app.get("/api/capabilities")
async def capabilities():
    """Non-sensitive capability flags — tells the frontend which integrations are active.
    No auth required: used at page load before the user enters an API key.
    """
    try:
        cfg = load_config()
        return {
            "fortigate":      bool(cfg.fortigate),
            "cisco_switches": len(cfg.cisco_switches),
            "aruba_switches": len(cfg.aruba_switches),
            "ruckus_r1":      bool(cfg.ruckus_r1),
            "aruba_central":  bool(cfg.aruba_central),
            "extreme_iq":     bool(cfg.extreme_iq),
        }
    except Exception as e:
        logger.error(f"Capabilities error: {e}", exc_info=True)
        return {
            "fortigate": False, "cisco_switches": 0, "aruba_switches": 0,
            "ruckus_r1": False, "aruba_central": False, "extreme_iq": False,
        }


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/r1/test", dependencies=[Depends(verify_api_key)])
async def r1_test():
    """Probe Ruckus One API and return sanitized diagnostics (no tokens or response bodies)."""
    logger.info("R1 test endpoint called")
    tracer = get_tracer()
    raw = await tracer.r1.test_connection()

    # Strip all sensitive fields before returning to the caller:
    #  - token_prefix  (partial JWT — still useful to an attacker)
    #  - probe response body snippets (may contain partial token data or server internals)
    #  - any error strings that might include OAuth details
    safe: dict = {
        "base_url":              raw.get("base_url"),
        "auth_mode":             raw.get("auth_mode"),
        "tenant_id_configured":  raw.get("tenant_id_configured"),
        "token_obtained":        raw.get("token_obtained"),
    }

    # Include per-probe HTTP status codes and redirect locations only — no response bodies
    raw_probes = raw.get("probes") or {}
    safe["probes"] = {
        url: {k: v for k, v in probe.items() if k in ("status", "location", "error")}
        for url, probe in raw_probes.items()
    }
    # Sanitize probe "error" fields too (they can contain full exception text)
    for probe in safe["probes"].values():
        if "error" in probe:
            probe["error"] = "Connection error — see server logs"

    # Include GET/POST venue probe status codes (no snippets)
    for key in ("GET /venues", "POST /venues/aps/query"):
        if key in raw:
            entry = raw[key]
            safe[key] = {"status": entry.get("status")} if "status" in entry else {"error": "probe failed"}

    if raw.get("error"):
        safe["error"] = raw["error"]

    return safe


@app.post("/api/discover", dependencies=[Depends(verify_api_key)])
async def discover(request: Request):
    """Stream CDP/LLDP discovery progress as Server-Sent Events.

    Request body:
      seed_ip     str    — starting device IP
      scope       str    — comma-separated CIDRs (blank = allow all)
      max_depth   int    — recursion depth limit (default 5)
      protocol    str    — "ssh" | "snmp" | "both"  (default "ssh")
      credentials object — {username, password, device_type, timeout}
                           SSH only; falls back to switch_credentials from config.
      snmp        object — {community, port, version}
                           SNMP only; community defaults to "public".
    """
    # Rate limiting — per client IP
    client_ip = request.client.host if request.client else "unknown"
    if not await _discover_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — max 10 discoveries per minute")

    body = await request.json()

    seed_ip   = (body.get("seed_ip") or "").strip()
    scope_raw = (body.get("scope")   or "").strip()
    max_depth = min(int(body.get("max_depth", 5)), 10)
    scope     = [s.strip() for s in scope_raw.split(",") if s.strip()] if scope_raw else []
    protocol  = (body.get("protocol") or "ssh").strip().lower()
    if protocol not in ("ssh", "snmp", "both"):
        protocol = "ssh"

    if not seed_ip:
        raise HTTPException(status_code=400, detail="seed_ip is required")

    # Validate seed_ip is a real IP address (prevents SSRF via hostname injection)
    try:
        ipaddress.ip_address(seed_ip)
    except ValueError:
        raise HTTPException(status_code=400, detail="seed_ip must be a valid IPv4 or IPv6 address")

    # ── SSH credentials ────────────────────────────────────────────────────────
    username = password = device_type = ""
    timeout  = 15
    if protocol in ("ssh", "both"):
        creds_body = body.get("credentials") or {}
        if creds_body.get("username") and creds_body.get("password"):
            username    = creds_body["username"]
            password    = creds_body["password"]
            device_type = creds_body.get("device_type", "cisco_ios")
            timeout     = int(creds_body.get("timeout", 15))
        else:
            cfg = load_config()
            gc  = cfg.switch_credentials
            if not gc or not gc.username or not gc.password:
                if protocol == "ssh":
                    raise HTTPException(
                        status_code=400,
                        detail="No SSH credentials provided and no switch_credentials configured."
                    )
                # "both" with no SSH creds → degrade to SNMP only
                protocol = "snmp"
            else:
                username    = gc.username
                password    = gc.password
                device_type = gc.device_type or "cisco_ios"
                timeout     = gc.timeout or 15

    # ── SNMP credentials ───────────────────────────────────────────────────────
    snmp_body      = body.get("snmp") or {}
    snmp_community = (snmp_body.get("community") or "public").strip()
    snmp_port      = int(snmp_body.get("port", 161))
    snmp_version   = (snmp_body.get("version") or "2c").strip()

    async def event_stream():
        try:
            async for event in discover_from_seed(
                seed_ip        = seed_ip,
                username       = username,
                password       = password,
                device_type    = device_type,
                scope          = scope,
                max_depth      = max_depth,
                timeout        = timeout,
                protocol       = protocol,
                snmp_community = snmp_community,
                snmp_port      = snmp_port,
                snmp_version   = snmp_version,
            ):
                yield event.to_sse()
                await asyncio.sleep(0)   # yield control so client receives events promptly
        except Exception as exc:
            logger.error("Discovery error: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'ip': seed_ip, 'reason': 'server error'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx response buffering
        },
    )


def _read_version() -> str:
    """Read the VERSION file from the project root. Falls back to 'unknown'."""
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION"),
        os.path.join(os.getcwd(), "VERSION"),
        "/app/VERSION",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
    return "unknown"


@app.get("/api/settings", dependencies=[Depends(verify_api_key)])
async def get_settings():
    """Return current config with all secrets masked. Safe to show in the UI."""
    cfg = load_config()
    d = cfg.model_dump()

    # ── FortiGate ──────────────────────────────────────────────────────────────
    if d.get("fortigate"):
        d["fortigate"]["access_token"] = _mask(cfg.fortigate.access_token)
        d["fortigate"]["ssh_password"]  = _mask(cfg.fortigate.ssh_password)

    # ── Global switch credentials ──────────────────────────────────────────────
    if d.get("switch_credentials") and d["switch_credentials"].get("password"):
        d["switch_credentials"]["password"] = _MASKED

    # ── Cisco switches ─────────────────────────────────────────────────────────
    for sw in d.get("cisco_switches", []):
        if sw.get("password"):
            sw["password"] = _MASKED

    # ── Aruba switches ─────────────────────────────────────────────────────────
    for sw in d.get("aruba_switches", []):
        if sw.get("password"):
            sw["password"] = _MASKED

    # ── Cloud: Ruckus One ──────────────────────────────────────────────────────
    if d.get("ruckus_r1"):
        r1 = cfg.ruckus_r1
        d["ruckus_r1"]["client_secret"] = _mask(r1.client_secret)
        d["ruckus_r1"]["api_key"]        = _mask(r1.api_key)

    # ── Cloud: Aruba Central ───────────────────────────────────────────────────
    if d.get("aruba_central"):
        d["aruba_central"]["client_secret"] = _mask(cfg.aruba_central.client_secret)

    # ── Cloud: ExtremeCloud IQ ─────────────────────────────────────────────────
    if d.get("extreme_iq"):
        xiq = cfg.extreme_iq
        d["extreme_iq"]["api_key"]       = _mask(xiq.api_key)
        d["extreme_iq"]["client_secret"] = _mask(xiq.client_secret)

    # ── Server ─────────────────────────────────────────────────────────────────
    if d.get("server", {}).get("api_key"):
        d["server"]["api_key"] = _MASKED

    return d


@app.put("/api/settings", dependencies=[Depends(verify_api_key)])
async def put_settings(request: Request):
    """Save updated config. Fields set to the mask sentinel are preserved from disk."""
    # Body size guard — prevents very large payloads from being parsed
    body_bytes = await request.body()
    if len(body_bytes) > 65_536:   # 64 KB
        raise HTTPException(status_code=413, detail="Request body too large (max 64 KB)")
    body = json.loads(body_bytes)
    current = load_config()

    # ── FortiGate ──────────────────────────────────────────────────────────────
    fg_body = body.get("fortigate")
    if fg_body:
        cur_fg = current.fortigate
        fg_body["access_token"] = _merge_secret(
            fg_body.get("access_token"), cur_fg.access_token if cur_fg else None)
        fg_body["ssh_password"] = _merge_secret(
            fg_body.get("ssh_password"), cur_fg.ssh_password if cur_fg else None)
    elif "fortigate" in body and fg_body is None:
        pass   # explicit null → remove section

    # ── Global switch credentials ──────────────────────────────────────────────
    sw_creds_body = body.get("switch_credentials")
    if sw_creds_body:
        cur_sc = current.switch_credentials
        sw_creds_body["password"] = _merge_secret(
            sw_creds_body.get("password"), cur_sc.password if cur_sc else None)

    # ── Cisco switches ─────────────────────────────────────────────────────────
    cur_cisco = {sw.name: sw for sw in current.cisco_switches}
    for sw in body.get("cisco_switches", []):
        cur = cur_cisco.get(sw.get("name"))
        sw["password"] = _merge_secret(sw.get("password"), cur.password if cur else None)
        # Keep username as-is — empty means "use global creds at runtime"

    # ── Aruba switches ─────────────────────────────────────────────────────────
    cur_aruba = {sw.name: sw for sw in current.aruba_switches}
    for sw in body.get("aruba_switches", []):
        cur = cur_aruba.get(sw.get("name"))
        sw["password"] = _merge_secret(sw.get("password"), cur.password if cur else None)
        # Keep username as-is — empty means "use global creds at runtime"

    # ── Cloud: Ruckus One ──────────────────────────────────────────────────────
    r1_body = body.get("ruckus_r1")
    if r1_body:
        cur_r1 = current.ruckus_r1
        r1_body["client_secret"] = _merge_secret(
            r1_body.get("client_secret"), cur_r1.client_secret if cur_r1 else None)
        r1_body["api_key"] = _merge_secret(
            r1_body.get("api_key"), cur_r1.api_key if cur_r1 else None)

    # ── Cloud: Aruba Central ───────────────────────────────────────────────────
    ac_body = body.get("aruba_central")
    if ac_body:
        cur_ac = current.aruba_central
        ac_body["client_secret"] = _merge_secret(
            ac_body.get("client_secret"), cur_ac.client_secret if cur_ac else None)

    # ── Cloud: ExtremeCloud IQ ─────────────────────────────────────────────────
    xiq_body = body.get("extreme_iq")
    if xiq_body:
        cur_xiq = current.extreme_iq
        xiq_body["api_key"] = _merge_secret(
            xiq_body.get("api_key"), cur_xiq.api_key if cur_xiq else None)
        xiq_body["client_secret"] = _merge_secret(
            xiq_body.get("client_secret"), cur_xiq.client_secret if cur_xiq else None)

    # ── Server ─────────────────────────────────────────────────────────────────
    srv_body = body.get("server", {})
    srv_body["api_key"] = _merge_secret(
        srv_body.get("api_key"), current.server.api_key)
    body["server"] = srv_body

    # ── Validate + save ────────────────────────────────────────────────────────
    try:
        new_cfg = AppConfig(**body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid config: {e}")

    try:
        save_config(new_cfg)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    reset_config()   # force reload on next request
    logger.info("Config saved via /api/settings")
    return {"ok": True, "message": "Configuration saved. Changes take effect immediately."}


@app.get("/api/ui-config")
async def ui_config():
    """Non-sensitive config the frontend needs to bootstrap."""
    cfg = load_config()
    return {
        "api_key_required": bool(cfg.server.api_key),
        "version": _read_version(),
    }


# ── Static frontend ────────────────────────────────────────────────────────────

if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/")
    async def root():
        return FileResponse(_index_html)
