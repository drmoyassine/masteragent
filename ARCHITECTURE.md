# MasterAgent — Architecture Reference

> **Last Updated**: 2026-10-26
> **Purpose**: Living reference for technical design, system boundaries, and structural patterns.

---

## 1. High-Level Overview

MasterAgent provides two tightly coupled but domain-separated modules within a single FastAPI runtime:

1. **Prompt Manager** — Git-backed version control for structured AI prompts
2. **Memory System** — 4-tier persistent agent memory with pgvector semantic search

Both modules share a single **PostgreSQL 16 + pgvector** instance. Redis provides caching and queuing for the memory system.

---

## 2. Infrastructure & Routing

### Entry Point
`backend/server.py` — thin entry point responsible only for:
- Loading environment variables
- Mounting CORS middleware
- Registering `APIRouter` instances
- Calling `init_db()` and `init_memory_db()` on startup

### Router Layout

| Namespace | Module | Purpose |
|---|---|---|
| `/api/auth`, `/api/prompts`, `/api/render`, `/api/settings`, `/api/templates` | `backend/routes/` | Prompt Manager |
| `/api/memory/config/*` | `backend/memory/config.py` | Memory admin config |
| `/api/memory/admin/*` | `backend/memory/admin.py` | Memory admin CRUD + stats |
| `/api/memory/interactions`, `/api/memory/memories`, `/api/memory/intelligence`, `/api/memory/knowledge`, `/api/memory/search/*` | `backend/memory/agent.py` | Agent-facing APIs |
| `/api/memory/webhooks/*` | `backend/memory/webhooks.py` | Webhook sources + inbound routing |
| `/api/memory/workspace/*` | `backend/memory/workspace.py` | Per-entity workspace chat |

The `memory/` sub-package assembles all its routers in `memory/__init__.py` under the `APIRouter(prefix="/api/memory")`.

---

## 3. Service Layer

The `backend/services/` package contains all infrastructure-facing business logic, kept at the top level to avoid circular imports with the `memory/` sub-package:

| Module | Responsibility |
|---|---|
| `services/config_helpers.py` | DB-backed config lookups (LLM configs, memory settings, system prompts) |
| `services/llm.py` | OpenAI-compatible LLM call abstraction |
| `services/embeddings.py` | Embedding generation via configured APIs |
| `services/search.py` | pgvector semantic search across memory tiers |
| `services/processing.py` | Text chunking, PII scrubbing, summarization, NER, document parsing (delegates to the liteparse runner when `PARSE_RUNNER_URL`/`PARSE_RUNNER_API_KEY` are set, incl. audio STT) |
| `services/parse_runner.py` | liteparse runner client (parse + transcribe) |
| `services/prompt_safety.py` | Untrusted-content doctrine: `frame_untrusted`, output injection scan, forced-draft resolution (§11) |
| `services/budget.py` | LLM budget caps (TASK-260) |
| `services/alert_delivery.py` | `memory_system_alerts` delivery poller |
| `services/job_safety.py` | Job-level safety gates for queued work |
| `services/memory_lock.py` | Distributed processing locks |
| `services/outbound_webhooks.py` | Outbound webhook dispatch |
| `services/vision_webhooks.py` | Vision webhook handling (secret from migration 006) |
| `services/provider_batch.py` | Provider-side batch operations |

Processing topology: `memory_system/scheduler.py` — a 60-second background loop
that claims each tier job at most once per day via `memory_job_log` — enqueues
into BullMQ; `memory/queue.py` hosts the BullMQ worker (Python `bullmq` package)
driven by a declarative JobSpec registry. The `memory_services.py` shim was
removed in the TASK-257 packageization.

---

## 4. Database Architecture

A single PostgreSQL instance hosts all tables. Schema is split by domain:

### Prompt Manager Tables (`db_init.py`)
- `users`, `api_keys`, `settings`, `prompts`, `prompt_sections`, `prompt_versions`, `templates`, `variables`, `account_variables`, `prompt_variables`

