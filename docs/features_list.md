# Features List — Knowledge Retrieval and Playbook Activation

**Status:** Next roadmap initiative — ready after Knowledge Hygiene QA
**Date:** 2026-07-11
**Supersedes remaining roadmap work in:** `plans/archived/knowledge-to-context-retrieval-report.md` Part 2.2–2.5 and `knowledge-pipeline-map.md` Sprint 3 items 8 and 10.
**Does not reimplement:** the shipped Sprint 2.5 pre-context retrieval work.

## 0. Documentation and roadmap index

This is the authoritative feature list for the next retrieval/activation initiative, not a replacement for unrelated active plans.

| Document | Classification | Action |
|---|---|---|
| `features_list.md` | Next feature roadmap | Implement after Knowledge Hygiene QA |
| `pairwise-to-clustering-knowledge-hygiene-plan.md` | Active implementation | Keep until delivery and QA complete |
| `mastermemory-npm-migration.md` | Future product roadmap | Keep; begins after Python contracts are production-proven |
| `knowledge-tier-productionization.md` | Production-state plan requiring VPS confirmation | Keep until its remaining production gates are explicitly closed |
| `knowledge-pipeline-map.md` | Current architecture/reference map | Keep and update as behavior changes |
| `generation-settings-reference.md` | Current operator reference | Keep |
| `nightly-learning-and-telemetry-reflection.md` | Current behavior reference | Keep |
| `plans/archived/*` | Implemented or superseded plans/reports | Historical reference only; do not implement |

Completed production-hardening, Variables, and Sprint 2.5 plans are archived. Prompt files remain under `docs/prompts` because they are runtime/reference assets, not roadmap documents.

## 1. Outcome

Create one explainable retrieval policy that determines which active canonical knowledge, skills, and playbooks an agent receives. Administrators can configure and preview the policy. Applicable playbooks and skills can be proactively injected with explicit activation reasons, while agents retain on-demand semantic/full-text retrieval.

```text
Conversation + entity context
  -> shared RetrievalService
  -> candidate knowledge
  -> facets, signals, category, status and capability checks
  -> explainable ranking + diversity + token budget
  -> lean knowledge index
  -> applicable full playbooks/skills
  -> agent context and on-demand retrieval tools
```

This initiative completes the consumption side of the learning loop. It does not change knowledge generation or consolidation semantics.

## 2. Code-verified baseline

### 2.1 Already implemented — preserve and reuse

| Capability | Current location | Status |
|---|---|---|
| Full versus lean-index injection | `memory/agent.py`, `context_knowledge_mode` | Shipped |
| Total injected-knowledge cap | `context_knowledge_count` | Shipped |
| Semantic similarity floor | `context_knowledge_min_similarity` | Shipped |
| Conversation vector from recent interaction embeddings | `memory/agent.py` | Shipped; window hardcoded to 10 |
| Relevance/quality ranking | `memory/agent.py` | Shipped; weights hardcoded 0.7/0.3 |
| Active-only agent retrieval | `memory/agent.py`, `services/search.py`, `memory_prior_context.py` | Shipped |
| Governed facet extraction and schema | `memory_facets.py` | Shipped |
| Profile-to-facet mapping | `profile_facet_map` | Shipped, opt-in |
| Hard facet filtering in get-context | `memory/agent.py` | Shipped |
| Strict/broaden behavior in search | `services/search.py` | Shipped |
| Pinned always-on knowledge | `metadata.always_inject` | Shipped |
| Knowledge Management skill | `memory_facets.py` | Shipped |
| Category and signal filters | `SearchRequest`, semantic/full-text endpoints | Shipped |
| Full record pull by ID | agent `GET /knowledge/{id}` | Shipped |
| Knowledge table category/status/filter UI | `components/memory/KnowledgeTab.jsx` | Shipped |
| Skill/playbook SKILL.md rendering and operational metadata | `memory_skill_md.py` | Shipped |

Do not create replacements for these features. Move their logic behind the shared service while preserving default behavior and response compatibility.

### 2.2 Remaining gaps — actual scope

