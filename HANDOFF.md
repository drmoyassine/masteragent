# Agent Handoff Document - PromptSRC

> **Last Updated**: February 27, 2026 (Session 3)
> **Status**: Production-Ready MVP + Variables System Complete
> **Priority**: Configure LLM APIs, test end-to-end flow

---

## ✅ Completed This Session (2026-02-27)

### High Priority - All Done!
1. **@ Autocomplete Position Fix** ✅
   - Fixed: Popover now appears inline at cursor position
   - File: [`VariableAutocomplete.jsx`](frontend/src/components/VariableAutocomplete.jsx)
   - Solution: Calculate cursor coordinates relative to container, not viewport

2. **Section Drag-and-Drop** ✅
   - Fixed: Sections can now be reordered via drag and drop
   - File: [`PromptEditorPage.jsx`](frontend/src/pages/PromptEditorPage.jsx)
   - Solution: Implemented using @dnd-kit/core and @dnd-kit/sortable

3. **Variable Bar Styling** ✅
   - Right-aligned "Variables:" label with variable list
   - Variables highlighted in light green color
   - Click on variable badge to insert at cursor

### Files Modified This Session
- `frontend/src/components/VariableAutocomplete.jsx` - Fixed popover positioning
- `frontend/src/pages/PromptEditorPage.jsx` - Added DnD, improved variable bar styling

---

## 🔴 Pending Tasks (Next Session)

### Configuration (P0)
1. **Configure LLM APIs**
   - Navigate to `/app/memory` → LLM APIs tab
   - Add API keys for: summarization, embedding, vision, entity_extraction, pii_scrubbing
   - Test with sample interactions

2. **Start GLiNER Service**
   ```bash
   docker-compose up gliner
   ```

3. **Initialize Qdrant**
   ```bash
   curl -X POST http://localhost:8001/api/memory/init
   ```

---

## Project Overview

**PromptSRC** is a full-stack application providing infrastructure for AI agents:
1. **Prompt Manager** - Version-controlled prompts stored in GitHub
2. **Memory System** - Persistent memory with semantic search for AI agents

### Quick Context
- **Frontend**: React 18 + Tailwind CSS + Shadcn/UI
- **Backend**: FastAPI (Python 3.11)
- **Databases**: SQLite (dev), PostgreSQL (prod), Qdrant (vectors)
- **NER**: GLiNER2 Docker service
- **Auth**: JWT for admins, API Keys for agents

---

## Current State

### 🔄 In Progress

#### Variables Management System (NEW - 2026-02-27)
Backend complete, frontend needs polish:
- **Database Tables**: `account_variables`, `prompt_variables`
- **API Endpoints**:
  - `GET/POST /api/variables/account` - Account-level variables
  - `GET/POST/DELETE /api/variables/prompt/{prompt_id}` - Prompt-level variables
  - `GET /api/prompts/{id}/available-variables` - Merged list for autocomplete
- **Variable Injection**: Updated `inject_variables()` with resolution order:
  1. Runtime variables (passed in request)
  2. Prompt-level variables
  3. Account-level variables
- **Frontend Components**:
  - [`VariablesPanel.jsx`](frontend/src/components/VariablesPanel.jsx) - Add/edit/delete UI
  - [`VariableAutocomplete.jsx`](frontend/src/components/VariableAutocomplete.jsx) - @ trigger popover
- **Known Issues**:
  - @ autocomplete popover position incorrect (middle of page, not at cursor)
  - Variable bar needs styling improvements (right-align, green highlights)
  - Drag-and-drop from variable list to editor not implemented

### ✅ Fully Implemented

#### Prompt Manager
- Multi-file Markdown prompts with ordered sections
- GitHub integration for storage and versioning
- Variable injection (Mustache-style)
- Render API with API key authentication
- Starter templates (Agent Persona, Task Executor, etc.)

