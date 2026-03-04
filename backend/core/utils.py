"""
core/utils.py — Shared utility functions

Small helpers used across routes and services to avoid inline duplication.
"""
from datetime import datetime, timezone


def utcnow() -> str:
    """Return current UTC time as an ISO-8601 string (timezone-aware)."""
    return datetime.now(timezone.utc).isoformat()
