# Knowledge Settings UI Refactor — Decision Log

## Decision protocol

Only decisions explicitly confirmed by the product owner are marked **Locked**. Code findings and recommendations remain **Pending** until confirmed.

## Locked decisions

### KD-001 — One generation token budget

Use one global maximum-output-token budget for every knowledge-producing pathway. Pathways inherit it by default and may define an explicit override inside their own accordion. Do not expose disconnected telemetry, intelligence-to-knowledge, skill, or playbook token controls outside the inheritance/override model.

Implementation direction:

- introduce one canonical generation token setting;
- migrate existing pathway values without breaking existing deployments;
- retain legacy setting names only as temporary compatibility aliases;
- keep consolidation proposal tokens conceptually separate because consolidation is not generation.

### KD-002 — One generation confidence threshold

Use one global minimum-confidence threshold for candidates emitted by every knowledge-producing pathway. Pathways inherit it by default and may define an explicit override inside their own accordion. Do not expose disconnected telemetry and skill/playbook confidence controls outside the inheritance/override model.

The shared threshold governs whether a generated candidate is accepted. It does not replace quality scoring, similarity thresholds, consolidation confidence, or automatic-application policy.

### KD-003 — Remove all legacy consolidation and dedup paths

All knowledge consolidation must use the shared hygiene/consolidation architecture: candidate discovery, preview, structured proposal, policy/review, transactional apply, lineage, and reversal.

Remove immediate legacy similarity-based merge/refine behavior from telemetry and every other knowledge-creation pathway. Creation-time consolidation, when enabled, must call the same shared preview/apply service. No producer may directly merge, increment, retire, or rewrite an existing knowledge record based only on embedding similarity.

### KD-004 — One global generation schedule

Use one global schedule for all knowledge-producing pathways. At the scheduled time, one orchestrated run processes the enabled pathways in a deterministic order. Pathways inherit it by default and may define an explicit schedule override inside their own accordion. Do not expose disconnected knowledge, skill/playbook, or telemetry schedules outside the inheritance/override model.

The global generation schedule does not include knowledge hygiene/consolidation maintenance. Hygiene remains separately triggered by manual analysis, explicit creation-time policy, or its own maintenance policy because it mutates and governs already-created knowledge rather than producing source candidates.

### KD-005 — One evidence threshold for scheduled and threshold-triggered synthesis

Use one global minimum-evidence threshold for intelligence-to-knowledge synthesis, with the established pathway/entity override pattern. The global scheduled run and the early threshold trigger must use the same effective threshold and batch-sizing rule. Remove the separate nightly `knowledge_schedule_floor` behavior.

### KD-006 — One generated-record activation policy with pathway overrides

Use one global generated-record status policy, with pathway-specific overrides following the standard inheritance pattern. Every producer must resolve `pathway override → global default`; no producer may silently hardcode `active` or `draft`.

The product/UI choices are “Approve immediately” and “Create as draft”, with **Approve immediately** retained as the global default for backward compatibility. Display persisted `status='active'` as **Approved** in the UI; approved records are available to agents and retrieval, while draft records remain administrator-only. Preserve the underlying `active` database/API value as the backward-compatible operational status.

Every transition to approved must capture approval audit data: approver actor/type, approval timestamp, and approval origin/policy (manual, generated-policy, consolidation, import, or system). Automatic approval is still approval and must be distinguishable from human approval. Pathway overrides use `inherit`, `approve_immediately`, or `create_as_draft` product semantics while legacy configuration remains readable during migration.

### KD-007 — Persist source embeddings

Persist embeddings for confirmed intelligence and telemetry/interactions used by knowledge-producing pathways. Do not clear telemetry embeddings after processing. Store and validate embedding provenance (provider/model, dimensions, serialization/version, generated timestamp) and provide resumable backfill/re-embedding for historical sources.

Retention, access, and storage controls may be tuned operationally, but source embeddings required for novelty detection and provenance tracing must remain available for the lifetime of their source records.

### KD-008 — Source-first pre-generation novelty discovery

Before an expensive knowledge-generation call, compare the new source evidence with previously processed evidence of the same source type using compatible persisted embeddings. Use the matched historical source IDs to trace the Knowledge records they previously produced through `source_intelligence_ids` and `source_ai_interaction_ids`, then resolve any retired Knowledge record through `merged_into` to its active canonical successor.

All producers must persist complete source-to-Knowledge provenance. In particular, telemetry reflection must populate `source_ai_interaction_ids` for every emitted candidate; current entity/day reflection logging alone is insufficient.

Source similarity is a discovery and cost-routing signal. KD-009 defines the initial routing policy and calibration defaults.

### KD-009 — Three-way pre-generation evidence routing

