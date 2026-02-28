# Architecture Decisions

> **Last Updated**: 2026-02-27
> **Purpose**: Documents key technical decisions, rationale, and trade-offs for the MasterAgent project.

---

## Decision Index

| Decision | Area | Status |
|----------|------|--------|
| [ADR-001](#adr-001-dual-database-architecture) | Database | ✅ Adopted |
| [ADR-002](#adr-002-dual-authentication-system) | Security | ✅ Adopted |
| [ADR-003](#adr-003-sqlite-for-development) | Database | ✅ Adopted |
| [ADR-004](#adr-004-qdrant-for-vector-storage) | Vector Store | ✅ Adopted |
| [ADR-005](#adr-005-gliner2-for-ner) | ML Services | ✅ Adopted |
| [ADR-006](#adr-006-react--shadcnui-for-frontend) | Frontend | ✅ Adopted |
| [ADR-007](#adr-007-fastapi-for-backend) | Backend | ✅ Adopted |
| [ADR-008](#adr-008-pluggable-storage-service) | Storage | ✅ Adopted |
| [ADR-009](#adr-009-automatic-storage-fallback) | Storage | ✅ Adopted |
| [ADR-010](#adr-010-modular-backend-architecture) | Backend | ✅ Adopted |
| [ADR-011](#adr-011-hashed-api-keys) | Security | ✅ Adopted |

---

## ADR-001: Dual Database Architecture

### Context
The application has two distinct concerns:
1. **Prompt Manager**: User accounts, API keys, prompt storage, GitHub integration
2. **Memory System**: Entity types, interactions, lessons, agent configurations

### Decision
Use two separate SQLite databases:
- `backend/prompt_manager.db` - Main application data
- `backend/data/memory.db` - Memory system data

### Rationale
- **Separation of Concerns**: Each module manages its own data independently
- **Isolation**: Memory system can be dropped/reset without affecting prompts
- **Scalability**: Each database can be migrated to separate PostgreSQL instances
- **Development**: Easier to test and debug individual modules

### Trade-offs
| Pros | Cons |
|------|------|
| Module independence | Cross-database queries not possible |
| Easier maintenance | Two connection pools to manage |
| Flexible scaling | Slightly more complex setup |

### Consequences
- Use `get_db_context()` for main DB operations
- Use `get_memory_db_context()` for memory DB operations
- No foreign keys across databases

---

## ADR-002: Dual Authentication System

### Context
The application serves two different user types:
1. **Human Administrators**: Configure system, manage prompts, view analytics
2. **AI Agents**: Consume prompts, store/retrieve memories via API

### Decision
Implement two authentication mechanisms:
- **JWT (Bearer Token)**: For admin/config endpoints via `require_admin_auth()`
- **API Key (X-API-Key header)**: For agent-facing endpoints via `verify_agent_key()`

### Rationale
- **Security Model**: Admins need session-based auth with expiration; agents need long-lived keys
- **Use Case Fit**: JWT supports OAuth/GitHub login flow; API keys are simple for programmatic access
- **Rate Limiting**: API keys enable per-agent throttling

### Trade-offs
| Pros | Cons |
|------|------|
| Purpose-built for each user type | Two auth systems to maintain |
| Clear security boundaries | More documentation needed |
| Supports OAuth integration | Slightly more complex middleware |

### Consequences
- All `/api/memory/interactions/*` endpoints use API key auth
- All `/api/memory/config/*` endpoints use JWT auth
- Rate limiting tied to API key identity

---

## ADR-003: SQLite for Development

### Context
Need a database solution that works locally without infrastructure setup.

### Decision
Use SQLite for development with PostgreSQL support for production.

### Rationale
- **Zero Configuration**: No separate database server to install
- **File-based**: Easy to inspect, backup, and version control
- **Fast Development**: Quick iteration without Docker dependencies
- **Production Path**: SQLAlchemy abstracts database differences

### Trade-offs
| Pros | Cons |
|------|------|
| No setup required | Not suitable for high concurrency |
| Easy to debug | Limited write concurrency |
| Portable | Different behavior than PostgreSQL |

### Consequences
- Use SQLAlchemy ORM for database abstraction
- Test with PostgreSQL before production deployment
- Database files excluded from git (`.gitignore`)

---

## ADR-004: Qdrant for Vector Storage

### Context
Memory system requires semantic search capabilities over text embeddings.

### Decision
Use Qdrant as the vector database for storing and searching embeddings.

### Rationale
- **Performance**: Optimized for high-dimensional vector search
- **Filtering**: Supports metadata filtering alongside vector search
- **Self-hosted**: Can run locally via Docker without cloud dependencies
- **API**: Clean REST and gRPC interfaces

### Trade-offs
| Pros | Cons |
|------|------|
| Fast similarity search | Additional service to manage |
| Metadata filtering | Learning curve for optimization |
| Docker-ready | Memory usage for large collections |

### Consequences
- Qdrant runs on ports 6333 (REST) and 6334 (gRPC)
- Collections created on first use
- Embedding dimension must match configured model

---

## ADR-005: GLiNER2 for NER

### Context
Memory system needs to extract entities (people, organizations, etc.) from text.

### Decision
Use GLiNER2 as a dedicated NER service running in Docker.

### Rationale
- **State-of-the-art**: GLiNER provides accurate entity extraction
- **Zero-shot**: Works without training data for new entity types
- **Isolated**: Runs as separate service, doesn't impact main app
- **Fallback**: System falls back to LLM-based extraction if unavailable

### Trade-offs
| Pros | Cons |
|------|------|
| High accuracy | Additional Docker container |
| No training needed | GPU recommended for performance |
| Configurable entity types | Model loading time on startup |

### Consequences
- GLiNER service runs on port 8002
- Fallback to LLM extraction when service unavailable
- Entity types configurable via admin UI

---

## ADR-006: React + Shadcn/UI for Frontend

### Context
Need a modern, maintainable UI with consistent design system.

### Decision
Use React 18 with Tailwind CSS and Shadcn/UI component library.

### Rationale
- **Shadcn/UI**: Copy-paste components, full customization, no lock-in
- **Tailwind CSS**: Utility-first styling, rapid development
- **React 18**: Latest features, concurrent rendering, good ecosystem
- **Craco**: Custom build configuration without ejecting

### Trade-offs
| Pros | Cons |
|------|------|
| Beautiful, consistent UI | Bundle size consideration |
| Full component control | Manual updates for Shadcn components |
| Accessible by default | Learning curve for Tailwind |

### Consequences
- Path alias `@/` maps to `frontend/src/`
- Components in `frontend/src/components/ui/`
- Use `yarn` for package management (not npm)

---

## ADR-007: FastAPI for Backend

### Context
Need a Python backend that's fast, well-documented, and supports async operations.

### Decision
Use FastAPI with Python 3.11+ for the backend API.

### Rationale
- **Performance**: Async support, automatic OpenAPI docs
- **Type Safety**: Pydantic models for request/response validation
- **Modern Python**: Type hints, async/await, dataclasses
- **Ecosystem**: Excellent integration with SQLAlchemy, Pytest

### Trade-offs
| Pros | Cons |
|------|------|
| Auto-generated API docs | Async learning curve |
| Strong typing | More verbose than Flask |
| Excellent performance | Requires Python 3.11+ |

### Consequences
- All routes defined with Pydantic models
- Automatic Swagger UI at `/docs`
- Async database operations where beneficial

---

## ADR-008: Pluggable Storage Service

### Context
The Prompt Manager originally required GitHub for prompt storage, creating a barrier for users who:
1. Don't have or want a GitHub account
2. Want to evaluate the system quickly without setup
3. Prefer local file system storage for privacy or simplicity

### Decision
Implement a pluggable storage architecture with:
- `StorageService` abstract base class defining the interface
- `GitHubStorageService` implementation (existing GitHub logic)
- `LocalStorageService` implementation (stores in `backend/local_prompts/{user_id}/`)
- `storage_mode` setting per user ('github' or 'local')
- Factory function `get_storage_service(user_id)` to instantiate correct service

### Rationale
- **Lower Barrier**: Users can start with local storage immediately
- **Flexibility**: Switch between storage modes as needs change
- **Backward Compatible**: Existing GitHub users unaffected
- **Testable**: Easy to mock storage for tests
- **Extensible**: Can add S3, GCS, etc. in the future

### Trade-offs
| Pros | Cons |
|------|------|
| No GitHub required | No cloud sync for local mode |
| Easy to extend | More code to maintain |
| User choice | Two code paths to test |
| Quick evaluation | Local files not backed up |

### Consequences
- New endpoint: `POST /api/settings/storage-mode`
- SetupPage now shows storage selection UI
- ConfigContext manages storage state in frontend
- Warning banners indicate storage mode status
- Local storage path: `backend/local_prompts/{user_id}/prompts/{slug}/v1/`

---

## ADR-009: Automatic Storage Fallback

### Context
Even with pluggable storage (ADR-008), users could encounter errors if:
1. They select GitHub storage but haven't configured a GitHub token
2. The GitHub token is revoked or expired
3. They want to quickly test the system without any configuration

### Decision
Implement automatic fallback in `get_storage_service()`:
- Check if `github_token` exists before returning GitHubStorageService
- If no token, return LocalStorageService regardless of `storage_mode` setting
- Log a warning when fallback occurs

### Rationale
- **Graceful Degradation**: System works even with misconfigured settings
- **Better UX**: No cryptic errors when GitHub isn't configured
- **Quick Start**: Users can create prompts immediately after signup
- **Self-Healing**: System recovers automatically from config issues

### Trade-offs
| Pros | Cons |
|------|------|
| No configuration errors | May confuse users expecting GitHub |
| Works out of the box | Silent fallback could hide issues |
| Better first impression | Local files not synced to cloud |

### Consequences
- `get_storage_service()` is the single source of truth for storage
- All endpoints must use this factory function
- Warning logs help identify configuration issues
- Users see warning banners in UI when using fallback

---

## Decision Template

```markdown
## ADR-XXX: [Title]

### Context
[What is the issue that we're seeing that is motivating this decision?]

### Decision
[What is the change that we're proposing and/or doing?]

### Rationale
[Why is this the best solution?]

### Trade-offs
| Pros | Cons |
|------|------|
| [Pro] | [Con] |

### Consequences
[What becomes easier or more difficult because of this change?]
```

---

## ADR-010: Modular Backend Architecture

### Context
`server.py` and `memory_routes.py` grew into massive, tangled monoliths (over 1,500 lines each). Finding code was confusing, database and auth logics were repetitively copy-pasted, and the files were becoming a massive technical debt liability threatening the project's scalability.

### Decision
Break the monolithic scripts into a strictly patterned Domain-Driven folder architecture mapped onto APIRouters:
- `core/` for shared authentication verification and database transaction scopes.
- `routes/` for base Prompt Manager functionality (`auth.py`, `templates.py`, `api_keys.py`, etc.).
- `memory/` for all Agent Memory functionality (`admin.py`, `agent.py`, `config.py`).

### Rationale
Isolates namespaces completely. Reduces `server.py` down to a 75-line minimalist boot loader strictly responsible for registering routers, allowing each domain branch to evolve and be tested concurrently without risking adjacent regression.

### Trade-offs
| Pros | Cons |
|------|------|
| Rapidly accelerates parallel development | More explicit imports needed per-file |
| Code discovery is intuitive and domain-mapped | Higher baseline file overhead |
| Eliminates shared-state god objects | Slower initial navigation for new devs |

### Consequences
- Import models exclusively using relative paths bounded within the domain scope.
- `server.py` may only be modified to mount system middleware or new outer-edge APIRouters.

---

## ADR-011: Hashed API Keys

### Context
Agent API keys were stored directly as plain text within the SQLite `api_keys` relation. While convenient for rapid preview development, this presented a critical, unacceptable security vulnerability. If the simple SQLite DB was captured or leaked, all authenticated agent keys would immediately be fully compromised in production.

### Decision
Migrate Agent Key schema interactions exclusively to one-way `hashlib.sha256` digest comparisons. The original plaintext API Key (`mem_xxxxxx...`) is *only* shown immediately post-creation once and never cached.

### Rationale
Absolute standard cryptographic security practice. If the vector database or SQLite file gets intercepted, zero credentials can be reversed back into workable agent payloads. 

### Trade-offs
| Pros | Cons |
|------|------|
| High security integrity against data exfiltration | Admins cannot recover a lost API key |
| Standardizes cryptographic boundaries | Debugging key mapping is harder without the raw strings |

### Consequences
- If an agent loses their key, an admin must delete the old mapping and generate an entirely new valid API key inside the UI; recovery is permanently impossible.

---

*Add new architecture decisions as they are made to maintain project context.*
