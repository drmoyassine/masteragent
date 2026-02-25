# Prompt Manager & Memory System - Product Requirements Document

## Original Problem Statement
Build a **Prompt Manager** (prompt versioning as code using GitHub) extended with an **Agent-Facing Memory System** (API-first memory backend for AI agents).

---

## Core Product Requirements

### Module 1: Prompt Manager (Complete)
- Prompts stored as ordered Markdown files in GitHub
- Versioning via Git branches/folders
- Variable injection with Mustache-style templates
- API-based prompt rendering
- Templates for different agent personas

### Module 2: Agent-Facing Memory System (In Progress)
**Architecture**: API-first microservice where agents push data, UI for configuration and exploration

**Admin Configuration (Complete)**:
- Dynamic schema: Entity types/subtypes, lesson types, channel types
- Agent credentials with API keys
- LLM API configurations per task (summarization, embedding, vision, NER, PII)
- System prompts for LLM operations
- General settings (chunking, lessons, PII, rate limits)

**Ingestion APIs (Pending)**:
- `POST /api/memory/interactions` - Agent submits interaction with text and documents
- Document parsing using vision LLM
- Text chunking (OpenClaw-style)
- Embedding generation and Qdrant storage
- Entity extraction using GLiNER2
- Summarization using configured LLM
- PII scrubbing for shared data

**Retrieval APIs (Pending)**:
- `GET/POST /api/memory/search` - Hybrid semantic search
- `GET /api/memory/timeline/{entity_type}/{entity_id}` - Entity history
- `GET/POST /api/memory/lessons` - Curated lessons

**Explorer UI (Pending)**:
- Search memories and lessons
- View entity timelines
- Browse daily logs
- Edit/approve lessons

---

## Technical Stack

### Backend
- **Framework**: FastAPI
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Vector Store**: Qdrant
- **NER**: GLiNER2 (docker service)
- **LLM**: Admin-configurable (OpenAI, Anthropic, Gemini, custom)
- **PII**: Admin-configurable (Zendata or other)

### Frontend
- **Framework**: React
- **UI**: Tailwind CSS, Shadcn/UI
- **Router**: react-router-dom

### Infrastructure
- **Docker Compose** with services:
  - promptsrc (main app)
  - qdrant (vector database)
  - gliner (NER service)

---

## What's Implemented (December 2025)

### ✅ Complete
1. **Prompt Manager Application**
   - Full-stack app with prompts, sections, versions
   - Templates (Agent Persona, Task Executor, etc.)
   - API keys for external access
   - GitHub integration for storage

2. **Authentication**
   - Email/password signup/login
   - GitHub OAuth
   - JWT tokens
   - User profiles with plans

3. **Memory System - Backend Infrastructure**
   - Database schema for all config tables
   - Memory router integrated into main app
   - Default data seeding (entity types, lesson types, channels, LLM configs)
   - All config API endpoints working

4. **Memory System - Admin Configuration UI**
   - LLM APIs tab - Configure API keys for each task
   - Entities tab - Manage entity types and subtypes
   - Lessons tab - Manage lesson types with colors
   - Channels tab - Manage channel types
   - Agents tab - Create agents with API keys
   - General tab - Chunking, PII, rate limiting settings

5. **Docker Deployment**
   - Dockerfile and docker-compose.yml
   - Qdrant service
   - GLiNER2 service

### 🔄 In Progress
- Agent API endpoints for ingestion (interactions)
- Agent API endpoints for retrieval (search, timeline, lessons)

### ⏳ Pending
- Memory Explorer UI
- OpenClaw Markdown sync
- Automated lesson mining
- Agent activity monitoring
- API rate limiting implementation

---

## API Endpoints

### Prompt Manager
- `/api/auth/*` - Authentication
- `/api/prompts/*` - Prompt CRUD
- `/api/templates/*` - Templates
- `/api/keys/*` - API keys
- `/api/settings` - GitHub config

### Memory System - Config (Complete)
- `/api/memory/config/entity-types` - Entity type CRUD
- `/api/memory/config/entity-subtypes` - Subtype CRUD
- `/api/memory/config/lesson-types` - Lesson type CRUD
- `/api/memory/config/channel-types` - Channel type CRUD
- `/api/memory/config/agents` - Agent management
- `/api/memory/config/llm-configs` - LLM API configs
- `/api/memory/config/system-prompts` - System prompts
- `/api/memory/config/settings` - General settings

### Memory System - Agent APIs (Pending full implementation)
- `POST /api/memory/interactions` - Ingest interaction
- `POST /api/memory/search` - Semantic search
- `GET /api/memory/timeline/{type}/{id}` - Entity timeline
- `GET/POST /api/memory/lessons` - Lessons management

---

## Database Schema

### Existing (Prompt Manager)
- `users` - User accounts
- `settings` - GitHub config per user
- `prompts` - Prompt metadata
- `prompt_versions` - Version tracking
- `templates` - Prompt templates
- `api_keys` - API keys

### New (Memory System)
**Configuration Tables**:
- `memory_entity_types` - Entity type definitions
- `memory_entity_subtypes` - Subtype definitions
- `memory_lesson_types` - Lesson categories
- `memory_channel_types` - Communication channels
- `memory_agents` - Agent credentials
- `memory_llm_configs` - LLM API settings per task
- `memory_system_prompts` - LLM prompts
- `memory_settings` - Global settings

**Data Tables**:
- `memories` - Private interaction records
- `memory_documents` - Parsed attachments
- `memory_document_chunks` - Text chunks
- `memory_lessons` - Curated lessons
- `memories_shared` - PII-scrubbed shared data
- `memory_lessons_shared` - Shared lessons
- `memory_audit_log` - Agent activity

---

## Test Credentials
- **Email**: admin@promptsrc.com
- **Password**: admin123

---

## File Structure
```
/app/
├── backend/
│   ├── server.py             # Main FastAPI app
│   ├── memory_db.py          # Memory system DB
│   ├── memory_models.py      # Pydantic models
│   ├── memory_routes.py      # Memory API routes
│   ├── memory_services.py    # LLM/Vector services
│   └── tests/
│       └── test_memory_system.py
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── MemorySettingsPage.jsx
│   │   │   └── ... (other pages)
│   │   └── lib/api.js
│   └── ...
├── gliner/
│   ├── Dockerfile
│   └── app.py
├── docker-compose.yml
└── memory/PRD.md
```