Route every eligible evidence bundle through three outcomes:

1. **Low similarity:** run normal new-Knowledge generation, then post-generation hygiene.
2. **Moderate similarity:** trace the related active canonical Knowledge and run a structured evidence-revision assessment using the complete canonical plus new evidence. The result may be `no_change`, `revise`, `create_new`, or `manual_review`. Any revision is versioned, audited, provenance-linked, validated, and transactional; similarity never directly overwrites content.
3. **Very high similarity:** skip the expensive generation LLM only when deterministic evidence-coverage safeguards pass, then link the new source evidence to the same canonical and record an audit/evidence event. Do not discard the evidence or rewrite content.

Initial calibration defaults:

- low: aggregate similarity below `0.78`;
- moderate: `0.78` through below `0.95`;
- very high: `0.95` or above.

The very-high route additionally requires compatible embedding provenance, near-complete source-member coverage, matches resolving to one canonical, and no deterministic context/outcome conflict. These values are starting defaults only and must be calibrated per embedding model and production pathway distributions before enabling no-LLM skips.

### KD-010 — Persist embeddings across all four tiers

Persist embeddings for Tier 0 interactions/telemetry, Tier 1 memories, Tier 2 intelligence, and Tier 3 Knowledge. Do not clear embeddings after processing. Every tier must record compatible embedding provenance and support coverage reporting plus resumable backfill/re-embedding.

Embedding retention is required for source-novelty gating, semantic retrieval, lineage tracing, and production calibration.

### KD-011 — Index retrieval with full always-on Knowledge

Retire full-record injection for ordinary retrieved/matched Knowledge. Agent-facing context returns ordinary matches only as the lean Knowledge index representation: id, name, category, signals, summary, and governed facets. Agents retrieve complete content explicitly by Knowledge ID when needed.

Active Knowledge records marked `always_inject` are the explicit exception: inject every such record with complete content on every context request. They are prepended before matched index entries and remain exempt from semantic relevance floors, facet/category filtering, and the ordinary retrieval-result cap.

Remove the full/index mode control and the general full-mode runtime path after a backward-compatible deployment migration. Keep the full always-on path as an intentional documented contract rather than treating it as a legacy-mode exception.

### KD-012 — Semantic relevance floor for matched index entries

Apply the relevance floor only to ordinary semantically matched Knowledge index entries. A floor of `0` disables similarity rejection while retaining relevance/quality ranking. Start production at `0`, persist embeddings across all tiers, collect similarity distributions, and calibrate a nonzero floor later. Always-on Knowledge bypasses this floor by design.

### KD-013 — Generate governed facets in the primary generation call

Every structured Knowledge-generation pathway must emit governed facets as part of its primary LLM result. Validate facet keys, types, and configured values deterministically before persistence. Do not make a second facet-extraction LLM call for normally generated records.

Preserve explicit caller-provided facets; generated facets may fill missing keys but must never erase authoritative metadata. Store facet schema version plus extraction/validation provenance. Keep a separately triggered extraction path only for manual/imported legacy records and resumable backfill.

### KD-014 — Explicit facets filter; profile-derived facets boost

Facets explicitly supplied by a caller/API are strict retrieval filters. Facets inferred from an entity profile influence ranking but do not hard-filter Knowledge out of the result set.

Replace raw JSON as the primary UI with a governed facet-schema editor and profile-property mapper. Keep raw JSON under Advanced. Make facet backfill versioned and resumable with coverage plus `succeeded`, `no_facet`, and `failed` outcomes so empty or failed records are not repeatedly charged.

### KD-015 — Versioned, explainable Knowledge quality model

Replace the current compressed score with one global versioned quality model:

- 35% evidence strength, based on normalized unique evidence bundles and diversity with diminishing returns;
- 30% Bayesian outcome feedback, neutral with no feedback and resistant to tiny samples;
- 20% unified generation confidence;
- 15% validation and provenance completeness.

Treat staleness/decay separately from quality and remove legacy merge count and simple record age from the quality formula. Recalculate quality transactionally whenever evidence, feedback, validation/activation, consolidation, or provenance changes. Store the score version and component breakdown for audit, UI explanation, and backfill.

Do not expose formula weights as normal operator settings. Replace “Quality Gauges” with score explanation, input coverage, feedback health, and recalculation/backfill status.

### KD-016 — Relocate non-Knowledge controls

Move Memory Generation Interaction Types from Knowledge settings to the Memories configuration because it governs Tier 0 → Tier 1 input selection. Move interactions, memories, and Knowledge queue concurrency controls to system-level Advanced / Performance settings because they govern infrastructure throughput rather than Knowledge behavior. Preserve runtime keys and values; this is a UI ownership change.

