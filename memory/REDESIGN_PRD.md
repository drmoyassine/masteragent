# Memory System Redesign PRD
> **Saved**: 2026-03-03 | **Status**: Approved & Finalized

See full session: 1fe06f0a-c8b4-46c3-9a25-c49006951cfe

## 4-Tier Memory Model

```
Interactions  →  Memories (Daily Logs)  →  Insights (Private)  →  Lessons (PII-scrubbed)
 (Redis 24h        (NER + embedded,          (LLM compaction         (generalized,
  + PG perm)        append-only)              every N memories)        shareable)
```

## Key Decisions
- **interaction_type** replaces channel — fully expressive
- **PostgreSQL + pgvector** — local by default, Supabase optional via UI
- **No SQLite, no Qdrant**
- **NER runs once** at Tier 0→1 transition only
- **Summarization token-gated** — reuse metadata summary field if present
- **Compaction: count-based per entity type** (configurable N, default 10)
- **Interactions permanent** — immutable event log
- **Rate limiting: per agent** only
- **Chat history → interactions table** (`interaction_type="ai_conversation"`)
- **PII scrub mandatory** before Lesson write
- **Insights** = private distilled patterns (draft→confirmed)
- **Lessons** = PII-scrubbed generalizations (shareable)
- **Single-tenant first**, multi-tenant via `tenant_id` + Supabase RLS later

## Interaction Schema
```
id, timestamp, interaction_type, agent_id, agent_name, content,
primary_entity_type, primary_entity_subtype, primary_entity_id,
metadata (JSONB), metadata_field_map (JSONB), has_attachments,
attachment_refs, source, status
```

## Memory Schema (Tier 1)
```
id, date, primary_entity_type, primary_entity_id, interaction_ids[],
interaction_count, content_summary, related_entities (JSONB),
intents[], relationships (JSONB), embedding (VECTOR 1536),
compaction_count, compacted, created_at
```

## Insights Schema (Tier 2)
```
id, primary_entity_type, primary_entity_id, source_memory_ids[],
insight_type, name, content, summary, embedding (VECTOR 1536),
status (draft|confirmed|archived), created_by, confirmed_by, confirmed_at
```

## Lessons Schema (Tier 3)
```
id, source_insight_ids[], lesson_type, name, content, summary,
embedding (VECTOR 1536), visibility (shared|team|private), tags[]
```

## External Access
- **REST API** — `POST /api/memory/interactions` (X-API-Key)
- **Webhooks** — inbound HMAC-verified + outbound notifications
- **MCP Server** — memory tools for LLM agents
- **Entity Workspace** — admin UI chat scoped to an entity
