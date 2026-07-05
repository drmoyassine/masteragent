# MasterMemory — npm Framework Migration Plan

> **Status**: Planned — blocked on [knowledge-tier-productionization.md](knowledge-tier-productionization.md)
> **Goal**: Extract the 4-tier experiential-learning memory architecture into an installable TypeScript framework. Users `npm create mastermemory`, pick a database (Supabase/Postgres, libSQL, SQLite), get the schema rolled into their own project (e.g. a `mastermemory` schema in their own Supabase instance, pgvector optional), and run the pipeline on their own infrastructure — including Supabase Edge Functions.

---

## 1. Honest Framing

**This is a rewrite, not a wrap.** The FastAPI backend cannot be "abstracted" into an npm package — Supabase Edge Functions run Deno/TypeScript, and none of the Python survives. What transfers is the valuable part:

- The four-tier schemas and their semantics (interactions → memories → intelligence → knowledge)
- Trigger/threshold logic (daily generation, threshold-based memory, compaction, knowledge accumulation)
- Prior-context injection strategy ("established facts, do NOT repeat" at every tier)
- Dedup, quality-scoring, merge/decay math
- The prompt templates, once battle-tested in prod

The Python system becomes the **reference implementation**. We port the *contract*, verified by golden fixtures captured from production (see productionization plan §6).

### Why not port now

1. Tier 3 has never run in production — every pipeline behavior fixed during productionization is a spec decision the port inherits for free. Porting now means porting the bugs.
2. The schema/naming migration (`lessons`→`knowledge`, `insights`→`intelligence`) is still in flight.

### Design break: code-first config

The DB-backed config system (`memory_llm_configs`, pipeline stages, admin-UI-managed prompts) **does not port**. It is the single biggest source of silent failure in the current system (missing config row → empty LLM response → swallowed parse error) and the wrong idiom for a library. The framework uses a typed config object:

```ts
// mastermemory.config.ts
export default defineMemory({
  db: supabaseAdapter({ schema: "mastermemory", vectors: "pgvector" }),
  llm: openAICompatible({ baseURL: ..., apiKey: ..., model: "gpt-4o-mini" }),
  embedding: { model: "text-embedding-3-small", dims: 1536 },
  entityTypes: {
    contact: {
      intelligenceSignals: [...],
      knowledgeSignals: [...],
      thresholds: { intelligence: 10, knowledge: 5 },
      autoApprove: { intelligence: true },
    },
  },
  prompts: { /* overrides; sane defaults ship in core */ },
  hooks: { onAttachment, extractEntities, scrubPII },  // optional
});
```

Sane defaults everywhere; a missing optional feature is *off*, never silently broken.

## 2. Package Architecture

Monorepo, TypeScript, targeting Node + Deno + edge runtimes (core rule: `fetch`-based I/O only, no Node-only deps in core):

```
mastermemory/
├── packages/
│   ├── core/                 # @mastermemory/core — runtime-agnostic pipeline engine
│   │   ├── tiers/            #   ingest, generateMemories, extractIntelligence, buildKnowledge
│   │   ├── scoring/          #   quality score, dedup, decay, consolidation
│   │   ├── prompts/          #   default templates + {{ variable }} injection
│   │   └── drivers/          #   interfaces only: Storage, Vector, Queue, Lock, Clock
│   ├── adapter-postgres/     # node-postgres; pgvector optional (flag)
│   ├── adapter-supabase/     # supabase-js; schema-scoped tables (mastermemory.*)
│   ├── adapter-libsql/       # libSQL/Turso; native vector type
│   ├── adapter-sqlite/       # better-sqlite3 + sqlite-vec, or JS cosine fallback
│   ├── server/               # @mastermemory/server — Hono HTTP surface (Deno/Node/Bun/edge)
│   └── create-mastermemory/  # npm create scaffolder
```

### Driver decisions (mapped from the Python system)