### Memory System Tables (`memory_system/store/db.py`)
- **Config**: `memory_entity_types`, `memory_entity_subtypes`, `memory_lesson_types`, `memory_channel_types`, `memory_agents`, `memory_llm_configs`, `memory_system_prompts`, `memory_settings`, `memory_entity_type_config`
- **Data**: `interactions`, `memories`, `intelligence`, `knowledge`, `entity_profiles`, `memory_agent_entities`, `memory_job_log`, `memory_system_alerts`, `memory_audit_log`, `memory_webhook_sources`

Tier tables carry a dimensionless `embedding public.vector` column plus `embedding_model`/`embedding_dimensions` row metadata (per the frozen `001` baseline; dimensions live on the row, not the column). Migration `005` dimensions `memories.embedding` to `vector(1536)` with an HNSW index on fresh installs to match prod; the other tiers remain dimensionless. SQL migrations are forward-only and live in `backend/migrations/` (applied by the runner in `memory_system/store/migrations.py`).

### Context Managers
- `core.db.get_db_context()` → Prompt Manager DB
- `core.storage.get_memory_db_context()` → Memory DB (both point to the same PostgreSQL instance via `MEMORY_POSTGRES_URL`)

---

## 5. 4-Tier Memory Model

```
Tier 0: Interactions (raw events — POST /api/memory/interactions)
    ↓  (batch processing / compaction)
Tier 1: Memories (chunked, embedded, searchable)
    ↓  (threshold-based compaction)
Tier 2: Intelligence (patterns + trends, draft → confirmed)
    ↓  (admin promotion)
Tier 3: Knowledge (organization-wide skills, playbooks, and trade knowledge)
```

---

## 6. Authentication Matrix

| Consumer | Mechanism | Header | Handler |
|---|---|---|---|
| Human admins | JWT + `users.is_admin` | `Authorization: Bearer <token>` | `memory.auth.require_admin_auth()` |
| AI agents / scripts | API Key | `X-API-Key: <key>` | `core.auth.verify_agent_key()` |
| Webhook sources | HMAC-SHA256 signature | `X-Webhook-Signature: <sig>` | `memory.webhooks` inline validation |

Agent API Keys are SHA-256 hashed before storage. The plaintext key is returned only once at creation time.

### Tenancy posture (TASK-259)

MasterAgent is **single-tenant in code**: there is one `users` table, one admin
identity, and no org/tenant column anywhere in the schema. Isolation comes from
**deployment** — one compose stack per deployment, all state in its own Postgres
volume — not from any row-level tenancy mechanism. Within a deployment,
per-agent entity scoping (`ENFORCE_AGENT_SCOPE` + `memory_agent_entities`
grants) is **authorization for agent keys**, not tenant isolation: it bounds
what one agent key can read, and nothing more. Do not present it (internally or
to consumers) as multi-tenancy; a second tenant means a second deployment.

Related hardening (TASK-259): agent-key PATCHes cannot change entity identity
or lifecycle status (`InteractionUpdateAgent`, `extra="forbid"`); write APIs
claim entities only after a validated access check (`claim_entity_on_write`);
workspace action blocks can only touch intelligence rows the retrieval actually
returned (`allowed_intelligence_ids`); webhook trigger conditions are a frozen
column allowlist (admin API rejects unknown keys with 400, runtime drops and
warns); provider API keys decrypt at the point of use (`resolve_api_key`) so
config dicts never carry plaintext; JWTs carry a `tver` claim matched against
`users.token_version` (missing claim = invalid — clean-slate revocation at
deploy); public signup defaults off; `MCP_SERVICE_KEY` authenticates only as
the non-admin `mcp-service` identity.

---

## 7. Storage Subsystem (Prompt Manager)

The Prompt Manager uses a pluggable storage factory (`storage_service.py`):

- **`GitHubStorageService`** — Active when `github_token` is configured. Commits directly to the user's configured repo/branch.
- **`LocalStorageService`** — Fallback when GitHub is not configured. Persists to `backend/local_prompts/{user_id}/`.

---

## 8. Deployment Topology

