# Knowledge Tier Productionization Plan

> **Status**: In progress — started 2026-07-05
> **Goal**: Make Tier 3 (knowledge) generation actually run in production, close the "learning by doing" loop, and stabilize the schema so it can later serve as the reference contract for the MasterMemory npm framework (see [mastermemory-npm-migration.md](mastermemory-npm-migration.md)).

---

## 1. Problem Statement

The memory pipeline runs in production as an education-abroad counselor (WhatsApp + email, Supabase CRM, n8n workflows). Tiers 0–2 work:

```
Interactions → Memories → Intelligence     ✅ working in prod
Intelligence → Knowledge                   ❌ ZERO rows ever created
Knowledge → agent context (get-context)    ⚠️ wired, but nothing to serve
```

The agent is not learning by doing. The plumbing for Tier 3 exists (~80%) but is gated shut by configuration defaults and silent failure modes, and the playbook/skill sub-pathway crashes on every run.

## 2. Root-Cause Diagnosis

Ranked by likelihood. Gates 1 and 2 are independent — production is probably blocked on **both**.

### Gate 1 — The confirmation bottleneck (structural)

- `run_knowledge_check` ([backend/memory_knowledge.py](../backend/memory_knowledge.py)) only consumes intelligence with `status = 'confirmed'`, needing ≥ `knowledge_threshold` (default 5) unused items per entity type.
- `insert_intelligence` ([backend/memory_db_writes.py](../backend/memory_db_writes.py)) writes `status = 'draft'` unless the entity type has `intelligence_auto_approve = TRUE`.
- `intelligence_auto_approve` **defaults to `FALSE`** ([backend/memory_db.py](../backend/memory_db.py), `memory_entity_type_config`).
- Nobody confirms drafts in the admin UI as part of the ops flow.

→ The pipeline is structurally dead above Tier 2: drafts accumulate forever, the threshold is never crossed, the knowledge check runs daily and finds nothing.

### Gate 2 — Missing LLM config = silent no-op

- `call_llm` ([backend/services/llm.py](../backend/services/llm.py)) returns `""` (empty string) when no active config matches the task type.
- `generate_knowledge_from_intelligence` then hits `json.loads("")`, which raises, is caught, logged, and swallowed. **No error surfaces anywhere.**
- The knowledge path resolves its model via: active pipeline node with `pipeline_stage = 'knowledge'` → fallback to `task_type = 'knowledge_generation'` row in `memory_llm_configs`. If neither exists, silent failure.
- `playbook_generation` and `skill_generation` resolve **only** by `task_type` (no pipeline-node path). If the admin UI never created rows for these task types, that branch has no model at all.

### Gate 3 — Playbook/skill pathway crashes (confirmed bugs)

1. **`memory_playbooks.py` `_process_cluster` (~line 180)**: `datetime.fromisoformat(min_ts)` where `min_ts` is already a `datetime` (psycopg returns objects for `TIMESTAMPTZ`) → `TypeError` on every qualifying cluster, swallowed by the caller's catch-all. The entire experiential→playbook pathway silently produces nothing.
2. **`memory_consolidation.py` `_refine_playbook` (~line 90)**: SELECTs `name, content, metadata, merge_count` but then checks `row.get("category") != "playbook"` — `category` is never selected → always `None` → always returns early. Playbook refinement after merges is a permanent no-op.

### Gate 4 — JSON parsing fragility (not a blocker, but a landmine)

All Tier 2/3 LLM calls do a bare `json.loads(result_text)`: no code-fence stripping, no `response_format: json_object`. The intelligence prompts happen to produce clean JSON in prod; the knowledge default prompt has no such battle-testing. One markdown fence kills the run silently.

### Related bug (already chipped): orphan sweeper re-processing

`run_orphan_sweeper` re-enqueues every interaction `status='pending'` older than 6h — but pending is the *normal* state until daily memory generation. `process_interaction` doesn't guard on `is_enriched`, so nightly re-runs duplicate attachment text, re-bill vision/embeddings, and re-fire `evaluate_outbound_webhooks` (likely root cause of the observed duplicate-webhook payloads). Fix: sweeper filters `is_enriched = FALSE` + make `process_interaction` idempotent.

## 3. What Is Already Wired (validated)

| Piece | Status |
|---|---|
| Daily trigger enqueues `generate_knowledge` (memory_tasks.py background loop) | ✅ present, same queue that successfully runs intelligence |
| Thresholds (global `knowledge_threshold`, per-entity-type `knowledge_extraction_threshold`) | ✅ present |
| PII scrub → synthesize → dedup vs prior knowledge → embed → insert | ✅ complete code path |
| Manual trigger endpoint | ✅ `POST /api/memory/trigger/run-Knowledge-check` — **note the capital K**; the README's lowercase route 404s |
| Consumption: `GET /api/memory/get-context` returns active shared knowledge (top 30 by quality) | ✅ zero further wiring needed once rows exist |
| Signal validation against entity-type-defined knowledge signals | ✅ present |

## 4. What Is Genuinely Missing