| Concern | Today (Python/VPS) | Framework |
|---|---|---|
| Queue | BullMQ + Redis | `QueueDriver`: Postgres jobs table with `FOR UPDATE SKIP LOCKED` (Supabase: pgmq/Queues); inline synchronous driver for SQLite/small deployments; BullMQ optional on Node |
| Scheduler | 60s asyncio loop in-process | Single idempotent `tick()` entry point. Supabase: pg_cron → edge function. Node: node-cron. Or manual invocation. The existing "has today's job run" job-log logic fits this shape directly |
| Entity lock | Redis `SET NX` + TTL | Postgres advisory locks / job-row transaction; SQLite is single-writer anyway. **Redis dependency dropped entirely** |
| Vector search | pgvector raw SQL | `VectorDriver`: pgvector · libSQL native vectors · sqlite-vec · brute-force JS cosine fallback (fine < ~50k rows). On/off flag per install |
| LLM calls | httpx → OpenAI-compatible | Same via `fetch` — ports almost line-for-line. Add fence-stripping + `response_format` hardening from day one |
| Vision/OCR | PyMuPDF in-process | **Not portable.** Optional `onAttachment` hook → any HTTP service (including the existing Python container) |
| NER | GLiNER container / LLM fallback | Optional `extractEntities` hook; LLM-based default in core |
| PII scrubbing | zendata / LLM | Optional `scrubPII` hook; LLM-based default in core |
| Admin UI | React SPA | Out of scope for v1; the HTTP surface exposes the same admin endpoints so the existing UI (or a future one) can attach |

### HTTP surface (`@mastermemory/server`)

Hono app mirroring today's agent-facing API so existing n8n workflows can migrate by swapping the base URL:

- `POST /interactions` (ingest, attachments via hook)
- `GET /get-context` (pending interactions + memories + intelligence + knowledge)
- `POST /search/semantic`, `POST /search/fulltext`
- CRUD on memories / intelligence / knowledge
- `POST /tick` (scheduler entry point)
- Admin triggers (generate-memories, intelligence-check, knowledge-check)

Auth: API-key header (same `X-API-Key` model), pluggable verifier.

### Scaffolder (`npm create mastermemory`)

Prompts: which DB · pgvector on/off · schema name (default `mastermemory`) · tiers to enable. Emits:

1. Migration SQL files into the user's project (Supabase users apply via their own migration flow, in their own project)
2. Typed `mastermemory.config.ts`
3. For Supabase: an edge-function template + pg_cron setup snippet for `tick()`

## 3. Scope

### v1 (the proven core loop only)

- Interactions → memories → intelligence → knowledge pipeline
- Threshold + scheduled triggers, prior-context injection, signal validation
- Semantic + fulltext search, get-context
- `tick()` scheduler, Postgres/Supabase adapters, scaffolder
- Pipeline run log (observability learned from productionization)

### v2+ (plugins — deliberately deferred; least proven in our own prod)

- Playbooks & skills extraction (union-find clustering + AI telemetry)
- Hermes (admin natural-language instruction → knowledge records)
- Consolidation / decay / quality recompute
- Outbound + inbound webhooks
- libSQL/SQLite adapters (pure adapter work once driver interfaces are proven)
- Admin UI package

## 4. Phased Roadmap

| Phase | What | Effort | Gate |
|---|---|---|---|
| 0 | Productionize knowledge tier in Python system | days | see productionization plan |
| 1 | Stabilize the contract: freeze schema, finish naming migration, capture golden fixtures from prod | 1–2 wks (overlaps 0) | knowledge generating in prod |
| 2 | Build monorepo: core + postgres/supabase adapters + server + scaffolder | 4–6 wks focused | Phase 1 fixtures pass as conformance tests |
| 3 | Dogfood: run the counselor workload on `@mastermemory/*` in our own Supabase project; FastAPI admin UI stays as optional console over the same schema | 2+ wks | Phase 2 shipped |
| 4 | v2 plugins + remaining adapters, public release | ongoing | Phase 3 stable |

## 5. Open Questions (decide before Phase 2)

- **Package naming/registry**: `mastermemory` vs `@mastermemory/*` scope availability on npm
- **Embedding dimensions**: fixed at config time vs flexible per-table (current Python allows flexible `vector` columns at the cost of no HNSW index — decide indexing strategy per adapter)
- **Multi-tenancy**: single-tenant per schema (current model) vs tenant column — single-tenant per schema recommended for v1 (matches "roll your own schema" story)
- **Prompt Manager relationship**: the Prompt Manager module stays a separate product; the framework's prompt config accepts plain strings/templates, with an optional integration to fetch from a Prompt Manager instance later
- **License** (current repo is MIT) and whether the reference Python implementation stays public
- **Agent-skills interchange**: adopt the open SKILL.md format (Anthropic agent-skills spec) as an **export format** for `knowledge.category='skill'` (and playbooks-as-procedural-skills) so extracted skills are directly consumable by Claude Code and other SKILL.md-compatible agents — internal storage stays relational
