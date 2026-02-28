# MasterAgent Architecture & Engineering Patterns

> **Last Updated**: 2026-03-01
> **Purpose**: Serves as the living root reference document for the technical design, system boundaries, and structural patterns of the MasterAgent (PromptSRC) application.

---

## 1. High-Level System Overview

MasterAgent is built as an **API-first microservice** encompassing two major domains:
1. **The Prompt Manager:** A Git-backed version control system for structured AI prompts, managed via UI and consumed via API.
2. **The Memory System:** A persistent, searchable vector memory bank designed for AI agents to intelligently ingest, track, and recall interaction history, extracted entities, and curated lessons.

These domains share the same FastAPI runtime but maintain strict separation laterally through dual databases, isolated authentication routes, and distinct routing namespaces.

---

## 2. Infrastructure & Modules

### Modular Routing Structure
The monolithic initialization script has been heavily refactored into domain-driven packages to prevent God Classes and isolate business logic.

- `backend/server.py` — The thin entry point. Exclusively responsible for booting FastAPI, loading environments, mounting CORSMiddleware, and registering `APIRouter` instances.
- `backend/core/` — Domain-agnostic utilities shared universally.
  - `core/db.py` — Database context managers and fallback settings.
  - `core/auth.py` — Cryptography, password validation, JWT validation, and the SHA256 API Key verification layers.
- `backend/routes/` — The Prompt Manager domain. Contains controllers for `/auth`, `/prompts`, `/render`, `/settings`, `/variables`, and `/templates`.
- `backend/memory/` — The Memory System domain.
  - `memory/config.py` — Admin configuration endpoints (Entity Types, Agents, Settings).
  - `memory/admin.py` — Statistical read-only reporting endpoints.
  - `memory/agent.py` — High-traffic, API-Key-secured agent interactions, searches, and timelines.

### The Storage Subsystem
Prompts are stored using a **Pluggable Storage Service** factory pattern (`storage_service.py`):
- **GitHub Node (`GitHubStorageService`)**: When a user provides a PAT (Personal Access Token), prompts are actively committed directly to the remote repository.
- **Local Fallback (`LocalStorageService`)**: Automatically cascades back to local disk persistence inside `backend/local_prompts/{user_id}` when GitHub is disconnected or the token is invalid. 

---

## 3. Databases & Persistence

The application employs a strict **Dual Database Architecture** to prevent the Prompt Manager and the Memory Modules from entangling state models.

1. **Main Database (`prompt_manager.db`)**
  - Managed by: `backend/db_init.py`
  - Purpose: Global User Accounts, API Keys, System Settings, Variable definitions, and Prompt metadata.
2. **Memory Database (`data/memory.db`)**
  - Managed by: `backend/memory_db.py`
  - Purpose: Entity logs, Daily interactions, Curated Lessons, and Agent identity mappings.
  - *Note*: Operates alongside Qdrant vectors; strict boundaries exist between raw private interaction states and sanitized shared state pools.

---

## 4. Authentication Matrix

Authentication mechanisms are split linearly based on the intended consumer:

| Consumer Type | Auth Mechanism | Header Spec | Handled By |
| --- | --- | --- | --- |
| **Human Admins/Builders** | JWT (JSON Web Tokens) | `Authorization: Bearer <token>` | `core.auth.require_admin_auth()` |
| **AI Agents/Scripts** | Cryptographic API Key | `X-API-Key: <key>` | `core.auth.verify_agent_key()` |

**Security Note:** Agent API Keys are one-way hashed natively within the `api_keys` relation using `hashlib.sha256`. At no point is a plaintext API key stored or logged within the backend. Validation is handled by dynamically hashing incoming payload variants and verifying absolute match properties.

---

## 5. Deployment Topology

The application is deployed via Docker Compose orchestrating multiple cohesive components:

- **PromptSRC Container**: Runs Nginx proxy routing to the React Frontend (`:80`) and standardizes Uvicorn backend APIs (`:8001`).
- **Qdrant Vector Database**: A high-performance Rust engine bound to the private network handling complex metadata filtering over high-dimensional tensor matrices (`:6333`).
- **GLiNER2 Name Entity Recognition (Optional)**: A dedicated Python microservice providing zero-shot dynamic entity boundary recognition (`:8002`). The backend gracefully falls back to OpenAI function-calling if this service is inaccessible. 

---

## 6. Frontend Conventions (React)
- **Framework**: SPA via React 18, bootstrapped by a highly modified Vite/Craco pipeline to support deep path alias routing (`@/*` mapping strictly to `frontend/src/*`).
- **State Routing**: `ConfigContext.jsx` acts as the root boundary defining whether a user operates against the GitHub layer (`storageMode === 'github'`) or local caching (`storageMode === 'local'`).
- **Data Mutation**: Read/Write actions aggressively invoke local `.catch()` handlers piped explicitly into Shadcn's `toast` notification system for guaranteed visibility.

*This document should be continually updated as significant infrastructural pivots or structural codebase patterns emerge during master development.*
