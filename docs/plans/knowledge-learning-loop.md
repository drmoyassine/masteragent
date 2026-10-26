# Plan: Closing the Knowledge Learning Loop

**Status:** Implemented — phases 0–3 shipped behind settings flags (capture ON, attribution ON, blend OFF at 0.0)
**Date:** 2026-10-26
**Depends on:** unified knowledge table, `recalculate_knowledge_quality` (PR #48-era), nightly scheduler + per-day claims, `memory_pipeline_runs` ledger, migration 007 (playbook removal)

---

## 1. Goal

The knowledge tier produces records but nothing learns from whether they *work*. Outcome signal exists (`success_count`/`failure_count`, `recalculate_knowledge_quality` computes `outcome = (s+2)/(s+f+4)`) but is only fed by a manual admin endpoint, and `quality_score` is consumed by **zero** retrieval or consolidation paths. This plan closes the loop with three pieces:

1. **Usage capture** — record when a knowledge record is actually injected into agent context
2. **Outcome attribution** — a nightly batch job that earns success/failure from signals that already exist downstream (no online judge, no ground-truth requirement)
3. **Consumption** — quality-weighted retrieval re-ranking, consolidation priors, and retirement candidates

**Non-goals:** online/in-loop LLM judging, automatic skill patching (refinement stays proposal-based per the DEC-091 draft doctrine), any behavior change on the hot path before data exists (phased rollout, §7).

**Why this shape:** every organ already exists. The loop closes by wiring, not by adding a subsystem — which is also the paper claim ("experiential learning without experience bloat", see §10).

---

## 2. Component A — Usage capture

### Schema (migration `008_knowledge_learning_loop.sql`)

```sql
CREATE TABLE knowledge_usage_events (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_id  UUID NOT NULL,            -- knowledge.id (no FK: knowledge rows are never hard-deleted, but stay lenient)
    interaction_id UUID,                    -- the interaction this context served (nullable for bare search calls)
    agent_id      TEXT,
    pathway       TEXT NOT NULL,            -- 'get_context' | 'semantic_search' | 'fulltext_search'
    entity_type   TEXT,
    entity_id     TEXT,
    rank          INT,                      -- position in the injected/returned list (1-based)
    attributed_at TIMESTAMPTZ,              -- set by the attribution job (idempotency cursor)
    outcome       TEXT,                     -- NULL until attributed; 'success' | 'failure' | 'no_signal'
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_kue_knowledge ON knowledge_usage_events (knowledge_id, created_at);
CREATE INDEX idx_kue_unattributed ON knowledge_usage_events (created_at) WHERE attributed_at IS NULL;
CREATE INDEX idx_kue_interaction ON knowledge_usage_events (interaction_id);

-- Denormalized for admin stats / retirement scans without an aggregate per request.
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0;
```

### Capture points

| Path | Where | interaction_id |
|---|---|---|
| `GET /api/memory/get-context` | `memory/agent.py::get_context` (~line 566), after the knowledge list is assembled | the interaction currently being ingested/served (already in scope in this endpoint) |
| `POST /api/memory/search/semantic` | `search_knowledge_by_vector` call sites | NULL |
| `POST /api/memory/search/fulltext` | `search_knowledge_by_fulltext` call sites | NULL |

Rules:

- Capture **active, non-draft** records only — drafts never served, never counted.
- Batch-insert per request (one `executemany` via `asyncio.to_thread`), capped by `knowledge_learning_max_events_per_call` (default 50) — the top-ranked records only.
- **Best-effort, never raises**: a capture failure must not fail the retrieval (same doctrine as `log_pipeline_run`).
- `get-context` fires per conversation turn; that is the honest usage signal (repeated injection = repeated evidence of relevance), but the cap keeps hot entities bounded.

---

## 3. Component B — Outcome attribution job

New scheduled job `knowledge_outcome_attribution` on `knowledge_ops`, nightly, per-day claim via `claim_job_date` (same pattern as `intelligence_schedule`), plus a `JobSpec` in `memory/queue.py` and an admin trigger (`POST /api/memory/admin/trigger/knowledge-outcome-attribution`). Every run appends a `memory_pipeline_runs` row (`job='knowledge_outcome_attribution'`, `records_created` = events attributed).

### Signals (phase 1 — conservative, no LLM)

For each unattributed event `(K, I, entity)` older than `knowledge_learning_min_signal_age_hours` (default 6h — let the interaction settle):

1. **Manual feedback (authoritative).** Existing `POST /knowledge/{id}/feedback` already increments counters directly; unaffected.
2. **Negative — lessons_learned echo.** If a `lessons_learned` knowledge record L becomes active whose `source_intelligence_ids` trace to intelligence derived from interactions of the **same entity** within `knowledge_learning_negative_window_days` (default 7) after I, **and** L shares ≥1 signal with K **or** cosine(K.embedding, L.embedding) ≥ `knowledge_learning_negative_similarity` (default 0.80) → event K = `failure` (provisional, see below).
3. **Positive — confirmed recurrence.** The telemetry reflection dedup-confirm path (`distill/telemetry.py`, `success_count + 1` on pattern recurrence) stays as-is. Additionally: if K is retrieved again for the same entity after ≥7 days with **no** intervening negative signal → event = `success`. Weak but directionally safe, and Laplace-smoothed anyway.
4. **No signal** → `outcome='no_signal'`, still marked attributed (do not rescan forever).

### Semantics

- Attribution writes the outcome **on the event row** and appends an audit row to the same table (the event row *is* the ledger — no separate outcomes table), then updates `knowledge.success_count`/`failure_count` and `usage_count` accordingly, then calls `recalculate_knowledge_quality(knowledge_id)`.
- **Provisional flags:** signal-derived (non-manual) attributions are recorded with their signal type; a future admin feedback on the same record overrides via the counters (manual endpoint keeps incrementing — the Laplace prior absorbs small disagreements).
- **Idempotent:** events are processed exactly once (`attributed_at IS NULL` filter + per-day job claim). Re-runs after failure resume from the cursor.
- All DB work in `asyncio.to_thread` (504 doctrine).

---

## 4. Component C — Consumption

### 4.1 Retrieval re-ranking (quality as tie-breaker)

In `search_knowledge_by_vector` / `search_knowledge_by_fulltext` (and the get-context knowledge assembly), final ordering becomes:

```sql
ORDER BY (1 - (embedding <=> :q)) + :w * COALESCE(quality_score, 0.5) DESC
```

- `knowledge_retrieval_quality_weight` (default **0.0** = off; ships disabled).
- Design constraint: `w` is small by construction (recommended 0.05–0.10). Similarity selects the candidate set; quality only **reorders near-equivalent records**. It must never pull a dissimilar record into results. Full-text path: same blend on `ts_rank`-normalized score.
- Missing quality (never scored) defaults to the Laplace prior 0.5 — new records are neither advantaged nor buried.

### 4.2 Consolidation priors

- **Canonical selection:** when the LLM merge proposal is ambiguous between equally-valid sources, prefer the record with higher `quality_score` (existing `_validate_source_set`/apply path; a one-line comparison in canonical selection).
- **Retirement candidates (the forgetting half):** the hygiene preview (`analysis_only`/`proposal_only` modes) gains a candidate class: `status='active' AND created_at < now() - knowledge_learning_retire_after_days (default 90) AND usage_count = 0 AND quality_score < 0.40`. These become **proposals in manual review** — never silent deletes, never auto-applied (hygiene stays `manual_only` until the user flips it).

### 4.3 Skill refinement proposals

When a skill record accumulates ≥`knowledge_learning_refine_min_failures` (default 2) provisional failure attributions, the hygiene run emits an **update proposal** ("skill X contradicted by lesson L — revise trigger/procedure?") into the existing preview/apply flow. No live patching; DEC-091 doctrine intact.

---

## 5. Settings (new keys, via MemorySettings)

| Key | Default | Purpose |
|---|---|---|
| `knowledge_learning_usage_capture` | `true` | capture events (cheap, safe to ship on) |
| `knowledge_learning_max_events_per_call` | `50` | hot-path bound |
| `knowledge_learning_attribution_enabled` | `true` | nightly job no-ops when false |
| `knowledge_learning_negative_window_days` | `7` | lessons_learned echo window |
| `knowledge_learning_negative_similarity` | `0.80` | K↔L cosine gate |
| `knowledge_learning_min_signal_age_hours` | `6` | settle time before attribution |
| `knowledge_learning_retire_after_days` | `90` | unused+low-quality retirement scan |
| `knowledge_learning_refine_min_failures` | `2` | skill refinement proposal trigger |
| `knowledge_retrieval_quality_weight` | `0.0` | retrieval blend (off until §7 phase 2) |

---

## 6. Observability

- `memory_pipeline_runs` rows for `knowledge_outcome_attribution` (attributed counts, signal breakdown in `detail`).
- Admin stats (`/admin/stats`): knowledge gains `usage_covered` (share of active records with ≥1 usage event in 30d) — this is the "is retrieval even reaching my knowledge?" dial that today has no answer.
- First diagnostic of the 51-failures class: attribution detail distinguishes "record never retrieved" from "retrieved and failed".

---

## 7. Rollout (phased, each independently revertible)

| Phase | Ships | Default state | Exit criteria |
|---|---|---|---|
| 0 | Migration 008 + usage capture + job scaffolding | capture ON, attribution ON, blend OFF | 2 weeks of events; no latency regression on get-context |
| 1 | Attribution active in nightly window | counters filling, ledger auditable | spot-check 20 attributions against reality; false-negative rate acceptable |
| 2 | Retrieval blend | `knowledge_retrieval_quality_weight` 0.05 | A/B: get-context answer quality unchanged or better; no dissimilar-record leakage |
| 3 | Retirement candidates + skill refinement proposals | hygiene `manual_only`, proposals only | user reviews first proposal batch |

Rollback = set capture/attribution flags false + weight 0; table is inert.

---

## 8. Testing

- **Unit:** attribution window/signal logic (echo, similarity gate, no_signal cursor); Laplace prior for unscored records; blend ordering (`w=0` preserves existing order exactly — pin this).
- **Integration (hermetic):** migration 008 forward on fresh + 006-state DB; get-context writes events (capped, active-only); job idempotent under re-run; manual feedback + attribution counters compose.
- **Pin:** existing suite stays green (323 tests) — blend default 0 must be a no-op.

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Rich-get-richer feedback loop | Laplace prior (0.5 default), small `w`, new-record neutrality, retirement path prevents immortal records |
| Wrong attribution poisons counters | Provisional flags + per-event audit rows; manual feedback overrides; counters re-derivable from the event table |
| Hot-path latency (get-context) | Batch insert, event cap, `to_thread`, best-effort failure |
| Lessons-learned echo over-attributes | Similarity gate + shared-signal requirement + settle window; conservative by default |
| Job pile-up after downtime | `attributed_at` cursor + per-day claim = resume, not repeat |

## 10. Paper mapping

This plan *is* the mechanism contribution for "experiential learning without experience bloat":

- **Loop-open vs loop-closed ablation** = `knowledge_retrieval_quality_weight` 0 vs tuned, attribution on/off, on LongMemEval accuracy-vs-memory-footprint growth curves.
- **Forgetting half** = retirement candidates vs Memento's append-only bank and Hermes' char-cap.
- **No-judge attribution** = Memento's per-task LLM judge replaced by downstream-signal joins — a cost dimension worth reporting (tokens per attributed outcome ≈ 0).

## 11. Open questions

1. Should `get-context` capture when `context_knowledge_mode='index'` (lean index) identically to full records? (Assume yes — injection is injection.)
2. Positive-recurrence window (7d) — too generous? Review after phase-0 data.
3. Does the WhatsApp/n8n inbound path produce interaction_ids usable for attribution joins, or only ingest-API traffic? Verify during phase 0.
