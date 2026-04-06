"""
memory/__init__.py — Memory system router
"""
from fastapi import APIRouter

from memory.config import router as config_router
from memory.agent import router as agent_router
from memory.admin import router as admin_router
from memory.webhooks import router as webhook_router
from memory.workspace import router as workspace_router

memory_router = APIRouter(prefix="/api/memory", tags=["Memory"])
memory_router.include_router(admin_router)
memory_router.include_router(config_router)
memory_router.include_router(agent_router)
memory_router.include_router(webhook_router)
memory_router.include_router(workspace_router)