1. Retrieval SQL and projection logic remain concentrated inside `memory/agent.py` rather than a reusable service.
2. Ranking weights and conversation-vector window are hardcoded.
3. There are no per-category caps, recency term, signal-overlap boost, or diversity control.
4. Get-context facets are hard filtering only; administrators cannot choose boost or off.
5. There is no token-budget enforcement across injected knowledge.
6. There is no live preview or per-result scoring explanation.
7. Playbook `trigger_conditions` are stored but not evaluated during retrieval.
8. Skill prerequisites, tools, permissions, environments, and agent applicability are not used during selection.
9. No retrieval event records which knowledge/playbook influenced a context response.
10. Repository endpoints exist for agent search, but external n8n/tool configuration cannot be verified from this repository.

## 3. Locked product decisions

1. `RetrievalService` is the single selection implementation for get-context, preview, and proactive activation.
2. Existing semantic/full-text search continues to use the shared active/visibility/facet primitives but remains query-oriented; it does not apply context caps.
3. Defaults reproduce current output ordering as closely as possible: relevance 0.7, quality 0.3, recency 0, window 10, strict facets, no signal boost, no category caps.
4. Pinned records bypass relevance floors and category caps but never bypass `status='active'`, shared visibility, or agent capability/safety checks.
5. Retired, draft, and merged source records never appear in agent context, semantic search, full-text search, prior context, or direct agent retrieval.
6. Retrieval ranks and gates; it does not rewrite knowledge.
7. Proactive playbook activation requires both semantic relevance and trigger evidence. Similarity alone is insufficient.
8. Skills are injected only when applicable to the current agent/environment and required by an activated playbook or independently above the skill threshold.
9. All score components and exclusion reasons are explainable in preview and optional telemetry.
10. No LLM call is added to the normal get-context hot path.

## 4. Shared retrieval architecture

Create:

- `backend/memory_retrieval.py` — orchestration, settings normalization, ranking, category caps, diversity, token budget, projections.
- `backend/memory_retrieval_repository.py` — candidate and context SQL only.
- `backend/memory_activation.py` — playbook/skill applicability and activation reasons.
- `backend/memory_retrieval_models.py` — typed request, recipe, score, explanation, activation, and preview models.

Conceptual interface:

```python
result = await retrieval_service.retrieve(
    query_context=RetrievalQueryContext(...),
    recipe=RetrievalRecipe.from_settings(settings),
    include_explanations=False,
)

preview = await retrieval_service.retrieve(
    query_context=admin_preview_context,
    recipe=unsaved_recipe,
    include_explanations=True,
)
```

`memory/agent.py` builds the query context, calls the service, and preserves the current get-context response structure. It must no longer contain ranking SQL constants or category-cap logic.

## 5. Retrieval Recipe

### 5.1 Settings and defaults

Add idempotent `memory_settings` columns and matching request/response model fields:

| Setting | Type | Default |
|---|---|---|
| `context_rank_weights` | JSONB | `{"relevance":0.7,"quality":0.3,"recency":0.0}` |
| `context_conversation_window` | INT 1..100 | `10` |
| `context_per_category_caps` | JSONB | `{}` |
| `context_facet_mode` | TEXT enum | `strict` |
| `context_signal_boost` | FLOAT 0..1 | `0.0` |
| `context_facet_boost` | FLOAT 0..1 | `0.10` |
| `context_recency_half_life_days` | INT 1..3650 | `180` |
| `context_token_budget` | INT 256..32768 | `6000` |
| `context_diversity_enabled` | BOOLEAN | `true` |
| `context_max_similar_results` | INT 1..20 | `3` |
| `playbook_activation_enabled` | BOOLEAN | `false` |
| `playbook_activation_similarity` | FLOAT 0..1 | `0.55` |
| `skill_activation_similarity` | FLOAT 0..1 | `0.60` |
| `retrieval_telemetry_enabled` | BOOLEAN | `true` |
| `retrieval_telemetry_sample_rate` | FLOAT 0..1 | `0.10` |

Validate and normalize the three base weights to sum to 1. If their sum is zero, reject the settings update. Signal and facet boosts are additive after the normalized base score and the final score is clamped to 0..1.

### 5.2 Score definition

For every eligible non-pinned record:

```text
base = relevance*w_relevance + quality*w_quality + recency*w_recency
score = clamp(base + signal_overlap*signal_boost + facet_match*facet_boost, 0, 1)
```

