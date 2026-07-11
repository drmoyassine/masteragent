# Nightly Learning Cadence + Telemetry Reflection

> **Created**: 2026-07-07. Two changes shipped together:
> 1. Intelligence & Knowledge now have the same **dual-valve** trigger model as Memory (schedule + threshold, whichever first), each on its own nightly time.
> 2. AI telemetry gets a **first-class, per-entity path to knowledge** via nightly reflection (skill / playbook / trade-knowledge / best-practice / lesson).
>
> **Updates since (2026-07-08):**
> - **Telemetry backfill** — `POST /trigger/backfill-telemetry?max_days=N` processes accumulated
>   historical telemetry (date-loop, idempotent+resumable); the **Drain Backlog** button
>   (`run-knowledge-check?drain=true`) now enqueues it alongside the intelligence→knowledge drain.
> - **Node-driven prompts** — telemetry reflection, playbook extraction, and skill decomposition
>   now read admin-editable node prompts (`telemetry_reflection` / `playbook_generation` /
>   `skill_generation`), seeded with the canonical defaults. The Knowledge-stage UI was refactored
>   from a misleading ordered "pipeline" into **pathway cards**.
> - For the current authoritative spec, see [generation-settings-reference.md](generation-settings-reference.md).
>
> Companion: [knowledge-to-context-retrieval-report.md](plans/archived/knowledge-to-context-retrieval-report.md), [knowledge-pipeline-map.md](knowledge-pipeline-map.md).

---

## Part 1 — The dual-valve cadence (what changed and why)

### Before

| Tier | Schedule valve | Threshold valve |
|---|---|---|
| Memory (0→1) | ✅ true nightly flush | ✅ intra-day |
| Intelligence (1→2) | ⚠️ ran nightly but **threshold-gated** — sub-threshold entities never reflected | ✅ intra-day |
| Knowledge (2→3) | ⚠️ ran nightly but **threshold-gated**; **no intra-day trigger at all** | ⚠️ nightly-check only |

The gap: intelligence/knowledge checks ran every night but only ever asked "is the pile ≥ threshold?" — an entity with 3 memories under a threshold of 10 **never** produced intelligence, even after a month. There was no "it's night, reflect on whatever accumulated" flush.

### After — every tier now has both valves

Each learning tier fires **once per day at its own configured time** (staggered so they cascade same-night) **and** retains an intra-day threshold trigger. Whichever fires first.

| Tier | Schedule (nightly sweep) | Threshold (intra-day) |
|---|---|---|
| Memory (0→1) | `memory_generation_time` (02:00) | `memory_threshold` |
| Intelligence (1→2) | `intelligence_generation_time` (02:30), floor `intelligence_schedule_floor` (2) | `intelligence_extraction_threshold` |
| Knowledge (2→3) | `knowledge_generation_time` (03:00), floor `knowledge_schedule_floor` (2) | `knowledge_threshold` — **now also fires intra-day** after each confirmed intelligence |
| Playbooks | `playbook_generation_time` (03:30) — **now nightly** (was weekly) | (n/a) |
| Telemetry reflection | `telemetry_reflection_time` (04:00) | (n/a) |
| Consolidation/dedup/decay | weekly `consolidation_run_interval_days` (7) — **stays maintenance, not learning** | (n/a) |

**Schedule floor** = the minimum accumulation for the *nightly sweep* to act, independent of the (usually higher) main threshold. Floor 2 = "reflect nightly on any entity with ≥2 accumulated, don't bother with singletons." Set floor=1 for a true every-scrap flush; disable the schedule for threshold-only; set threshold very high for schedule-only.

### Mechanics

- `memory_tasks._background_loop` wakes every 60s and fires each tier via `_time_reached(now, configured_time)` guarded by its own `memory_job_log` row (`intelligence_schedule`, `knowledge_schedule`, `playbook_extraction`, `telemetry_reflection`) → exactly once per day.
- Schedule sweeps pass a `min_count` override: `run_compaction_check(min_count=floor)` and `run_knowledge_check(min_count=floor)` temporarily lower the effective threshold to the floor.
- Intra-day knowledge trigger: `compact_entity` now calls `_check_knowledge_trigger(entity_type)` after auto-approved intelligence is created — enqueues a knowledge check the moment unused confirmed intelligence ≥ threshold (mirrors how memory generation triggers the intelligence check).

---

## Part 2 — Telemetry Reflection (AI telemetry → knowledge, option B)

### The problem it solves

Previously telemetry (`internal_ai_thought` / `internal_ai_tool_call`) had **no independent path to knowledge**. It was excluded from memory generation (correctly), invisible to intelligence, and only entered at *playbook enrichment* — where it (a) couldn't initiate anything, (b) required a 3-distinct-entity intelligence cluster it had no influence over, and (c) was joined via a fragile ±1h window comparing compaction-time to conversation-time. A brilliant single-session tool sequence was simply lost.

### The new pathway

