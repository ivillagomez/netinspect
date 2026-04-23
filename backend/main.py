import asyncio
import hmac
import logging
import os
from fastapi import FastAPI, HTTPException, Depends, Security, Request
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import load_config
from backend.models import TraceRequest, TraceResult
from backend.tracer.mac_tracer import NetworkTracer

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


# ── API routes ─────────────────────────────────────────────────────────────────

@app.post("/api/trace", response_model=TraceResult, dependencies=[Depends(verify_api_key)])
async def trace(request: TraceRequest):
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
            "fortigate":      {"name": "FortiGate"},
            "cisco_switches": [{"name": sw.name} for sw in cfg.cisco_switches],
            "ruckus_r1":      {"name": "Ruckus One"},
        }
    except Exception as e:
        logger.error(f"Devices listing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load device list")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/r1/test", dependencies=[Depends(verify_api_key)])
async def r1_test():
    """Probe Ruckus One API and return the raw HTTP result for diagnostics."""
    logger.info("R1 test endpoint called")
    tracer = get_tracer()
    result = await tracer.r1.test_connection()
    # Redact auth headers before returning
    if "headers_sent" in result:
        hdrs = result["headers_sent"]
        for k in list(hdrs.keys()):
            if "auth" in k.lower() or "key" in k.lower():
                hdrs[k] = hdrs[k][:8] + "…" if len(hdrs.get(k, "")) > 8 else "***"
    return result


@app.get("/api/ui-config")
async def ui_config():
    """Non-sensitive config the frontend needs to bootstrap."""
    cfg = load_config()
    return {"api_key_required": bool(cfg.server.api_key)}


# ── Static frontend ────────────────────────────────────────────────────────────

if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/")
    async def root():
        return FileResponse(_index_html)