- `relevance`: cosine similarity clamped to 0..1; zero when no query vector exists.
- `quality`: `quality_score` clamped to 0..1; zero when absent.
- `recency`: `2 ** (-age_days / half_life_days)`.
- `signal_overlap`: Jaccard similarity between recent intelligence signals and record signals.
- `facet_match`: matching requested/profile facets divided by requested facets; zero when none exist.

Apply the configured similarity floor to semantic relevance before boosts. Pinned records receive `selection_reason='pinned'` and are projected first.

### 5.3 Facet modes

- `strict`: current get-context behavior; incompatible/missing governed facets are excluded when a facet value is available.
- `boost`: never exclude on facets; matching records receive `facet_boost`.
- `off`: do not filter or score facets.

Explicit request facets override profile-derived facets. Canonicalize values through existing `memory_facets` helpers.

### 5.4 Caps, diversity, and token budget

Apply controls in this order:

1. Active/shared/protected eligibility.
2. Facet policy and similarity floor.
3. Score and deterministic tie-break by quality, updated timestamp, then ID.
4. Diversity suppression: after selecting a record, no more than `context_max_similar_results` records with cosine >=0.90 to it may be selected. Record suppression reason.
5. Per-category caps using database names `best_practices`, `lessons_learned`, `trade_knowledge`, `skill`, `playbook`; missing keys mean unlimited within total cap.
6. Total record cap.
7. Token budget using the repository's token estimation helper if available, otherwise deterministic `ceil(characters/4)`. Pinned records consume budget first. If pinned content alone exceeds the budget, project pinned records to index form except the Knowledge Management skill and add a truncation warning.

## 6. Proactive playbook and skill activation

### 6.1 Playbook eligibility

A playbook is eligible only when:

- active/shared and not retired/merged;
- category is `playbook`;
- semantic relevance meets `playbook_activation_similarity`;
- at least one trigger evidence source exists: normalized phrase match in conversation text, overlap with recent intelligence signals, or compatible governed facets;
- required agent/environment metadata does not conflict with the current caller.

Return activation evidence, not just a score:

```json
{
  "knowledge_id": "...",
  "activation_score": 0.78,
  "reasons": ["semantic_similarity", "trigger_phrase:visa refusal", "signal:objection"],
  "warnings": [],
  "full_content_injected": true
}
```

Inject full playbook content after the lean index and before ordinary full declarative records. Respect the token budget. If an eligible playbook cannot fit, inject its index entry with `activation_deferred=true` so the agent can pull it by ID.

### 6.2 Skill eligibility

Parse current SKILL.md plus metadata. Recognize these fields when present: `inputs`, `outputs`, `tools`, `prerequisites`, `permissions`, `side_effects`, `failure_conditions`, `safety_requirements`, `environments`, `agent_ids`, and `agent_types`.

A skill may activate when linked by an activated playbook's `skill_ids`, or independently when semantic relevance meets `skill_activation_similarity`. Exclude it when explicit tools, permissions, environment, or agent applicability conflict. Missing metadata means unknown, not incompatible; include with a warning in preview and require on-demand pull unless linked by a playbook.

Never claim that an external tool or permission is available merely because a skill names it.

## 7. Live preview and explanations

Add authenticated admin endpoint:

```text
POST /api/memory/admin/context-preview
```

Request accepts entity type/ID or sample text, optional explicit facets/signals, and an unsaved recipe. It has no side effects and returns:

- resolved query context and vector source;
- selected pinned, ranked, playbook, and skill records;
- each score component and final score;
- cap, diversity, facet, threshold, capability, and token-budget decisions;
- projected payload exactly as get-context would return;
- token estimate and warnings.

Add a **Retrieval Recipe** card to the existing Knowledge settings tab with:

- injection mode and total/token caps;
- per-category caps;
- auto-normalized relevance/quality/recency controls with live formula;
- conversation window and recency half-life;
- facet mode and boost;
- signal boost;
- diversity controls;
- playbook/skill activation toggles and thresholds;
- entity/sample-text preview panel.

Saving settings and previewing unsaved settings are separate actions.

## 8. Retrieval telemetry and attribution

Add `memory_retrieval_events`:

