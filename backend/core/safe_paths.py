"""Path and identifier validation shared by prompt storage backends."""
import re
from pathlib import Path

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")


def validate_storage_component(value: str, label: str) -> str:
    """Reject separators, traversal, control characters, and empty components."""
    if not value or value in {".", ".."} or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def safe_join(root: Path, *parts: str) -> Path:
    """Join paths and prove the resolved result remains beneath ``root``."""
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("Storage path escapes the configured root") from exc
    return candidate


def validate_relative_storage_path(value: str, label: str = "storage path") -> str:
    """Validate a slash-separated repository path without changing its shape."""
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if normalized.startswith("/") or not parts:
        raise ValueError(f"Invalid {label}")
    for part in parts:
        validate_storage_component(part, label)
    return "/".join(parts)