### KD-017 — Three Knowledge settings subtabs

Organize `/app/settings?tab=memory&memoryTab=knowledge` into exactly three subtabs:

1. **Knowledge Generation** — controls and actions that create Knowledge: generate-next-batch/process-backlog actions; one global generation schedule, token budget, confidence threshold, and evidence threshold; entity/pathway overrides; Approved-versus-Draft policy; enabled producers; skill/playbook/telemetry generation; and generation prompt/model configuration.
2. **Knowledge Maintenance** — controls and actions that evaluate or change the existing corpus: source-novelty routing thresholds and evidence-link health; consolidation/hygiene modes and cluster controls; Analyze Now and proposal/run status; embedding coverage/backfill across all tiers; quality component health/recalculation; lineage/reversal access; export; and maintenance audit visibility.
3. **Knowledge Retrieval** — controls governing what agents receive: index result limit; semantic relevance floor; full always-on Knowledge management; governed facet schema; explicit-filter/profile-boost mapping; facet coverage and versioned backfill; and retrieval-health visibility.

Do not add a fourth Advanced tab. Place rare or technical controls in collapsed **Advanced** sections within the owning subtab. Show a compact shared status/header above the subtabs only when it summarizes all three areas; it is not a separate tab.

### KD-018 — Knowledge Generation layout and pathway ownership

Order the Knowledge Generation subtab as follows:

1. **Shared Global Generation Controls** — global schedule, maximum output tokens, minimum confidence, evidence threshold, and Approved-versus-Draft policy. These are inherited by every pathway unless that pathway explicitly overrides them.
2. **Generation Actions and Status** — Generate Next Batch, Process Backlog, current backlog/run state, last outcome, and actionable failures.
3. **Knowledge Generation Pathways** — pathway accordion cards for declarative Knowledge, telemetry reflection, skill/playbook extraction, and any future producer.

Each pathway accordion owns all pathway-specific configuration:

- enabled/disabled state and effective readiness;
- source and produced Knowledge categories;
- inheritance state and pathway overrides for shared global controls;
- applicable entity-type overrides;
- task system prompt and Prompt Manager linkage;
- provider account, compute model, reasoning/thinking options, and execution-engine settings;
- pathway-specific validation, recent status, and save/reset-to-global actions.

Do not place pathway/entity overrides, prompts, models, or execution controls in separate cards below the pathway list. The collapsed pathway header should summarize provider/model, readiness, trigger strategy, and which settings are overridden; expanding it reveals the complete configuration shown in the pathway card design.

## Verified findings

