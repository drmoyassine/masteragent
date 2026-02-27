# Active Context

> **Last Updated**: 2026-02-27T05:30:00Z
> **Purpose**: Tracks current session context, recent changes, and immediate next steps for AI assistants.

---

## Current Focus

**Task**: Variables Management System Polish
**Status**: 🔄 In Progress
**Started**: 2026-02-27

### Pending Tasks
1. **@ Autocomplete Position** - Popover appears in middle of page, not inline at cursor position
2. **Section DnD Not Working** - Cannot reorder sections via drag and drop
3. **Variable Bar Styling**:
   - Right-align "Variables:" label with variable list
   - Highlight variables in light green color (both in list and editor)
   - Enable drag-and-drop from horizontal list into editor at cursor location
4. **Review HANDOFF.md** - Check if there are remaining items

### What Was Done
- Fixed save button (section write endpoints now use storage service)
- Implemented Variables Management System (backend + frontend)
- Added scope selection (Prompt Level vs Account Level)
- Restored horizontal variable list
- @ autocomplete partially working (needs position fix)
- Fixed login redirect race condition (async login flow)
- Fixed route content issue (removed aggressive redirect)
- Implemented pluggable storage service architecture
- Added local file system storage option
- Updated SetupPage with storage selection UI
- Added ConfigContext for configuration state
- Added warning banners in MainLayout
- Added Docker volume mounts for data persistence
- Fixed automatic fallback to local storage when GitHub not configured
- Fixed section endpoints to use storage service (template sections now appear)
- Fixed frontend-backend version consistency (frontend now reads `is_default` from API)
- Updated AGENTS.md with PowerShell syntax guidelines and lessons learned

---

## Recent Changes

### 2026-02-27 (Session 2 - Variables System)
| Change | Files | Description |
|--------|-------|-------------|
| Variables backend | `backend/server.py` | Added account_variables and prompt_variables tables + CRUD endpoints |
| Variables API | `backend/server.py` | Added `/prompts/{id}/available-variables` endpoint for autocomplete |
| Variables injection | `backend/server.py` | Updated `inject_variables()` with resolution order (runtime > prompt > account) |
| VariablesPanel | `frontend/src/components/VariablesPanel.jsx` | Add/edit/delete UI for variables |
| VariableAutocomplete | `frontend/src/components/VariableAutocomplete.jsx` | @ trigger autocomplete component |
| Scope selection | `PromptEditorPage.jsx` | Radio buttons for Prompt Level vs Account Level |
| Horizontal variable list | `PromptEditorPage.jsx` | Available variables display at top of editor |
| Section write fix | `backend/server.py` | Section CRUD now uses storage service with local fallback |

### 2026-02-27 (Session 1 - Storage & Auth)
| Change | Files | Description |
|--------|-------|-------------|
| Login redirect fix | `AuthContext.jsx`, `AuthCallbackPage.jsx`, `AuthPage.jsx` | Made login async to fix race condition |
| Route content fix | `App.js`, `ConfigContext.jsx` | Removed aggressive redirect, added config context |
| Storage service | `backend/storage_service.py` | Abstract interface + GitHub + Local implementations |
| Storage mode API | `backend/server.py` | Added storage_mode column and endpoint |
| SetupPage rewrite | `SetupPage.jsx` | Storage selection UI (local vs GitHub) |
| Warning banners | `MainLayout.jsx` | Visual indicators for storage status |
| GLiNER CPU fix | `gliner/Dockerfile` | CPU-only PyTorch to avoid 2.5GB CUDA download |
| Docker profiles | `docker-compose.yml` | Made GLiNER optional via profiles |

### 2026-02-26
| Change | Files | Description |
|--------|-------|-------------|
| Memory bank creation | `.memory/*` | Initial creation of memory bank system |
| AGENTS.md | `AGENTS.md`, `.roo/rules-*` | AI assistant documentation |

---

## Immediate Next Steps

### If Continuing Development

1. **Configure LLM APIs** (P0)
   - Navigate to `/app/memory` → LLM APIs tab
   - Add API keys for: summarization, embedding, vision, entity_extraction, pii_scrubbing
   - Test with sample interactions