1. **An approval policy decision** — nobody decided whether Tier 2→3 is human-gated or automatic, so it defaulted to "gated and nobody is gating."
2. **Observability** — every failure mode is a swallowed log line. No way to see "knowledge check ran, found 0 confirmed items, threshold 5" from the admin UI.
3. **Any test of the knowledge path** — Tiers 0–2 were debugged by production pressure; Tier 3 never had that.
4. **Relevance-matched retrieval** — get-context returns a global top-30 by quality score regardless of conversation context. Acceptable for v1 with few records; wrong at scale (defer).

## 5. Execution Plan

Order matters. Steps 1–2 are diagnosis/fixes; 3–4 open the gates; 5–7 verify and harden.

### Step 1 — Diagnose prod (run these first)

```sql
-- Gate 1: are we drowning in drafts?
SELECT status, COUNT(*) FROM intelligence GROUP BY status;

SELECT entity_type, intelligence_auto_approve, knowledge_extraction_threshold
FROM memory_entity_type_config;

-- Gate 2: do the LLM config rows even exist?
SELECT task_type, pipeline_stage, is_active FROM memory_llm_configs
WHERE task_type IN ('knowledge_generation','playbook_generation','skill_generation')
   OR pipeline_stage = 'knowledge';
```

### Step 2 — Land the bug fixes

- [ ] Orphan sweeper idempotency (`is_enriched` guard in sweeper + `process_interaction`)
- [ ] Playbook `fromisoformat` crash (handle `datetime` objects)
- [ ] `_refine_playbook` missing `category` column in SELECT

### Step 3 — Set the approval policy

**Recommendation**: set `intelligence_auto_approve = TRUE` for the contact entity type. Intelligence quality is already passively reviewed through daily use; a human gate that nobody operates is worse than no gate. Keep draft mode as the default for *new* entity types.

- [ ] Enable auto-approve for the production entity type(s)
- [ ] Bulk-confirm the existing draft backlog (admin bulk endpoints exist)

### Step 4 — Create the missing LLM configs

- [ ] Pipeline node for stage `knowledge` with an inline prompt (mirror how the working intelligence stage is configured)
- [ ] `task_type = 'playbook_generation'` row
- [ ] `task_type = 'skill_generation'` row

### Step 5 — Harden JSON parsing

One shared helper used by all Tier 2/3 LLM call sites:
- Strip markdown code fences before `json.loads`
- Send `response_format: {"type": "json_object"}` when the provider supports it
- On parse failure, log the **raw LLM output** (currently lost)

### Step 6 — Fire and verify end-to-end

1. `POST /api/memory/trigger/run-Knowledge-check` (capital K)
2. Verify knowledge rows created (`SELECT * FROM knowledge ORDER BY created_at DESC`)
3. Verify they appear in `get-context` payloads
4. **Last mile**: confirm the n8n counselor workflow actually renders the `knowledge` array from the get-context payload into the agent's system prompt. The API returns it; consumption must be verified in the workflow.

### Step 7 — Add pipeline observability

New table `memory_pipeline_runs` written by every check/generation run:

| column | example |
|---|---|
| `job` | `knowledge_check`, `intelligence_extraction`, `playbook_extraction` |
| `outcome` | `created`, `skipped`, `failed` |
| `reason_code` | `below_threshold`, `no_confirmed_intelligence`, `llm_config_missing`, `parse_error` |
| `detail` | `{"entity_type": "contact", "count": 3, "threshold": 5}` |

Surface in the System Monitor page. This is the difference between this month's mystery and never having this mystery again.

## 6. Schema Stabilization (feeds the npm migration)

Once knowledge generates and stabilizes:

- [ ] Finish the naming migration (`lessons`→`knowledge`, `insights`→`intelligence` remnants in routes, ARCHITECTURE.md, admin UI labels)
- [ ] Remove git-tracked OneDrive conflict copies (`backend/*-DESKTOP-3M67GL2.py`) and gitignore the pattern
- [ ] Freeze the four-tier schema and document it as the contract
- [ ] Capture **golden fixtures**: real (PII-scrubbed) inputs/outputs at each tier boundary from prod — these become the conformance test suite for the TypeScript port
- [ ] Update README (stale `memory/services/` reference) and ARCHITECTURE.md (still describes `insights`/`lessons` tables; missing playbooks, skills, consolidation, Hermes)

## 7. Deferred (do not block on these)

- Relevance-matched knowledge retrieval in get-context (semantic match / playbook `trigger_conditions` evaluation at serve time)
- Automated `outcome_signal` feedback (currently only the manual admin feedback endpoint writes it, despite carrying 30% of quality-score weight)
- Decay-logic fixes (`decay_min_interactions_since_trigger` read but unused; `metadata->>'entity_type'` never matches skills or plain knowledge records)
- `compact_entity` self-fallback typo: `get_llm_config("intelligence_generation") or get_llm_config("intelligence_generation")`
- Consolidation merge improvements (union `source_intelligence_ids` provenance instead of retire-and-count)