1. `telemetry_reflection_confidence_min` filters the confidence reported by the telemetry-reflection LLM for each proposed learning. Candidates below the threshold are discarded.
2. Telemetry reflection and intelligence-to-knowledge generation are independent producers with separate schedules, prompts, inputs, output schemas, and token budgets.
3. `extraction_confidence_threshold` is currently consumed by the intelligence-cluster skill/playbook extraction pathway, not by telemetry reflection or general knowledge generation.
4. Telemetry candidates use the canonical category-aware embedding path on creation, but embedding generation is best-effort and a record may be inserted without an embedding if generation fails.
5. Telemetry currently performs an immediate legacy similarity/dedup check using `dedup_similarity_threshold`. A newly inserted active record enters the newer creation-time hygiene workflow only when `knowledge_hygiene_creation_time_enabled` is enabled; otherwise it is considered by later manual or scheduled hygiene runs.
6. `knowledge_max_tokens` is shared by intelligence-to-knowledge generation, legacy refine-on-merge, and the new consolidation proposal call. Its current UI description presents it only as a knowledge-generation limit, so the coupling is not visible to the operator.
7. `knowledge_auto_activate` is applied by telemetry and skill/playbook extraction, but the primary intelligence-to-knowledge pathway currently calls `insert_knowledge` with its default `active` status and does not consult this setting. The UI claim that the dial governs every creation pathway is therefore inaccurate.
8. The nightly `knowledge_schedule_floor` replaces both eligibility threshold and batch size for the scheduled run. This can synthesize smaller, differently-sized batches than the normal threshold trigger, despite both controls appearing to govern the same generation pipeline.
9. “Prior Context — Semantic Matches” is generation prompt context used to discourage repetition. `context_knowledge_*` controls agent-facing retrieval/injection. Their similar naming hides that they affect different consumers.
10. Generation-time “Prior Context — Semantic Matches” overlaps with creation-time hygiene candidate discovery. Both perform semantic retrieval against existing active knowledge, but they query from different representations: the former embeds the incoming intelligence batch before generation, while the latter compares the completed generated record. The generation prompt can suppress, reshape, or implicitly blend knowledge without a consolidation proposal, complete source records, lineage, or audit event.
11. The current generation response schema has no `skip`, `duplicate`, or `existing_record_id` outcome. Existing-knowledge references therefore cannot deterministically prevent creation. They only instruct the LLM not to repeat the supplied snippets; when the LLM returns non-empty content, the pipeline continues toward insertion. The legacy post-generation/pre-insert dedup check is the component that currently prevents a new row by directly merging into an existing record.
12. Existing-knowledge reference lookup is active only for automatic confirmed-intelligence → knowledge synthesis (`generate_knowledge_from_intelligence`), including next-batch, backlog-drain, and scheduled knowledge runs. It embeds the concatenated, PII-scrubbed incoming intelligence batch (truncated to 2,000 characters), then returns the nearest `N` active knowledge records globally across all categories. It has no minimum-similarity cutoff, category constraint, entity constraint, or facet constraint, so “similar” currently means nearest available vectors rather than verified duplicates or even necessarily strong matches.
13. Confirmed intelligence records normally retain durable embeddings. Interaction/telemetry embeddings are generated during ingestion but are deliberately cleared after memory processing to limit database growth, so historical telemetry cannot currently support the proposed comparison without re-embedding or storing a durable derived signature.
14. Intelligence and telemetry records do not become retired when Knowledge is consolidated. Knowledge lineage lives on Knowledge records; source intelligence remains confirmed and telemetry remains in the immutable interaction log/reflection history. A source-novelty gate therefore needs explicit processed-evidence provenance rather than using active/retired Knowledge status as a proxy.
15. Knowledge already supports both `source_intelligence_ids` and `source_ai_interaction_ids`, enabling historical-source → Knowledge traversal. Telemetry reflection currently fails to populate `source_ai_interaction_ids`, while the playbook pathway does populate it; this provenance gap must be corrected before source-first gating is reliable across all pathways.
16. Agent-facing Knowledge relevance is computed from the average embedding of the entity's ten most recent embedded interactions, then blended as 70% semantic relevance and 30% Knowledge quality. Because interaction embeddings are currently cleared after processing, this query can lose its semantic signal and fall back to quality ordering; KD-007 corrects that underlying problem.
17. `context_knowledge_min_similarity` is currently fail-open: records with missing embeddings pass the floor, a missing conversation vector passes every record, and the SQL error fallback ignores the floor entirely. The UI label therefore overstates how strictly the setting filters results.
18. `context_knowledge_count` caps only ordinary retrieved records. Every active `always_inject` record is prepended in full, bypasses facets and the cap, and remains full-content even in index mode.
19. Full retrieval mode returns complete content and metadata for every selected record; index mode returns id/name/category/signals/summary/facets and expects the agent to fetch full content on demand. A count of 30 has materially different context-token cost between the two modes.
20. Current quality scores cluster around `0.20–0.29` by construction: a new record commonly contributes `0.025` from evidence breadth (`1/10 × 25%`), `0` from outcome, `0.075–0.135` from confidence, `0` from merge count, and about `0.10` from recency.
21. Knowledge feedback increments `success_count` or `failure_count` but never recalculates `outcome_signal` or `quality_score`. The formula's 30% outcome component therefore remains zero despite feedback.
22. Evidence breadth is populated inconsistently. General intelligence-to-Knowledge generation leaves the default `1` even when multiple intelligence records contributed; telemetry uses `1`; playbooks use distinct entity count; skills use hardcoded scoring inputs. Scores are therefore not comparable across pathways.
23. General Knowledge generation does not request an extraction-confidence field and inherits the storage default `0.5`, while telemetry/playbook pathways use LLM-reported confidence. The confidence component is not semantically consistent across categories/pathways.
24. The quality recomputation job processes only active Knowledge with a non-null embedding. Drafts and active records missing embeddings retain stale or null scores, even though quality inputs are not inherently dependent on an embedding.
25. Facet extraction currently uses a separate LLM call per generated record with a fixed 400-token cap. This duplicates generation cost and uses the `knowledge_generation` task configuration rather than a separately observable structured extraction stage.
26. `enrich_metadata_with_facets` overwrites any caller-provided `metadata.facets` with the extraction result, including `{}` on disabled/failed extraction, so valid manual/imported facets can be lost.
27. The facet schema governs keys but not a controlled value vocabulary. Values are scalar strings normalized mainly by casing against values already stored, so synonyms and multi-value contexts remain inconsistent.
28. Facet backfill repeatedly selects active records whose facets remain empty. Records with legitimately no extractable facets or repeated extraction failures can incur the same LLM cost on every run because no attempted/version state is stored.


## Pending product decisions

None currently.
