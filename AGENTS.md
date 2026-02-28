# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
MasterAgent (PromptSRC) - Full-stack AI agent infrastructure with prompt management and memory system.

## Memory Bank System

The project uses a unified memory bank located in `.memory/` for AI assistant context persistence:

| File | Purpose |
|------|---------|
| `.memory/project.md` | Project overview, goals, architecture |
| `.memory/active-context.md` | Current focus, recent changes, next steps |
| `.memory/progress.md` | Task tracking, completed/pending features |
| `.memory/decisions.md` | Architecture Decision Records (ADRs) |
| `.memory/patterns.md` | Coding patterns, conventions, gotchas |

### Session Start Protocol
1. Read `.memory/active-context.md` for current state
2. Review `.memory/progress.md` for task status
3. Check `.memory/patterns.md` before coding

### Session End Protocol
1. Update `.memory/active-context.md` with changes made
2. Update `.memory/progress.md` if milestones reached
3. Add decisions to `.memory/decisions.md` if architectural

### Related Documentation
- `ARCHITECTURE.md` - Master engineering architecture and system boundaries
- `docs/` - Technical design documents (e.g., variables-system-design.md)
- `HANDOFF.md` - Project handoff document
- `memory/PRD.md` - Memory system product requirements

## Critical Architecture Notes

### Dual Database System
- **Main DB**: `backend/prompt_manager.db` - Users, prompts, settings, API keys
- **Memory DB**: `backend/data/memory.db` - Entity types, interactions, lessons, agents
- Use `get_db_context()` for main DB, `get_memory_db_context()` for memory DB

### Dual Authentication
- **JWT (Bearer token)**: Admin/config endpoints - via `core.auth.require_admin_auth()`
- **API Key (X-API-Key header)**: Agent-facing endpoints - via `core.auth.verify_agent_key()`

### Service Ports
- Backend: 8001 (Docker), 8000 (local dev)
- GLiNER NER: 8002
- Qdrant: 6333 (REST), 6334 (gRPC)

## Build Commands
```bash
# Frontend (uses yarn + craco)
cd frontend && yarn install && yarn build
# Backend
cd backend && pip install -r requirements.txt
# Docker (production)
docker-compose up --build
```

## Test Commands
```bash
# Run all backend tests
cd backend && pytest tests/ -v
# Run specific test file
pytest tests/test_memory_auth.py -v
# Run with environment override
REACT_APP_BACKEND_URL=http://localhost pytest tests/
```

## Key Patterns
- Frontend path alias: `@/` maps to `frontend/src/`
- Memory router prefix: `/api/memory`
- LLM configs keyed by `task_type` (summarization, embedding, vision, entity_extraction, pii_scrubbing)
- Test credentials: `admin@promptsrc.com` / `admin123`

## Lessons Learned

### PowerShell Syntax (Windows Environment)
> **CRITICAL**: User runs PowerShell 7. Always use PowerShell syntax for commands.

| Unix/Bash | PowerShell | Notes |
|-----------|------------|-------|
| `&&` | `;` | Command chaining |
| `2>/dev/null` | `2>$null` | Redirect stderr to null |
| `grep` | `Select-String` | Search text patterns |
| `cat` | `Get-Content` | Read file contents |
| `rm` | `Remove-Item` | Delete files/folders |
| `cp` | `Copy-Item` | Copy files/folders |
| `mv` | `Move-Item` | Move files/folders |

**Examples:**
```powershell
# Chain commands
cd backend ; python -m pytest tests/ -v

# Redirect stderr
curl -s http://localhost/api/health 2>$null

# Search for pattern
Get-Content server.py | Select-String "error"
```

### Frontend-Backend Version Consistency
- Backend creates prompts with version **"v1"** (not "main")
- Frontend must read `is_default` from versions API to set correct version
- **Never hardcode version defaults** in frontend - always use API response
- Related: [`PromptEditorPage.jsx`](frontend/src/pages/PromptEditorPage.jsx)

### Storage Service Pattern
- **GitHub is primary storage** when configured (has token)
- **Automatic fallback to local** filesystem when GitHub not configured
- All endpoints should use `get_storage_service()` factory function
- Factory checks `github_token` existence before returning GitHub service
- Related: [`storage_service.py`](backend/storage_service.py)

### Docker Volume Mounts for Persistence
- Database should be in separate `/db/` directory for volume mounting
- Local prompts need their own volume mount (`promptsrc_prompts`)
- Named volumes persist across container redeployments
- Volume paths in `docker-compose.yml`:
  - `promptsrc_db` → `/app/backend/db/`
  - `promptsrc_prompts` → `/app/backend/local_prompts/`
