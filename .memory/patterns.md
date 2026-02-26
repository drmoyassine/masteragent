# Code Patterns & Conventions

> **Last Updated**: 2026-02-26
> **Purpose**: Documents coding standards, common patterns, and important gotchas for the MasterAgent project.

---

## Quick Reference

| Area | Convention |
|------|------------|
| **Package Manager (Frontend)** | yarn (not npm) |
| **Package Manager (Backend)** | pip |
| **Path Alias (Frontend)** | `@/` → `frontend/src/` |
| **API Prefix (Memory)** | `/api/memory` |
| **Database (Main)** | `get_db_context()` |
| **Database (Memory)** | `get_memory_db_context()` |

---

## Backend Patterns

### Database Context Managers

Always use context managers for database connections:

```python
# Main database (users, prompts, settings)
from server import get_db_context

with get_db_context() as db:
    # db operations here
    pass

# Memory database (interactions, entities, lessons)
from memory_db import get_memory_db_context

with get_memory_db_context() as db:
    # memory operations here
    pass
```

### Authentication Decorators

```python
# JWT authentication for admin endpoints
from server import require_admin_auth

@router.get("/api/memory/config/entity-types")
async def get_entity_types(current_user: dict = Depends(require_admin_auth)):
    # Only authenticated admins can access
    pass

# API Key authentication for agent endpoints
from memory_routes import verify_agent_key

@router.post("/api/memory/interactions")
async def create_interaction(
    request: InteractionRequest,
    agent: dict = Depends(verify_agent_key)
):
    # agent contains: {"agent_id": "...", "name": "..."}
    pass
```

### Pydantic Models

All request/response models in [`memory_models.py`](../backend/memory_models.py):

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class InteractionRequest(BaseModel):
    content: str
    channel: Optional[str] = "default"
    metadata: Optional[dict] = None

class InteractionResponse(BaseModel):
    id: int
    summary: str
    entities: List[dict]
    created_at: datetime
```

### LLM Configuration Pattern

LLM configs are keyed by `task_type`:

```python
# Task types supported:
TASK_TYPES = [
    "summarization",      # Text summarization
    "embedding",          # Vector embeddings
    "vision",             # Image parsing
    "entity_extraction",  # NER fallback
    "pii_scrubbing"       # PII detection/removal
]

# Fetch config from database
config = db.query(LLMConfig).filter(
    LLMConfig.task_type == "summarization",
    LLMConfig.is_active == True
).first()
```

### Background Tasks

```python
from memory_tasks import (
    sync_openclaw_task,
    mine_lessons_task,
    update_agent_stats
)

# Tasks are async functions
async def run_background_tasks():
    await sync_openclaw_task()
    await mine_lessons_task()
    await update_agent_stats()
```

---

## Frontend Patterns

### Path Aliases

Use `@/` for imports from `src/`:

```javascript
// Good
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { useAuth } from '@/context/AuthContext';

// Avoid
import { Button } from '../../../components/ui/button';
```

### API Client

All API calls through [`lib/api.js`](../frontend/src/lib/api.js):

```javascript
import { api } from '@/lib/api';

// Authenticated requests (JWT)
const response = await api.get('/api/memory/config/entity-types');

// Agent requests (API Key)
const response = await api.post('/api/memory/interactions', {
  content: "User interaction text",
  channel: "email"
}, {
  headers: { 'X-API-Key': agentApiKey }
});
```

### Shadcn/UI Components

Components are in [`components/ui/`](../frontend/src/components/ui/):

```javascript
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/hooks/use-toast';
```

### Page Structure

```javascript
// Standard page structure
import React, { useState, useEffect } from 'react';
import { MainLayout } from '@/components/layout/MainLayout';

export function ExamplePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const result = await api.get('/api/endpoint');
      setData(result);
    } catch (error) {
      toast({ title: 'Error', description: error.message, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <MainLayout>
      {/* Page content */}
    </MainLayout>
  );
}
```

---

## Common Patterns

### Error Handling

```python
# Backend - Graceful degradation
try:
    result = await llm_service.summarize(text)
except Exception as e:
    logger.error(f"Summarization failed: {e}")
    result = ""  # Return empty, don't crash
```

```javascript
// Frontend - User feedback
try {
  await api.post('/api/endpoint', data);
  toast({ title: 'Success', description: 'Operation completed' });
} catch (error) {
  toast({ 
    title: 'Error', 
    description: error.response?.data?.detail || error.message,
    variant: 'destructive' 
  });
}
```

### Rate Limiting

```python
# Implemented in memory_routes.py
from fastapi import HTTPException
from datetime import datetime, timedelta

async def check_rate_limit(agent_id: int, db):
    # Check agent's rate limit
    # Raise HTTPException(429) if exceeded
    pass
```

---

## Gotchas & Important Notes

### ⚠️ Database Connections

- **Never** share connections between main DB and memory DB
- Always use context managers (`with` statements)
- Close connections properly to avoid locks

### ⚠️ Frontend Build

- Use `yarn build` not `npm run build`
- Craco config required for path aliases
- Environment variables must start with `REACT_APP_`

### ⚠️ Docker Networking

- Services communicate via container names
- Backend accessible at `http://backend:8001` from other containers
- Qdrant at `http://qdrant:6333` from backend

### ⚠️ LLM Configuration

- LLM configs must be set via admin UI before use
- Empty responses indicate missing API keys
- Check `llm_configs` table for configuration status

### ⚠️ Qdrant Collections

- Collections created on first use
- Call `POST /api/memory/init` to initialize explicitly
- No automatic migrations for schema changes

### ⚠️ GLiNER Service

- Falls back to LLM extraction if unavailable
- GPU recommended for production
- First request may be slow (model loading)

### ⚠️ Authentication Mix-ups

- Admin endpoints require JWT (`Authorization: Bearer <token>`)
- Agent endpoints require API key (`X-API-Key: <key>`)
- Check endpoint definition if auth fails

---

## File Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| React Pages | PascalCase + `Page.jsx` | `MemorySettingsPage.jsx` |
| React Components | PascalCase + `.jsx` | `MainLayout.jsx` |
| UI Components | kebab-case + `.jsx` | `alert-dialog.jsx` |
| Python Modules | snake_case + `.py` | `memory_services.py` |
| Test Files | `test_` + snake_case + `.py` | `test_memory_auth.py` |

---

## Test Patterns

```python
# Backend test structure
import pytest
from fastapi.testclient import TestClient
from server import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    # Login and return JWT headers
    response = client.post("/api/auth/login", json={
        "email": "admin@promptsrc.com",
        "password": "admin123"
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_entity_types_crud(client, auth_headers):
    response = client.get("/api/memory/config/entity-types", headers=auth_headers)
    assert response.status_code == 200
```

---

## Environment Variables

```bash
# Backend (.env)
JWT_SECRET_KEY=your_secret_key
GITHUB_CLIENT_ID=your_github_client_id
GITHUB_CLIENT_SECRET=your_github_client_secret
QDRANT_URL=http://localhost:6333
GLINER_URL=http://localhost:8002

# Frontend (.env)
REACT_APP_BACKEND_URL=http://localhost
```

---

*Update this file when new patterns are established or conventions change.*
