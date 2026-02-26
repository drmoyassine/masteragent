# Architect Mode Rules - MasterAgent (PromptSRC)

## Architectural Constraints

### Database Separation (CRITICAL)
- **NEVER** mix main DB and memory DB operations in same transaction
- Main DB (`prompt_manager.db`): users, prompts, templates, api_keys, settings
- Memory DB (`data/memory.db`): entity_types, agents, interactions, lessons
- Cross-DB queries require separate connections

### Authentication Layer Architecture
```
┌─────────────────────────────────────────────────────┐
│                   FastAPI Backend                    │
├─────────────────────┬───────────────────────────────┤
│   Admin Endpoints   │      Agent Endpoints          │
│   (JWT Auth)        │      (API Key Auth)           │
│   /api/config/*     │      /api/interactions        │
│   /api/prompts/*    │      /api/lessons             │
│   /api/settings     │      /api/search              │
├─────────────────────┴───────────────────────────────┤
│              Memory Router (/api/memory)             │
└─────────────────────────────────────────────────────┘
```

### Service Dependencies
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   Backend    │────▶│   Qdrant     │
│   (React)    │     │  (FastAPI)   │     │ (Vectors)    │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────▼───────┐
                     │   GLiNER     │
                     │   (NER)      │
                     └──────────────┘
```

### LLM Configuration Pattern
- Each `task_type` has ONE active config (`UNIQUE(task_type, is_active)`)
- Configs stored in `memory_llm_configs` table
- Services fetch config via `get_llm_config(task_type)`
- API keys stored as `api_key_encrypted` (currently plaintext, future: encrypt)

### Frontend State Architecture
```
AuthProvider (context/AuthContext.jsx)
    └── MainLayout
        └── ProtectedRoute
            └── Page Components
                └── API calls via lib/api.js
```

## Design Patterns

### Context Manager Pattern (Required for DB)
```python
# CORRECT
with get_db_context() as conn:
    cursor = conn.cursor()
    cursor.execute("...")

# WRONG - connection not closed
conn = get_db()
cursor = conn.cursor()
```

### API Response Pattern
```python
# Pydantic models for all responses
@router.get("/items", response_model=List[ItemResponse])
async def list_items():
    return [dict(row) for row in cursor.fetchall()]
```

### Frontend API Pattern
```javascript
// All API calls in lib/api.js
// Auth handled by interceptor
export const getResource = () => api.get('/resource');
```

## Scaling Considerations
1. **Database**: SQLite → PostgreSQL via `DATABASE_TYPE` env var
2. **Qdrant**: Already supports distributed mode
3. **GLiNER**: Stateless, can be horizontally scaled
4. **Backend**: Uvicorn workers can be increased

## Environment Variables
```
# Backend
JWT_SECRET_KEY, DATABASE_TYPE, DATABASE_URL
QDRANT_URL, QDRANT_API_KEY
GLINER_URL
GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET

# Frontend (build-time)
REACT_APP_BACKEND_URL
```