```
VPS / EasyPanel
├── masteragent container (supervisord)
│   ├── nginx :80          → serves React build, proxies /api/ → uvicorn
│   └── uvicorn :8001      → FastAPI application
├── postgres container (pgvector/pgvector:pg16)
│   └── :5432 (internal only — not exposed to host)
└── redis container (redis:7-alpine)
    └── :6379 (internal only — not exposed to host)
```

All inter-container communication is via Docker Compose service names (`postgres`, `redis`). Only the `masteragent` service's HTTP port is managed externally (by EasyPanel's override file).

GLiNER is optional, started with `docker compose --profile gliner up`.

---

## 9. DATABASE_URL Resolution Order

`core/db.py` resolves the PostgreSQL connection URL as follows:

1. `DATABASE_URL` env var (if set and not a SQLite URI)
2. `MEMORY_POSTGRES_URL` env var
3. Hard-coded default: `postgresql://postgres:postgres@postgres:5432/memory`

This ensures the backend connects correctly inside Docker even without explicit configuration.

---

## 10. Frontend Conventions

- **Framework**: React 19 SPA, bootstrapped with Create React App + CRACO
- **State**: `ConfigContext.jsx` manages storage mode (`github` vs `local`)
- **Path Alias**: `@/` maps to `frontend/src/`
- **API Layer**: All calls centralized in `frontend/src/lib/api.js`
- **UI Components**: Shadcn/UI component library

*Update this document when significant infrastructure changes are made.*

---

## 11. AI Safety — Untrusted-Content Doctrine (TASK-262)

Governance rule, not just code: **every interaction in MasterAgent enters from
outside** (emails, chats, documents, agent telemetry), so anything distilled
FROM that content is externally-derived by construction. The pipeline
(memory → intelligence → knowledge) treats it accordingly at four layers
(`services/prompt_safety.py` is the single module):

1. **Treat-as-data framing.** Every prompt embedding externally-authored
   content wraps it in `frame_untrusted()` — explicit `<<<UNTRUSTED_DATA>>>`
   delimiters plus a preamble instructing the model to summarize, never obey.
   Payloads containing the delimiters are defanged, so an injected close-tag
   cannot escape the frame structurally. Wired into: memory generation
   (prior context, raw interactions, NER output), summarization, PII scrub,
   intelligence/knowledge synthesis, telemetry reflection, playbook/skill
   generation, consolidation proposals.
2. **No-instructions output invariant.** Distillation OUTPUTS are scanned for
   directive-shaped text (`scan_untrusted_output`) — flag-only, never dropped.
   The marker lands in the row's `processing_errors`/`metadata`
   (`possible_injection`) for human review; intelligence rows carry no such
   column, so that stage logs the flag (durable flags land downstream).
3. **Content trust at artifact creation.** `resolve_creation_status()` forces
   status=`draft` (with `metadata.ai_safety.forced_draft_reason`) for
   skills/playbooks produced by external pathways
   (`telemetry_reflected`/`experiential`/`decomposed`), regardless of the
   `approve_immediately` default (DEC-091 posture: activation is a human
   Settings action). Internal pathways (admin-authored) and informational
   categories keep policy control. Exports carry provenance: SKILL.md
   frontmatter gains `content_trust`/`approval_status`/`forced_draft_reason`,
   and the knowledge-pack INDEX flags status + trust per record (the pack's
   `status=active` default already withholds drafts).
4. **Human-visible alerts.** Forced drafts and other safety events emit
   `memory_system_alerts` rows (upsert-on-code, `delivered_at` reset so the
   TASK-260 delivery poller re-notifies).

**Entity erasure** (`memory_system/maintain/erasure.py`,
`POST /api/admin/entities/{type}/{id}/erase`): admin-JWT-only, `dry_run=true`
by default, audit-logged always. Collects the full footprint BEFORE deleting
(interactions → memories → intelligence → knowledge, including cross-entity
lineage), then in one transaction: deletes owned rows, deletes knowledge only
when NO source survives anywhere, STRIPS the dead lineage ids from other
entities' citing rows (never deletes those), removes source links, the
profile row, and agent grants, and flushes cached interactions.
