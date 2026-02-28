"""
memory/__init__.py — Memory system router
"""
from fastapi import APIRouter

from memory.config import router as config_router
from memory.agent import router as agent_router
from memory.admin import router as admin_router

memory_router = APIRouter(prefix="/api/memory", tags=["Memory"])
memory_router.include_router(config_router)
memory_router.include_router(agent_router)
memory_router.include_router(admin_router)
