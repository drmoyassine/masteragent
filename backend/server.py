"""
server.py — Application entry point (refactored)

Responsibilities:
  1. Load environment variables
  2. Initialize databases (main + memory)
  3. Create the FastAPI app
  4. Register all route modules
  5. Configure CORS and middleware

All business logic has been extracted to:
  core/      — shared DB and auth utilities
  routes/    — main API route modules
  memory/    — memory system routes (split from memory_routes.py)
  db_init.py — database schema creation and seeding
"""
import os
import logging
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
init_memory_db()
seed_admin_user()

# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────
app = FastAPI(title="Prompt Manager & Memory System API")

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

_meta_router = APIRouter(prefix="/api")

@_meta_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

@_meta_router.get("/")
async def root():
    return {"message": "Prompt Manager & Memory System API", "version": "1.0.0"}

# Register all routers under /api prefix
for _router in [auth_router, settings_router, templates_router,
                prompts_router, render_router, api_keys_router,
                variables_router, _meta_router]:
    app.include_router(_router, prefix="/api")

# Memory system (already carries its own /api/memory prefix)
app.include_router(memory_router)

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

logger.info("Starting Prompt Manager API")
logger.info(f"CORS Origins: {os.environ.get('CORS_ORIGINS', '*')}")
logger.info(f"Frontend URL: {FRONTEND_URL}")
logger.info(f"Database Path: {DB_PATH}")