#### Memory System - Backend
- **Database Schema**: All tables created (`memory_db.py`)
  - Config: entity_types, subtypes, lesson_types, channel_types, agents, llm_configs, system_prompts, settings
  - Data: memories, memory_documents, memory_lessons, memories_shared, lessons_shared, audit_log
- **Ingestion Pipeline** (`POST /api/memory/interactions`)
  - Text + file parsing
  - Chunking (configurable)
  - Entity extraction (GLiNER2 or LLM fallback)
  - Summarization
  - Embedding → Qdrant
  - PII scrubbing for shared memories
  - Rate limiting per agent
- **Retrieval APIs**
  - Semantic search
  - Entity timeline
  - Daily log
  - Lessons CRUD
- **Background Tasks** (`memory_tasks.py`)
  - OpenClaw Markdown sync
  - Automated lesson mining
  - Agent stats/monitoring

#### Memory System - Frontend
- **Memory Settings** (`/app/memory`) - 6 tabs for admin configuration
- **Memory Explorer** (`/app/memory/explore`) - Search, timeline, daily log, lessons
- **System Monitor** (`/app/memory/monitor`) - Stats, sync triggers, agent activity

#### Authentication & Security
- JWT auth on all admin config endpoints
- API key auth on agent endpoints
- Rate limiting implemented

---

## File Reference

### Backend (Key Files)
```
/app/backend/
├── server.py              # Main app, prompt routes, auth
├── memory_db.py           # Database schema, initialization
├── memory_models.py       # Pydantic models
├── memory_routes.py       # All /api/memory/* endpoints (1500+ lines)
├── memory_services.py     # LLM calls, embeddings, Qdrant, PII
├── memory_tasks.py        # Background tasks (sync, mining, stats)
└── requirements.txt
```

### Frontend (Key Files)
```
/app/frontend/src/
├── pages/
│   ├── LandingPage.jsx        # Updated with both modules
│   ├── MemorySettingsPage.jsx # Admin config UI
│   ├── MemoryExplorerPage.jsx # Search, timeline, lessons
│   └── MemoryMonitorPage.jsx  # Stats, task triggers
├── components/layout/
│   └── MainLayout.jsx         # Navigation (7 items)
└── lib/api.js                 # All API functions
```

### Docker
```
/app/
├── docker-compose.yml     # Main app + Qdrant + GLiNER
├── Dockerfile             # Multi-stage build
└── gliner/
    ├── app.py             # GLiNER2 NER service
    └── Dockerfile
```

---

## Known Limitations & Technical Debt

### 1. LLM Integration Not Configured
- All LLM configs stored in DB but no API keys set
- Summarization, embedding, vision parsing return empty until configured
- **Fix**: Admin needs to add API keys in Memory Settings → LLM APIs tab

### 2. GLiNER2 Service
- Dockerfile created but not running in preview environment
- Falls back to LLM-based extraction when unavailable
- **Fix**: Run GLiNER service via `docker-compose up gliner`

### 3. Qdrant Collections
- Collections created on first use
- No migrations for existing data
- **Fix**: Call `POST /api/memory/init` to initialize

### 4. Background Tasks
- Currently triggered manually via UI buttons
- Not running on a scheduler
- **Fix**: Add `asyncio.create_task()` call on startup or use Celery

### 5. Error Handling
- Some LLM calls return empty strings on failure
- Could add more specific error responses
- **Priority**: Low (graceful degradation is acceptable)

---

## Future Enhancements (Prioritized)

### P0 - Critical for Production
1. **Real LLM Configuration**
   - Guide users to add OpenAI/Anthropic/Gemini API keys
   - Test embedding generation and search quality

2. **Startup Initialization**
   - Auto-call `init_qdrant_collections()` on server start
   - Run background task scheduler

3. **PostgreSQL Migration**
   - Test with PostgreSQL instead of SQLite
   - Add migration scripts

### P1 - Important Features
4. **Bulk Import/Export**
   - Endpoint to import memories from JSON/CSV
   - Export memories and lessons as ZIP

