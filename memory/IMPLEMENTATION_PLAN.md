# Memory System Implementation Plan
> **Saved**: 2026-03-03 | **Based on**: Redesign PRD (session 1fe06f0a)

See full PRD: `masteragent/memory/REDESIGN_PRD.md`

## Phase 1 — Infrastructure: PostgreSQL + pgvector + Redis ✅/🔄
- Remove Qdrant, replace with pgvector in PostgreSQL
- Add local PostgreSQL + Redis to docker-compose
- New `backend/core/storage.py` pluggable storage factory
- Fix: `start_background_tasks()` never called in server.py
- Fix: agent key hash comparison bug in `memory/auth.py`

## Phase 2 — New Interaction Schema & Ingestion API
- New `interactions` table (Tier 0 schema)
- Redis 24h write-through cache on ingest
- Immediate document parsing on ingest
- New `InteractionCreate` Pydantic model

## Phase 3 — Daily Memory Generation Job
- Background loop: NER + summarization + embedding
- `metadata_field_map` support for metadata extraction
- Token-gated summarization (reuse external summary if present)
- Per-entity-type NER confidence threshold

## Phase 4 — Compaction: Insights + Lessons
- Count-based compaction trigger per entity type
- LLM insight generation (`task_type="insight_generation"`)
- PII scrub + generalization → Lesson promotion
- Admin endpoints: CRUD for insights and lessons
- Per-entity-type config UI

## Phase 5 — Semantic Search (pgvector)
- Replace Qdrant queries with pgvector cosine `<=>` operator
- Fan-out search across memories + insights + lessons
- SQL LIKE fallback when embedding unavailable

## Phase 6 — Webhooks
- Webhook source registration (admin JWT)
- Inbound events: HMAC-SHA256 verification + normalization
- Outbound notifications on Insight/Lesson creation

## Phase 7 — Supabase Connection
- Settings UI: Supabase URL + Service Role Key input
- Storage factory switch on connect
- Clean-start policy on switch

## Phase 8 — Entity Workspace (Chat Interface)
- `POST /api/memory/workspace/{entity_type}/{entity_id}/chat`
- Context window: memories + insights + lessons + Prompt Manager skill
- Structured actions: create_insight, update_insight, promote_to_lesson
- Logged as `interaction_type="ai_conversation"`
