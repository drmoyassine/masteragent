# Knowledge Settings and Pipeline Refactor — Delivery Report

## Shipped behavior

- Knowledge settings are presented as three sub-tabs: **Knowledge Generation**, **Knowledge Maintenance**, and **Knowledge Retrieval**.
- Generation is ordered as: global defaults, actions/recent runs, then independent pathway accordions.
- Each generation pathway contains its prompt/model configuration plus pathway and entity-specific overrides.
- Schedule, maximum output tokens, minimum confidence, evidence threshold, and Approved-versus-Draft policy resolve through entity → pathway → global defaults.
- One daily Knowledge orchestration job invokes all enabled producers. Legacy individual queue job names and endpoints remain accepted for backward compatibility.
- Tier 0–3 embeddings are retained with model, version, dimensions, and timestamp provenance. The embedding backfill and coverage gauge cover all four tiers.
- Declarative, telemetry, playbook, and skill generation perform source-evidence similarity analysis before their generation LLM call.
- Low similarity permits new generation. Moderate similarity invokes evidence-to-canonical revision assessment in enforced mode. Very high similarity links corroborating evidence to the active canonical record and skips generation in enforced mode.
- Direct pairwise merge/refine calls were removed from Knowledge producers, Hermes, and skill imports. Consolidation is handled by the shared hygiene preview/apply architecture.
- Generated facets are requested in the primary generation response and validated against the governed schema. The older second facet-generation call is no longer used by the revised automatic producers.
- Quality score v2 is versioned and explainable, combining evidence strength, Bayesian outcome feedback, generation confidence, provenance completeness, and approval assurance.
- Ordinary retrieved Knowledge is injected as a compact index entry. Records marked `always_inject` remain fully injected.
- Explicit request facets are hard filters. Profile-derived facets provide a bounded ranking boost and do not exclude otherwise relevant records.
- A positive relevance floor strictly excludes records without a compatible query/record embedding. A floor of zero ranks without exclusion.
- Retired Knowledge remains excluded from agent context, semantic search, full-text search, and direct agent retrieval, while remaining visible to administrators with lineage.
- Manual creation, manual edits, imports, and generated records stamp embedding and approval provenance and trigger quality recalculation.

## Compatibility and rollout

- Existing storage values `active` and `draft` remain unchanged; the UI presents these as **Approved** and **Draft**.
- Legacy settings columns and individual queue job names remain readable during migration, but runtime policy uses the canonical settings.
- The one-time settings migration copies legacy values into canonical globals/pathway overrides without overwriting a completed migration.
- Evidence routing defaults to `analysis_only`. Production can calibrate observed similarity metrics before switching to `enforced`.
- Knowledge hygiene defaults remain review-first; this refactor does not silently enable automatic consolidation.

## Verification completed

- Python compilation succeeds for the backend.
- Production frontend build succeeds.
- `66` focused Knowledge tests pass, covering the existing consolidation suite and the new policy, quality, and pre-generation routing behavior.
- The full HTTP integration suite requires the configured backend/PostgreSQL service; it was not runnable against an absent local service during this implementation session.

## Production activation checklist

1. Deploy the additive database migration before enabling new routing.
2. Run the Tier 0–3 embedding backfill and confirm the coverage gauge reaches the expected level.
3. Keep evidence routing in `analysis_only` and inspect route metrics on production evidence.
4. Calibrate the moderate and very-high similarity thresholds for the configured embedding model.
5. Switch routing to `enforced` only after reviewing analysis results.
6. Keep consolidation in `proposal_only` or `manual_only` until proposals have been production-validated.
