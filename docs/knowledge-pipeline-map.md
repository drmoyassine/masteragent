# Knowledge Pipeline — End-to-End Map

> **Created**: 2026-07-05, day the first production knowledge record shipped.
> Companion to [knowledge-tier-productionization.md](knowledge-tier-productionization.md). Covers: every path knowledge is **created**, how it **lives**, every path it is **consumed**, the **telemetry→playbook** pipeline status, and the **retrieval design** for scaling injection without context bloat.

---

## 1. Creation Pathways (`source_pathway` column)

| # | Pathway | Trigger | Code | Status in prod |
|---|---|---|---|---|
| 1 | **Batch synthesis** (`experiential`) | Daily job or manual trigger; ≥ `knowledge_threshold` (5) unused **confirmed** intelligence per entity type | `memory_knowledge.run_knowledge_check` → `generate_knowledge_from_intelligence` | ✅ LIVE (first record 2026-07-05) |
| 2 | **Playbook extraction** (`experiential`, category=`playbook`) | Weekly (`playbook_extraction_interval_days`=7) or ≥20 unlinked intelligence; clusters similar intelligence across ≥3 distinct entities, enriched with AI telemetry | `memory_playbooks.run_playbook_check` | ❌ BROKEN (see §4) |
| 3 | **Skill decomposition** (`decomposed`, category=`skill`) | Automatic after each playbook creation; 1–3 reusable capabilities per playbook | `memory_playbooks._generate_skills_from_playbook` | ❌ blocked by #2 |
| 4 | **Hermes admin instruction** (`admin_instructed`) | Admin posts natural language to `POST /api/memory/instruct`; LLM routes to category (incl. skill/playbook) | `memory_hermes.process_admin_instruction` | ⚠️ wired, untested in prod; needs `admin_instruct` LLM config row |
| 5 | **Manual promotion** | Admin promotes a single intelligence | `POST /trigger/...` → `memory_knowledge.promote_to_knowledge` | ⚠️ wired, untested |
| 6 | **Manual creation** | Admin UI "New Knowledge" button | `POST /api/memory/knowledge` (admin) | ✅ |

All pathways write to the **unified `knowledge` table** (categories: `best_practices`, `lessons_learned`, `trade_knowledge`, `playbook`, `skill`).

## 2. Lifecycle

```
draft ──(admin activate / auto_activate+score gate)──► active ──► retired
                                                        │  ▲
                              consolidation (weekly): merge duplicates (retire loser,
                              merge_count++ on winner), decay stale playbooks/skills,
                              recompute quality_score
```

- **Quality score** (`memory_dedup.compute_quality_score`): evidence breadth 25% + outcome signal 30% + LLM confidence 15% + merge recurrence 20% + recency 10%. Batch-synthesis records insert with `quality_score = NULL` — backfilled by weekly consolidation.
- **Outcome signal** feeds from feedback (`success_count`/`failure_count` via the feedback endpoint) — currently admin-only, thumbs up/down in Knowledge tab.
- **Dedup at creation**: new knowledge is checked against existing via cosine similarity (`dedup_similarity_threshold` 0.85); matches merge instead of duplicating (playbook/skill/Hermes paths) or are avoided via prior-knowledge prompt injection (batch path).

## 3. Consumption Pathways (how agents get knowledge)

| Channel | Auth | Selection logic today | Gap |
|---|---|---|---|
| `GET /get-context` | agent key | **Global top-30** `active`+`shared` by `quality_score DESC NULLS LAST` — full content, no relevance matching | Bloat + irrelevance as corpus grows (§5) |
| `POST /search/semantic` `layers:["knowledge"]` | agent key | pgvector cosine + time decay, `visibility='shared'` | **No `status` filter** — retired/draft records surface; no category/signals params exposed |
| `POST /search/fulltext` `layers:["knowledge"]` | agent key | websearch tsquery | same gaps |
| `GET /knowledge` (list) / CRUD | agent key | filterable list | fine |
| Outbound webhook payload | HMAC | mirrors get-context | inherits top-30 problem |

