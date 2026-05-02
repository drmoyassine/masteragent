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
from fastapi import Depends
from fastapi_mcp import FastApiMCP, AuthConfig

from mcp_utils import sanitize_tools_for_gemini, verify_mcp_service_key

_mcp_svc_key = os.environ.get("MCP_SERVICE_KEY", "")
_mcp_http_client = httpx.AsyncClient(headers={
    "Authorization": f"Bearer {_mcp_svc_key}",
    "X-API-Key": _mcp_svc_key,
}) if _mcp_svc_key else None

_mcp_auth = AuthConfig(dependencies=[Depends(verify_mcp_service_key)])

_prompts_mcp = FastApiMCP(
    app,
    name="MasterAgent Prompts",
    include_tags=["📝 Prompts"],
    http_client=_mcp_http_client,
    auth_config=_mcp_auth,
)
sanitize_tools_for_gemini(_prompts_mcp.tools)
_prompts_mcp.mount_http(mount_path="/api/prompts/mcp")

_memory_mcp = FastApiMCP(
    app,
    name="MasterAgent Memory",
    include_tags=["🧠 Memory"],
    http_client=_mcp_http_client,
    auth_config=_mcp_auth,
)
sanitize_tools_for_gemini(_memory_mcp.tools)
_memory_mcp.mount_http(mount_path="/api/memory/mcp")

logger.info(
    "MCP servers mounted (auth: X-API-Key=MCP_SERVICE_KEY): "
    "/api/prompts/mcp, /api/memory/mcp"
)

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
