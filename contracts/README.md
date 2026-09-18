# MasterAgent API Contracts & Hygiene Ratchet

This directory contains the machine-checkable OpenAPI contract for MasterAgent and the untyped operations hygiene baseline.

## Files
- `openapi.json` — Machine-checkable OpenAPI 3.0 specification exported from the FastAPI application. Every path operation carries an `x-surface` attribute (`library` or `console`).
- `openapi_gaps.json` — Baseline inventory of untyped response operations. New untyped routes added beyond this list trigger CI failure.

## Surface Classification (`x-surface`)
- **`library` (125 operations)**: Core agent engine API surface consumed programmatically by clients and frameworks (ingest, search, memories, intelligence, knowledge, facets, prompts, render, tick).
- **`console` (103 operations)**: Administrative and configuration surface (`/admin`, `/config`, `/settings`, `/api-keys`, `/auth`). Excluded from runtime edge compilation gates.

## Three-Step Contract Rule for Developers
When adding or modifying API endpoints in MasterAgent:
1. Define the handler in FastAPI with an explicit `response_model` (Pydantic model).
2. Regenerate the contract via:
   ```powershell
   .venv311/Scripts/python.exe backend/scripts/export_openapi.py
   .venv311/Scripts/python.exe backend/scripts/openapi_check.py
   ```
3. Commit the updated router code, `contracts/openapi.json`, and `contracts/openapi_gaps.json` together in the same PR.