- ID, timestamp, agent ID, entity type/ID;
- recipe/settings snapshot;
- query-vector source;
- candidate/selected/excluded counts;
- selected knowledge IDs and score breakdowns;
- activated playbook/skill IDs and reasons;
- token estimate and warnings;
- optional later outcome reference.

Write events best-effort only when telemetry is enabled and the deterministic sample check passes. Telemetry failure must never fail get-context. Do not store raw conversation text; store IDs, hashes, metrics, and reasons.

Add a small System Monitor panel showing retrieval count, average selected records/tokens, top activated playbooks, zero-result rate, and exclusion reasons.

## 9. Agent and n8n contract

Keep existing endpoints and MCP discovery compatible. Document the required agent behavior:

1. Read injected lean index.
2. Use full-record `GET /knowledge/{id}` before relying on a skill/playbook not injected in full.
3. Use semantic search for conceptual retrieval and full-text search for exact terms.
4. Honor activation warnings and verify tools/permissions before execution.
5. Never request retired records; a retired ID returns not found to agents.

Repository work includes API/MCP schemas, examples, and tests. Actual n8n workflow installation is an operational task because workflows are not stored in this repository; the delivery report must state whether it was verified externally.

## 10. Implementation sequence

### Work package 1 — Extract shared service

- Move current candidate SQL, pinned selection, ranking, projection, facets, and fallback behavior behind `RetrievalService`.
- Preserve current defaults and get-context response tests byte-for-byte where timestamps are excluded.
- Make semantic/full-text search reuse shared eligibility/facet helpers.

### Work package 2 — Recipe and scoring

- Add settings/models/UI validation.
- Implement configurable scoring, facet modes, signal boost, recency, caps, diversity, and token budget.
- Add unit fixtures for no-vector and missing-quality cases.

### Work package 3 — Preview and UI

- Implement preview endpoint and explanations.
- Build the Retrieval Recipe card and live preview.
- Ensure unsaved preview never mutates settings.

### Work package 4 — Playbook and skill activation

- Implement trigger evidence and capability checks.
- Inject applicable full procedures within budget.
- Add category-specific fixtures and explainability.

### Work package 5 — Telemetry and last-mile contract

- Add sampled retrieval events and monitor panel.
- Update API/MCP documentation and provide n8n configuration example.
- Verify active-only behavior across every external path.

## 11. Acceptance criteria

1. Current production defaults preserve existing retrieval ordering/projection within deterministic tie behavior.
2. Retired/draft/merged sources are absent from every agent-facing path.
3. Pinned records remain included but obey active status and token safety.
4. Weight changes visibly and predictably change preview rankings.
5. Strict, boost, and off facets produce tested distinct behavior.
6. Per-category caps prevent one category from crowding out others.
7. Diversity suppresses redundant results with an explanation.
8. Token budget is never exceeded except the explicitly reported Knowledge Management skill safeguard.
9. Playbooks require semantic plus trigger evidence.
10. Skills with explicit incompatible permissions/tools/environment are not injected.
11. Preview output explains every inclusion and exclusion and causes no writes except optional audit access logging.
12. Get-context adds no LLM call and remains within the agreed latency regression budget (p95 no more than 20% slower on the production-sized fixture).
13. Search and direct retrieval remain backward-compatible.
14. Telemetry failure cannot fail retrieval and stores no raw conversation text.

## 12. Tests and delivery gate

Add pure tests for scoring, normalization, recency, Jaccard signals, facet modes, caps, diversity, token budgeting, trigger matching, capability checks, deterministic ordering, and projections. Add integration tests for get-context parity, preview, settings validation, search compatibility, active-only enforcement, and telemetry failure. Add frontend tests for recipe validation, normalized weights, preview rendering, and activation explanations.

Run the repository's backend suite, frontend tests/build, Compose validation, and diff checks. The delivery report must separate repository-complete functionality from external n8n verification.

## 13. Explicitly out of scope

- Knowledge generation and consolidation changes.
- LLM reranking on the get-context hot path.
- Cross-category knowledge rewriting.
- Autonomous tool execution.
- HNSW/index-dimension migration; handle this as the later performance refactor.
- MasterMemory npm port; freeze these retrieval contracts after production validation, then port them.
