"""
backend/scripts/export_openapi.py — Export OpenAPI schema for MasterAgent.

Ensures deterministic output using PYTHONHASHSEED=0 via subprocess isolation
and key-sorted JSON formatting. Supports --check for CI drift verification.
"""
import json
import os
import re
import sys
import subprocess
from pathlib import Path

# ─────────────────────────────────────────────
# 1. Subprocess Isolation for PYTHONHASHSEED=0
# ─────────────────────────────────────────────
if os.environ.get("PYTHONHASHSEED") != "0":
    env = {**os.environ, "PYTHONHASHSEED": "0"}
    result = subprocess.run([sys.executable] + sys.argv, env=env)
    sys.exit(result.returncode)

# ─────────────────────────────────────────────
# 2. Main Export Logic
# ─────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

def derive_tags(path: str, existing_tags: list) -> list:
    """Derive appropriate OpenAPI tags if none provided."""
    if existing_tags:
        return existing_tags
    p = path.lower()
    if "/api/memory/admin" in p:
        return ["Memory Admin"]
    if "/api/memory/config" in p:
        return ["Memory Config"]
    if "/api/memory/webhooks" in p or "webhook" in p:
        return ["Memory Webhooks"]
    if "/api/memory/workspace" in p:
        return ["Memory Workspace"]
    if "/api/memory/trigger" in p:
        return ["Memory Triggers"]
    if "/api/memory" in p:
        return ["🧠 Memory"]
    if "/api/prompts" in p:
        return ["📝 Prompts"]
    if "/api/settings" in p:
        return ["Settings"]
    if "/api/auth" in p:
        return ["Auth"]
    if "/api/templates" in p:
        return ["Templates"]
    if "/api/api-keys" in p:
        return ["API Keys"]
    return ["General"]

def classify_surface(path: str, tags: list) -> str:
    """Classify endpoint as 'console' (admin/config) or 'library' (runtime engine)."""
    p = path.lower()
    tag_str = " ".join(t.lower() for t in tags)
    
    if (
        "/admin" in p
        or "/config" in p
        or "/settings" in p
        or "/api-keys" in p
        or "/auth" in p
        or "admin" in tag_str
        or "config" in tag_str
        or "settings" in tag_str
        or "auth" in tag_str
    ):
        return "console"
    return "library"

def export_openapi():
    from server import app

    # Ensure all routes generate schema for contract tagging
    for route in app.routes:
        if hasattr(route, "include_in_schema"):
            route.include_in_schema = True

    # Generate OpenAPI schema
    openapi_schema = app.openapi()

    paths = openapi_schema.get("paths", {})
    console_count = 0
    library_count = 0
    seen_op_ids = set()

    for path, methods in paths.items():
        for method, op in methods.items():
            if method.lower() in ("get", "post", "put", "delete", "patch", "options", "head"):
                # 1. Derive tags if missing
                op["tags"] = derive_tags(path, op.get("tags", []))

                # 2. Derive unique operationId if missing or duplicated
                op_id = op.get("operationId")
                clean_path_id = re.sub(r"[^a-zA-Z0-9_]", "_", f"{method}_{path}").strip("_")
                if not op_id or op_id in seen_op_ids:
                    op["operationId"] = clean_path_id
                seen_op_ids.add(op["operationId"])

                # 3. Classify surface
                surface = classify_surface(path, op["tags"])
                op["x-surface"] = surface
                if surface == "console":
                    console_count += 1
                else:
                    library_count += 1

    # Format JSON deterministically
    formatted_json = json.dumps(openapi_schema, indent=2, sort_keys=True) + "\n"

    target_dir = ROOT_DIR / "contracts"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "openapi.json"

    is_check = "--check" in sys.argv

    if is_check:
        if not target_file.exists():
            print(f"Error: {target_file} does not exist for --check.", file=sys.stderr)
            sys.exit(1)

        current_content = target_file.read_text(encoding="utf-8")
        if current_content != formatted_json:
            print(f"Error: OpenAPI spec drift detected in {target_file}!", file=sys.stderr)
            print("Run '.venv/Scripts/python.exe backend/scripts/export_openapi.py' to update.", file=sys.stderr)
            sys.exit(1)

        op_count = len(openapi_schema.get("paths", {}))
        total_endpoints = console_count + library_count
        print(f"OpenAPI spec check passed clean. Path operations: {total_endpoints} ({library_count} library, {console_count} console) across {op_count} paths.")
        sys.exit(0)
    else:
        target_file.write_text(formatted_json, encoding="utf-8")
        total_endpoints = console_count + library_count
        print(f"Exported OpenAPI spec to {target_file} ({total_endpoints} operations: {library_count} library, {console_count} console).")

if __name__ == "__main__":
    export_openapi()
