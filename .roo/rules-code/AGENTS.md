# Code Mode Rules - MasterAgent (PromptSRC)

## Database Context Managers - CRITICAL
```python
# Main DB (users, prompts, settings)
from server import get_db_context
with get_db_context() as conn:
    cursor = conn.cursor()
    # Auto-commits on exit

# Memory DB (entities, interactions, lessons)
from memory_db import get_memory_db_context
with get_memory_db_context() as conn:
    cursor = conn.cursor()
    # Auto-commits on exit
```

## Authentication Patterns
```python
# Admin endpoints (JWT Bearer token)
@router.get("/config/entity-types")
async def list_types(user: dict = Depends(require_admin_auth)):
    # user dict contains: id, email, username, etc.

# Agent endpoints (X-API-Key header)
@router.post("/interactions")
async def create_interaction(
    data: InteractionCreate,
    agent: dict = Depends(verify_agent_key)
):
    # agent dict contains: id, name, access_level
```

## Frontend Path Aliases
```javascript
// Use @/ for src/ imports
import { Button } from "@/components/ui/button";
import { getSettings } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
```

## Memory System Models
```python
# LLM task types (in memory_models.py)
LLMTaskType.SUMMARIZATION
LLMTaskType.EMBEDDING
LLMTaskType.VISION
LLMTaskType.ENTITY_EXTRACTION
LLMTaskType.PII_SCRUBBING

# When creating LLM configs:
config = LLMConfigCreate(
    task_type="summarization",  # Must match enum
    provider="openai",
    name="GPT-4 Summarizer",
    api_key="sk-..."
)
```

## API Client Pattern
```javascript
// frontend/src/lib/api.js - all API calls go here
// Auth token auto-attached via interceptor
import { getSettings, createAgent } from '@/lib/api';

// For agent endpoints with API key:
renderPrompt(promptId, version, variables, apiKey);
```

## Common Gotchas
1. **Two separate SQLite databases** - check which DB your data lives in
2. **Memory router prefix** - all memory endpoints start with `/api/memory`
3. **Frontend uses craco** - not standard CRA, config in `craco.config.js`
4. **Yarn required** - frontend uses `yarn.lock`, not `package-lock.json`
5. **React 19** - uses new React features, check compatibility