2. **Start GLiNER Service** (P0)
   ```bash
   docker-compose up gliner
   ```

3. **Initialize Qdrant** (P1)
   ```bash
   curl -X POST http://localhost:8001/api/memory/init
   ```

4. **Enable Background Tasks** (P1)
   - Add scheduler for automated sync and mining
   - Consider Celery or asyncio tasks on startup

### If Starting Fresh Session

1. Read this file (`.memory/active-context.md`)
2. Review [`progress.md`](progress.md) for current status
3. Check [`decisions.md`](decisions.md) for architectural context
4. Reference [`patterns.md`](patterns.md) for coding conventions

---

## Active Development Areas

| Area | Status | Notes |
|------|--------|-------|
| Variables System | 🔄 In Progress | @ autocomplete position, DnD, styling needed |
| Prompt Manager | ✅ Stable | No active work needed |
| Memory Backend | ✅ Complete | Awaiting LLM configuration |
| Memory Frontend | ✅ Complete | All pages implemented |
| Authentication | ✅ Complete | Dual auth working |
| Docker Deploy | ✅ Working | Production-ready |
| Testing | ✅ Passing | 5 iterations completed |
| Documentation | ✅ Current | Memory bank created |

---

## Configuration Status

| Component | Configured | Action Needed |
|-----------|------------|---------------|
| JWT Secret | ✅ | None |
| GitHub OAuth | ⚠️ | Set credentials in `.env` |
| Qdrant | ✅ | Auto-initializes |
| GLiNER | ⚠️ | Start Docker container |
| LLM APIs | ❌ | Add keys via admin UI |

---

## Known Issues

| Issue | Impact | Workaround |
|-------|--------|------------|
| @ autocomplete position | Popover in middle of page | Needs cursor position fix |
| Section DnD not working | Cannot reorder sections | Needs drag-and-drop implementation |
| Variable bar styling | Not aligned/highlighted | CSS improvements needed |
| LLM not configured | Empty summarization/embedding | Add API keys in settings |
| GLiNER not running | Slower NER, LLM fallback | `docker-compose up gliner` |
| Manual background tasks | No auto-sync | Trigger via Monitor page |

---

## Session Notes

### For New AI Assistants

When starting a new session:

1. **Read Order**:
   1. This file (`active-context.md`)
   2. [`project.md`](project.md) for overview
   3. [`progress.md`](progress.md) for status
   4. [`patterns.md`](patterns.md) before coding

2. **Key Files to Know**:
   - [`AGENTS.md`](../AGENTS.md) - Quick reference
   - [`HANDOFF.md`](../HANDOFF.md) - Detailed handoff
   - [`backend/memory_routes.py`](../backend/memory_routes.py) - Memory API (1500+ lines)
   - [`frontend/src/lib/api.js`](../frontend/src/lib/api.js) - API client

3. **Before Making Changes**:
   - Check which database (main vs memory)
   - Verify auth type (JWT vs API Key)
   - Follow patterns in [`patterns.md`](patterns.md)

4. **After Making Changes**:
   - Update this file with changes made
   - Update [`progress.md`](progress.md) if milestones reached
   - Add decisions to [`decisions.md`](decisions.md) if architectural

---

## Quick Commands Reference

```bash
# Start development
docker-compose up -d

# Backend only
cd backend && uvicorn server:app --reload --port 8000

# Frontend only
cd frontend && yarn start

# Run tests
cd backend && pytest tests/ -v

# Initialize memory system
curl -X POST http://localhost:8001/api/memory/init
```

---

## Contact Points

| Resource | Location |
|----------|----------|
| Project README | [`README.md`](../README.md) |
| Agent Guidance | [`AGENTS.md`](../AGENTS.md) |
| Handoff Doc | [`HANDOFF.md`](../HANDOFF.md) |
| Memory PRD | [`memory/PRD.md`](../memory/PRD.md) |
| Test Reports | [`test_reports/`](../test_reports/) |

---

*Update this file at the start and end of each session to maintain context continuity.*
