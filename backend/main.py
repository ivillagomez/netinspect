import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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


def get_tracer() -> NetworkTracer:
    global _config, _tracer
    if _tracer is None:
        _config = load_config()
        _tracer = NetworkTracer(_config)
    return _tracer


@app.on_event("startup")
async def startup():
    logger.info("NetInspect starting up...")
    try:
        get_tracer()
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Startup config error: {e}")


# --- API Routes ---

@app.post("/api/trace", response_model=TraceResult)
async def trace(request: TraceRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    tracer = get_tracer()
    try:
        result = await tracer.trace(request.query.strip())
        return result
    except Exception as e:
        logger.error(f"Trace error for '{request.query}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/devices")
async def list_devices():
    """Return configured devices for status overview."""
    try:
        cfg = load_config()
        return {
            "fortigate": {"host": cfg.fortigate.host, "name": "FortiGate"},
            "cisco_switches": [
                {"name": sw.name, "host": sw.host} for sw in cfg.cisco_switches
            ],
            "ruckus_r1": {"base_url": cfg.ruckus_r1.base_url},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# --- Static frontend ---

_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str):
        file_path = os.path.join(_frontend_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