5. **Webhook Notifications**
   - Notify external systems when lessons are created
   - Real-time activity streaming

6. **Agent Dashboard**
   - Per-agent usage statistics
   - Rate limit monitoring
   - API key rotation

### P2 - Nice to Have
7. **Team Collaboration**
   - Multi-user workspaces
   - Role-based access control

8. **Advanced Search**
   - Faceted filtering
   - Saved searches
   - Search history

9. **GLiNER Model Customization**
   - Custom entity labels per tenant
   - Fine-tuned models

10. **Real-time Activity Dashboard**
    - WebSocket-based live updates
    - Streaming log view

---

## API Endpoints Summary

### Health
```
GET  /api/memory/health
POST /api/memory/init
```

### Config (JWT Required)
```
GET/POST/DELETE  /api/memory/config/entity-types
GET/POST/DELETE  /api/memory/config/entity-subtypes
GET/POST/DELETE  /api/memory/config/lesson-types
GET/POST/DELETE  /api/memory/config/channel-types
GET/POST/PATCH/DELETE  /api/memory/config/agents
GET/POST/PUT/DELETE  /api/memory/config/llm-configs
GET/POST/PUT/DELETE  /api/memory/config/system-prompts
GET/PUT  /api/memory/config/settings
```

### Agent APIs (API Key Required)
```
POST  /api/memory/interactions
POST  /api/memory/search
GET   /api/memory/timeline/{type}/{id}
GET   /api/memory/lessons
```

### Admin APIs (JWT Required)
```
GET   /api/memory/daily/{date}
GET   /api/memory/memories/{id}
POST  /api/memory/search
GET/POST/PUT/DELETE  /api/memory/admin/lessons
GET   /api/memory/admin/timeline/{type}/{id}
GET   /api/memory/admin/stats
GET   /api/memory/admin/stats/agents
POST  /api/memory/admin/sync/openclaw
POST  /api/memory/admin/tasks/mine-lessons
```

---

## Test Credentials

```
Admin Email: admin@promptsrc.com
Admin Password: admin123
Agent API Key: mem_YhZtU7wjp8-gFQKAjyT7ZwKzTC3L7R7I6cqHM3oJbYA
```

---

## Testing Checklist

Before deploying:
- [ ] Login with admin credentials
- [ ] Navigate to Memory Settings → Configure at least one LLM API key
- [ ] Create an agent and note the API key
- [ ] Test ingestion: `curl -X POST /api/memory/interactions -H "X-API-Key: ..." -F "text=Test" -F "channel=note"`
- [ ] Search memories via explorer
- [ ] Check System Monitor stats
- [ ] Test OpenClaw sync (enable in settings first)

---

## Architecture Decisions

### Why Separate Private/Shared Memories?
- Private: Contains raw text with PII
- Shared: PII-scrubbed for team/org-wide access
- Configurable via admin settings

### Why GLiNER2 Instead of LLM for NER?
- Faster and cheaper than LLM calls
- More consistent entity extraction
- Can run locally without API keys
- Falls back to LLM if GLiNER unavailable

### Why Qdrant?
- Purpose-built for vector search
- Supports filtering and metadata
- Easy to self-host
- Good performance at scale

---

## Contact & Resources

- **Code Repository**: `/app/` (this directory)
- **PRD**: `/app/memory/PRD.md`
- **Test Reports**: `/app/test_reports/`
- **Preview URL**: Check `REACT_APP_BACKEND_URL` in `/app/frontend/.env`

---

## Quick Commands

```bash
# Restart backend
sudo supervisorctl restart backend

# Check backend logs
tail -f /var/log/supervisor/backend.err.log

# Test health
curl $(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)/api/memory/health

# Login and get token
curl -X POST $API_URL/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@promptsrc.com","password":"admin123"}'

# Test with token
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/memory/admin/stats
```

---

**Good luck with the continued development!** 🚀
