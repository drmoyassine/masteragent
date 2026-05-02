"""
server.py — Application entry point (refactored)

Responsibilities:
  1. Load environment variables
  2. Initialize databases (main + memory)
  3. Create the FastAPI app
  4. Register all route modules
  5. Configure CORS and middleware
  6. Start background tasks on startup

All business logic has been extracted to:
  core/      — shared DB and auth utilities
  routes/    — main API route modules
  memory/    — memory system routes (split from memory_routes.py)
  db_init.py — database schema creation and seeding
"""
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
env_path = ROOT_DIR / ".env"
if not env_path.exists():
    env_path = ROOT_DIR.parent / ".env"
load_dotenv(env_path)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# ─────────────────────────────────────────────
# Database initialization (must run before routes import DB)
# ─────────────────────────────────────────────
from db_init import init_db, seed_admin_user
from memory_db import init_memory_db

init_db()
init_memory_db()  # Set up PostgreSQL schema + seed defaults
seed_admin_user()

# ─────────────────────────────────────────────
# Background tasks (lifespan)
# ─────────────────────────────────────────────
from memory_tasks import start_background_tasks, stop_background_tasks
from memory.queue import start_bullmq_workers, stop_bullmq_workers

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on boot, stop cleanly on shutdown."""
    logger.info("Starting memory system background tasks")
    await start_background_tasks()
    await start_bullmq_workers()
    yield
    logger.info("Stopping memory system background tasks")
    await stop_background_tasks()
    await stop_bullmq_workers()

# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────
app = FastAPI(
    title="MasterAgent Platform SDK",
    docs_url=None,  # We manually override this below for custom CSS
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# ─────────────────────────────────────────────
# Custom Swagger UI (Dark Mode)
# ─────────────────────────────────────────────
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
import os

static_dir = os.path.join(ROOT_DIR, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/api/static", StaticFiles(directory=static_dir), name="static")

@app.get("/api/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - API Reference",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="/api/static/custom-swagger.css",
    )

# ─────────────────────────────────────────────
# Route modules
# ─────────────────────────────────────────────
from routes.auth import router as auth_router
from routes.settings import router as settings_router
from routes.templates import router as templates_router
from routes.prompts import router as prompts_router
from routes.render import router as render_router
from routes.api_keys import router as api_keys_router
from routes.variables import router as variables_router
from memory import memory_router

# Health check and root (minimal, defined inline)
from fastapi import APIRouter
from datetime import datetime, timezone

_meta_router = APIRouter() # Removed prefix="/api" to avoid double prefixing

@_meta_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@_meta_router.get("/")
async def root():
    return {"message": "Prompt Manager & Memory System API", "version": "1.0.0"}

# Register all routers under /api prefix. Only expose prompts to public Swagger
app.include_router(auth_router, prefix="/api", include_in_schema=False)
app.include_router(settings_router, prefix="/api", include_in_schema=False)
app.include_router(templates_router, prefix="/api", include_in_schema=False)
app.include_router(prompts_router, prefix="/api", tags=["📝 Prompts"]) # Agent SDK visible
app.include_router(render_router, prefix="/api", include_in_schema=False)
app.include_router(api_keys_router, prefix="/api", include_in_schema=False)
app.include_router(variables_router, prefix="/api", include_in_schema=False)
app.include_router(_meta_router, prefix="/api", include_in_schema=False)

# Memory system (already carries its own /api/memory prefix)
app.include_router(memory_router)

# ─────────────────────────────────────────────
# MCP Servers (fastapi-mcp, streamable HTTP)
# Two separate endpoints so n8n can connect per-domain:
#   /api/prompts/mcp  → prompt CRUD + render + variables
#   /api/memory/mcp   → memory agent SDK (ingest, search, CRUD)
#
# - Inbound auth: X-API-Key (or Authorization: Bearer) must equal
#   MCP_SERVICE_KEY. Same credential the rest of the API accepts.
# - Outbound: the http_client pre-injects MCP_SERVICE_KEY into every tool call.
# - Tool schemas are sanitized so Gemini's strict OpenAPI subset accepts them
#   (no anyOf / no array `type` / no null branches).
# ─────────────────────────────────────────────
import httpx
from fastapi_mcp import FastApiMCP

from mcp_utils import sanitize_tools_for_gemini

_mcp_svc_key = os.environ.get("MCP_SERVICE_KEY", "")
_mcp_http_client = httpx.AsyncClient(headers={
    "Authorization": f"Bearer {_mcp_svc_key}",
    "X-API-Key": _mcp_svc_key,
}) if _mcp_svc_key else None

_prompts_mcp = FastApiMCP(
    app,
    name="MasterAgent Prompts",
    include_tags=["📝 Prompts"],
    http_client=_mcp_http_client,
)
sanitize_tools_for_gemini(_prompts_mcp.tools)
_prompts_mcp.mount_http(mount_path="/api/prompts/mcp")

_memory_mcp = FastApiMCP(
    app,
    name="MasterAgent Memory",
    include_tags=["🧠 Memory"],
    http_client=_mcp_http_client,
)
sanitize_tools_for_gemini(_memory_mcp.tools)
_memory_mcp.mount_http(mount_path="/api/memory/mcp")

logger.info("MCP servers mounted: /api/prompts/mcp, /api/memory/mcp")

# ─────────────────────────────────────────────
# Sanitization self-check — fails loud at boot if any tool still leaks anyOf/etc
# ─────────────────────────────────────────────
import json as _json

def _count_leaks(tools):
    counts = {"anyOf": 0, "oneOf": 0, "allOf": 0, "list_type": 0, "ref": 0, "nullable": 0, "default_null": 0}
    for t in tools:
        s = _json.dumps(t.inputSchema)
        counts["anyOf"] += s.count('"anyOf"')
        counts["oneOf"] += s.count('"oneOf"')
        counts["allOf"] += s.count('"allOf"')
        counts["list_type"] += s.count('"type": [')
        counts["ref"] += s.count('"$ref"')
        counts["nullable"] += s.count('"nullable"')
        counts["default_null"] += s.count('"default": null')
    return counts

_p_leaks = _count_leaks(_prompts_mcp.tools)
_m_leaks = _count_leaks(_memory_mcp.tools)
logger.info(f"[mcp-sanitizer] prompts MCP tools={len(_prompts_mcp.tools)} leaks={_p_leaks}")
logger.info(f"[mcp-sanitizer] memory MCP tools={len(_memory_mcp.tools)} leaks={_m_leaks}")
for _name, _leaks in [("prompts", _p_leaks), ("memory", _m_leaks)]:
    if any(v > 0 for v in _leaks.values()):
        logger.error(f"[mcp-sanitizer] {_name} MCP STILL HAS LEAKS: {_leaks} — Gemini will reject")

# Diagnostic: leak counts only (no schema content) — unauthenticated
@app.get("/api/mcp-debug/leaks", include_in_schema=False)
async def mcp_leaks():
    return {
        "prompts": {"tool_count": len(_prompts_mcp.tools), "leaks": _count_leaks(_prompts_mcp.tools)},
        "memory":  {"tool_count": len(_memory_mcp.tools),  "leaks": _count_leaks(_memory_mcp.tools)},
        "memory_tool_names": [t.name for t in _memory_mcp.tools],
    }

# ─────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_MCP_PATHS = ("/api/prompts/mcp", "/api/memory/mcp")


@app.middleware("http")
async def mcp_auth_guard(request: Request, call_next):
    """Protect MCP endpoints.

    Accepts any of:
      - X-API-Key / Authorization: Bearer matching MCP_SERVICE_KEY (service key)
      - X-API-Key / Authorization: Bearer matching any active key in memory_agents
        (the UI-created 'Memory Keys')
    Using middleware so no OAuth/WWW-Authenticate headers confuse n8n's MCP client.
    """
    if not request.url.path.startswith(_MCP_PATHS):
        return await call_next(request)

    from fastapi.responses import JSONResponse

    raw_key = (
        request.headers.get("x-api-key")
        or request.headers.get("X-API-Key")
        or ""
    )
    bearer = request.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        raw_key = raw_key or bearer[7:]

    if not raw_key:
        return JSONResponse({"detail": "API key required"}, status_code=401)

    # Fast-path: service key
    if _mcp_svc_key and raw_key == _mcp_svc_key:
        return await call_next(request)

    # Slow-path: check memory_agents table (same logic as verify_agent_key)
    import hashlib
    from core.storage import get_memory_db_context
    try:
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        with get_memory_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM memory_agents WHERE api_key_hash = %s AND is_active = TRUE",
                (key_hash,)
            )
            if cursor.fetchone():
                return await call_next(request)
    except Exception as e:
        logger.error(f"MCP auth DB error: {e}")
        return JSONResponse({"detail": "Auth check failed"}, status_code=500)

    return JSONResponse({"detail": "Invalid or missing MCP credentials"}, status_code=401)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug(f"Request: {request.method} {request.url}")
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"Headers: {dict(request.headers)}")
    response = await call_next(request)
    return response


# ─────────────────────────────────────────────
# Startup logging
# ─────────────────────────────────────────────
from core.db import DB_PATH

logger.info("Starting Prompt Manager & Memory System API")
logger.info(f"CORS Origins: {os.environ.get('CORS_ORIGINS', '*')}")
logger.info(f"Frontend URL: {FRONTEND_URL}")
logger.info(f"Main DB: {DB_PATH}")
logger.info(f"Memory DB: {os.environ.get('MEMORY_POSTGRES_URL', 'postgresql://postgres:postgres@localhost:5432/memory')}")