**Not implemented**: proactive playbook matching (PRD §6.1 — match entity's fresh intelligence against playbook `trigger_conditions`/embeddings in `has-context`); playbook/skill-specific detail+feedback endpoints for agents (feedback is admin-only).

## 4. Telemetry → Playbook/Skill Pipeline (PRD: `backend/memory/PLAYBOOKS_PRD.md`)

**Design intent**: declarative knowledge answers "what do we know"; playbooks answer "what should we do". Telemetry interactions (`internal_ai_thought`, `internal_ai_tool_call`) capture *how the agent actually acted*; clustering intelligence across entities finds *recurring situations*; the LLM fuses both into ordered, trigger-conditioned procedures, then decomposes them into reusable skills.

**Implemented and wired**:
1. Telemetry ingestion: agents POST interactions with the two types; **excluded from memory generation** by default (`memory_generation_interaction_types` = exclude list — visible in Knowledge settings → Processing).
2. Weekly scheduler in `memory_tasks._background_loop` (interval or evidence-threshold override) → `extract_playbooks` job.
3. `run_playbook_check`: per entity type, pairwise cosine (≥0.85) on confirmed+embedded intelligence across **distinct** entities → union-find clustering → clusters spanning ≥ `extraction_min_entities` (3) qualify.
4. Cluster enrichment: telemetry interactions for the same entities within the cluster's time window ±1h, not previously processed (`playbook_processed_interactions` table).
5. LLM playbook (steps, trigger_conditions, confidence) → confidence gate (0.6) → centroid-embedding dedup → insert as `knowledge` category=`playbook` (draft, or active via `playbook_auto_activate` + `auto_activate_score_threshold`).
6. Skill decomposition → dedup → insert category=`skill`.
7. Weekly consolidation: merge, `_refine_playbook` on merge, decay, quality recompute.

**Broken / missing for production** (in order):
1. ❌ **Crash**: `datetime.fromisoformat(min_ts)` on `datetime` objects — every qualifying cluster dies before the LLM call (fix chip pending).
2. ❌ **`_refine_playbook` no-op**: `category` column missing from its SELECT (same chip).
3. ❌ **No LLM config rows** for `task_type='playbook_generation'` and `'skill_generation'` — these resolve by task type only (no pipeline-node path, and the Add Pipeline Step dialog doesn't offer them). Without rows: empty response → parse fail. Needs direct rows in `memory_llm_configs` (SQL or a UI extension).
4. ⚠️ **Telemetry volume unverified**: confirm the n8n counselor actually posts `internal_ai_thought`/`internal_ai_tool_call` interactions (`SELECT interaction_type, COUNT(*) FROM interactions WHERE interaction_type LIKE 'internal_ai%' GROUP BY 1`). Extraction works without telemetry but produces shallower playbooks.
5. ⚠️ **Decay mismatch** (deferred list): `_apply_decay` filters `metadata->>'entity_type'`, but skills store `entity_types` (array) → skills never decay.
6. ⚠️ **No proactive retrieval**: playbooks reach agents only via the generic knowledge top-30 and search; `trigger_conditions` are stored but never evaluated.

## 5. Retrieval Design — injecting knowledge without context bloat

**Principle**: entity tiers (interactions/memories/intelligence) are *naturally bounded* per entity; knowledge is *unbounded* and org-global — so knowledge injection must be **selected, not enumerated**. Three layers, cheapest first:

### Layer 1 — Relevance-ranked pre-injection (replace global top-30)
Pure pgvector, no LLM, no latency worth noticing:
1. Build a **query vector for the conversation**: mean of embeddings of the entity's pending interactions (already embedded at ingest) — fall back to latest memory/intelligence embeddings.
2. `knowledge WHERE status='active' AND visibility='shared'` ranked by `cosine × quality_weight`, with a **similarity floor** (e.g. 0.30) so irrelevant records drop out entirely.
3. **Signals overlap boost**: entity's recent intelligence `signals` ∩ knowledge `signals`.
4. Cap at K (settings: `context_knowledge_count`, default ~5) + always include top-N (~2) "core rules" by quality regardless of similarity (org-wide invariants).
5. **Inject compact form**: `name + summary + signals` (not full `content`) — agent pulls full content via `GET /knowledge/{id}` when it decides it needs it.

### Layer 2 — On-demand pull (make the interacting agent the retriever)
Already 80% built: `search/semantic` + `search/fulltext` with `layers:["knowledge"]` behind agent-key auth and MCP. **Recommendation: no separate librarian sub-agent for now.** Instead, expose retrieval as a *tool of the counselor agent* (n8n MCP client already auto-discovers these endpoints): "search organizational knowledge / playbooks" becomes a tool call the agent makes when the pre-injected summaries look relevant. A sub-agent adds an LLM hop + latency to every message for selection quality that embedding search already provides at current corpus size (1–100s of records). Revisit a librarian sub-agent when: corpus > several hundred records, multi-playbook arbitration is needed, or retrieval requires multi-hop reasoning.
Required endpoint fixes: add `status='active'` filter to knowledge search; expose `category` + `signals` filters in `SearchRequest` (so agents can ask for playbooks vs facts).

### Layer 3 — Proactive playbook push (the PRD's original design, later)
At get-context time, match the conversation vector against **playbook embeddings + trigger_conditions**; if similarity crosses a higher bar (e.g. 0.45), inject that playbook's *full steps* — this is the "system pushes procedure at the right moment" behavior. Ship after Layers 1–2 prove out and playbook extraction actually produces records.

## 6. Observability — `memory_pipeline_runs` (plan Step 7, not yet built)

**Why**: every pipeline failure so far (empty pipeline node, disabled toggle, missing LLM config, parse errors) was invisible until someone tailed docker logs. One table turns "why is there no knowledge?" into a dashboard glance.

**What**: every check/generation run writes one row:
`id, job (knowledge_check|intelligence_extraction|playbook_extraction|consolidation|memory_generation), started_at, finished_at, outcome (created|skipped|failed), reason_code (below_threshold|no_confirmed_intelligence|llm_config_missing|parse_error|lock_held|...), detail JSONB, records_created INT`

**Where**: write helper in `memory_db_writes`, called from the 4–5 pipeline entry points; `GET /api/memory/admin/pipeline-runs` (filter by job/outcome, last N); System Monitor page table with reason-code badges.

## 7. Sprint Plan & Fix List

**Sprint 1** ✅ (shipped 2026-07-05): items 2, 3, 4 + manual triggers/backfill
**Sprint 2** ✅ (shipped 2026-07-05): items 5, 5b, 5c, 6, 7 · **Sprint 3**: items 8, 9, 10

**Zero-regression guarantee (Sprint 2)**: no DB-backed generation prompt (memory/intelligence/knowledge `inline_system_prompt`) was changed — those are admin-owned and good. Item 5d (prompt "borrows") was deliberately NOT hardcoded; it remains an optional admin-side enhancement documented below. Every new LLM path (refine-on-merge) and retrieval change (relevance ranking) falls back to prior behavior on any failure.

| # | Item | Size | Status |
|---|---|---|---|
| 1 | Feedback + knowledge admin API URL bugs | XS | ✅ done |
| 2 | Provider-aware `scrub_pii`. **Prod action pending**: reassign PII node to a real LLM provider or toggle it off | S | ✅ done (code) |
| 3 | Playbook `fromisoformat` crash + `_refine_playbook` no-op | S | ✅ done |
| 4 | `playbook_generation` + `skill_generation` config rows seeded | XS | ✅ done |
| 4b | Manual triggers + backfill drain | S | ✅ done |
| 4c | Latent ImportError in `/trigger/backfill-profiles` | XS | ✅ done |
| 5 | Knowledge search `status='active'` filter + `knowledge_category`/`knowledge_signal` params on SearchRequest; applied to both semantic + fulltext knowledge search | S | ✅ done |
| 5b | **Refine-on-merge** (`memory_dedup.refine_or_increment_merge`): on dedup match, conservative preservation-first LLM merge into the existing record (`content`/`summary` update + `version++`), re-rendered to SKILL.md for skill/playbook, re-embedded. Wired into skill decomposition, Hermes, and marketplace import. Gated by `knowledge_refine_on_merge` setting; **falls back to `increment_merge` on any failure** (zero regression). Playbook centroid pre-gen dedup stays as increment (consolidation refines it) | M | ✅ done |
| 5c | Universal export: `render_knowledge_md` for declarative categories (render-on-export, memory-file style); `GET /knowledge/{id}/skill.md` generalized to all categories; **`GET /knowledge-pack`** zip bundle (`INDEX.md` + one file per record, category subfolders). UI Export Pack button | M | ✅ done |
| 6 | Relevance-ranked get-context injection: CTE with pgvector `AVG(vector)` over the entity's recent interaction embeddings, blended 0.7 relevance / 0.3 quality; `context_knowledge_count` cap (default 30 = prior) + `context_knowledge_min_similarity` floor (default 0 = reorder-only, drop-nothing); **falls back to prior quality-ordered query on any error**. Settings inputs added | M | ✅ done |
| 7 | `memory_pipeline_runs` table + `log_pipeline_run` best-effort helper + `GET /pipeline-runs` admin endpoint; knowledge_check instrumented (created/skipped + reason_code). System Monitor UI panel = follow-up | M | ✅ done (UI panel deferred) |
| 5d | Prompt borrows (Why/How-to-apply, description discipline, absolute dates) — **NOT hardcoded** (zero-regression). Optional: admin may add to node prompts in the UI | — | optional / documented |
| 8 | n8n last mile: verify counselor renders `knowledge` array; add knowledge-search as agent tool | S | Sprint 3 |
| 9 | Orphan sweeper idempotency (duplicate-webhook root cause) | S | Sprint 3 (chip pending) |
| 10 | Layer-3 proactive playbook push | M | Sprint 3 |

### Sprint 2.5 — Knowledge pre-context retrieval ✅ shipped (PR #31, 2026-07-06)
Spec: **[knowledge-precontext-retrieval-plan.md](knowledge-precontext-retrieval-plan.md)**. Delivery report: **[sprint2.5-delivery-report.md](sprint2.5-delivery-report.md)**. Turns get-context knowledge injection into a lean, governed, filterable index: WS-1 `context_knowledge_mode` (full|index), WS-2 `GET /knowledge/{id}` + `GET /knowledge/facets` + fixed `list_knowledge`, WS-3 always-on UI-editable Knowledge Management skill (epistemic contract + broaden→tools→delegate ladder), WS-4 governed `metadata.facets` via a separate extraction step (generation prompts untouched) + backfill, WS-5 hard facet filter on all categories (pinned skill exempt) with semantic broaden. Governed filtering = `metadata.facets` only; `tags` off the agent surface. Zero-regression: `profile_facet_map` defaults NULL (opt-in), `full` mode byte-identical to Sprint 2, extraction degrades to `{}`.

### Sprint 2 follow-ups (small, deferred)
- System Monitor UI panel for `/pipeline-runs` (endpoint + data exist; render a table with reason-code badges).
- Skill/playbook import dialog + per-record export button in the Knowledge tab (endpoints exist; `importSkillMd`/`exportKnowledgeMarkdown` API clients wired).
- Optional 5d prompt enhancements (admin-applied).

### Optional 5d prompt enhancements (apply in UI, not hardcoded)
For admins who want the memory-file disciplines, these can be pasted into the respective pipeline node prompts without code changes:
- **Intelligence/Knowledge**: end the body with a `**Why:**` and `**How to apply:**` line.
- **Summary/description**: "state what this is AND when it applies, self-contained, ≤1024 chars."
- **Memory generation**: "convert relative dates (today, last week) to absolute dates."

## 8. Agent-Skills Standard (SKILL.md) — adopted 2026-07-05

Skills and playbooks follow the **Anthropic agent-skills standard**. No new column: for `category IN ('skill','playbook')` the **`content` column stores the full SKILL.md document** (YAML frontmatter: `name` lowercase-hyphen slug ≤64 chars, `description` ≤1024 chars stating what + when, `metadata:` with source/category/version/signals/tags; markdown body with When-to-use / Procedure or Trigger-conditions / Steps). `summary` keeps the description for compact Layer-1 injection; `metadata` JSONB keeps structured steps/trigger_conditions for programmatic access. Playbooks render in the same SKILL.md format — the standard has no separate playbook type; a playbook is a procedural skill.

- **Rendering** ([backend/memory_skill_md.py](../backend/memory_skill_md.py)): auto-rendered in `insert_knowledge` for every creation path (extraction, decomposition, Hermes, admin manual create); re-rendered with `version++` on playbook refinement.
- **Export / publish**: `GET /api/memory/knowledge/{id}/skill.md` (admin JWT or agent key) → downloadable spec-compliant document; legacy records rendered on the fly.
- **Import / install**: `POST /api/memory/skills/import` `{skill_md, category, status, signals?, tags?}` — validates frontmatter, stores the document verbatim, dedups against existing records (merge instead of duplicate), `source_pathway='imported'`.
- **Why**: marketplace interop — install publicly available skills into agent context, and publish hard-earned experiential ones.
- Remaining (Sprint 2): UI export/download button + import dialog in the Knowledge tab; bundle export (zip with directory layout) when skills grow supporting files.

## 8b. Declarative knowledge + memory-file standards (reflection, 2026-07-05)

**Knowledge ("KNOWLEDGE.md")**: no marketplace standard exists for declarative knowledge; the skills standard's transferable core is frontmatter discovery header + on-demand body + progressive disclosure. Decision: apply the **same renderer/format to all knowledge categories** but **render-on-export only** (unlike skills/playbooks, declarative content has no import round-trip requirement, and its `content` feeds LLM prompts where frontmatter is token noise; all fields are relational so export rendering is lossless).

**Memory (MEMORY.md pattern — Claude Code auto-memory et al.)**: index line → frontmattered fact-file, typed memories, Why/How-to-apply bodies, update-in-place discipline, curated smallness. Comparison verdict: MEMORY.md-style systems are **serving formats without a factory**; MasterAgent is a **factory without a standard serving format** — complementary. MasterAgent is ahead on generation, consolidation/decay automation, and semantic search; behind on two-level disclosure (→ Sprint 2 item 6) and update-in-place (→ Sprint 2 item 5b), both now validated by a proven reference model.

Sprint 2 additions from this reflection:
- **5c — Universal export**: extend per-record SKILL.md-style rendering to all categories + **knowledge-pack bundle** endpoint (`INDEX.md` one-line-per-record + one frontmattered markdown file each) — drops directly into Claude Code memory dirs / AGENTS.md-style docs folders / git repos.
- **5d — Prompt borrows** (config-only, pipeline untouched): Why/How-to-apply body structure in intelligence/knowledge prompts; summary/description discipline (what + when it matters, self-contained, ≤1024 chars); absolute-dates rule in memory generation prompt.