A nightly job (`memory_telemetry.run_telemetry_reflection`) reflects on **each entity's telemetry for one day, plus that day's conversation** (for outcome context), and asks one question: *did the agent DO or DISCOVER anything reusable?*

- **Reflection before codification**: one LLM reflection per entity-day condenses raw telemetry into 0–k **typed candidates** — never dumps raw telemetry into knowledge.
- **Typed output**: each candidate targets `skill | playbook | best_practices | lessons_learned | trade_knowledge`. This is the key: a tool call that returned "University X waives IELTS with a medium-of-instruction cert" becomes **trade_knowledge discovered by doing** — previously lost entirely.
- **Recurrence builds conviction**: candidates enter as **drafts** with `evidence_breadth=1`, `source_pathway='telemetry_reflected'`. The existing dedup + refine-on-merge machinery promotes and strengthens them as the same pattern recurs across days/entities (merge_count → quality). A one-off stays a weak draft; a real pattern compounds.
- **Single-entity capable**: unlike playbooks, one entity's telemetry can produce a learning. No cluster gate.
- **Idempotent**: `telemetry_reflection_log (entity_type, entity_id, reflection_date)` PK guards against re-processing.
- **Governed & safe**: goes through `insert_knowledge` → SKILL.md rendering (skill/playbook) + facet extraction + governance are all inherited. Confidence-gated (`telemetry_reflection_confidence_min`, default 0.6).

### Flow

```
nightly 04:00 → run_telemetry_reflection(yesterday)
  → for each entity with unreflected telemetry that day:
      fetch day's telemetry + conversation
      → 1 LLM reflection → typed candidates [{target, name, summary, content, confidence, ...}]
      → per candidate ≥ confidence_min:
          embed → dedup(category)
            → match?  refine-on-merge (strengthen existing)
            → new?    insert_knowledge(draft, evidence_breadth=1, source_pathway='telemetry_reflected')
      → mark (entity, day) reflected  [idempotency]
      → log_pipeline_run('telemetry_reflection', ...)
```

### Relationship to the existing playbook pathway

Both now run nightly and are complementary, not redundant:
- **Playbook extraction** = *cross-entity* pattern mining (same signal across ≥3 entities → generalized procedure). Breadth-first.
- **Telemetry reflection** = *per-entity* learning-by-doing (this agent did/found something reusable, even once). Depth-first, single-entity.
A learning surfaced by reflection that later recurs across entities can also get picked up and generalized by playbook extraction — the dedup layer keeps them from duplicating.

---

## Part 3 — Settings reference (all new, all in Knowledge/Intelligence tabs)

| Setting | Default | Meaning |
|---|---|---|
| `intelligence_schedule_enabled` | true | nightly intelligence sweep on/off |
| `intelligence_generation_time` | 02:30 | UTC time for the sweep |
| `intelligence_schedule_floor` | 2 | min uncompacted memories for nightly synthesis |
| `knowledge_schedule_enabled` | true | nightly knowledge sweep on/off |
| `knowledge_generation_time` | 03:00 | UTC time |
| `knowledge_schedule_floor` | 2 | min unused confirmed intelligence for nightly synthesis |
| `playbook_schedule_enabled` | true | nightly playbook extraction on/off |
| `playbook_generation_time` | 03:30 | UTC time |
| `telemetry_reflection_enabled` | true | nightly telemetry reflection on/off |
| `telemetry_reflection_time` | 04:00 | UTC time |
| `telemetry_reflection_confidence_min` | 0.6 | drop candidates below this |
| `telemetry_reflection_max_tokens` | 1200 | reflection LLM output cap |

Manual triggers (admin): `POST /trigger/reflect-telemetry?reflection_date=YYYY-MM-DD` (UI: **Reflect Telemetry** button). Existing `run-intelligence-check`, `run-knowledge-check` still work for on-demand full-threshold checks.

Backwards compatibility: every default preserves prior behavior *except* the intended fixes — sub-threshold nightly sweeps and nightly (vs weekly) playbooks now fire. The old `playbook_extraction_interval_days` / `_evidence_threshold` settings are superseded by the nightly schedule but left in place.

---

## Part 4 — Files

**New**: `backend/memory_telemetry.py` (reflection pathway).
**Backend edits**: `memory_tasks.py` (per-tier scheduler loop), `memory_compaction.py` (`min_count` sweep + intra-day knowledge trigger), `memory_knowledge.py` (`min_count`), `memory_db.py` (12 settings + `telemetry_reflection_log` table), `memory_models.py` (settings fields), `memory/queue.py` (`run_intelligence_sweep`, `reflect_telemetry` jobs), `memory/admin.py` (`/trigger/reflect-telemetry`).
**Frontend**: `lib/api.js` (`triggerReflectTelemetry`), `settings/MemorySettings.jsx` (Schedule blocks on Intelligence & Knowledge tabs, Telemetry Reflection card, Reflect Telemetry button).
