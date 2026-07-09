# Pairwise → Clustering Knowledge Hygiene Plan

**Status:** Reviewed, code-grounded, language-neutral — ready for phased implementation
**Date:** 2026-07-09 (rev. 2026-07-10 — language-neutral architecture revision)
**Owner:** drmoy
**Reference implementation:** Python (`pip install masteragent`) — the canonical impl. A future TypeScript implementation (`npm install masteragent`) will reproduce **this architecture** (§2, §4, §20). The **architecture, not the implementation, is what must remain stable.**
**Implementer:** hand-off agent — see §17 (per-phase build spec) and §18 (acceptance/rollback).
**Depends on:** PR #43 (creation-dedup/auto-activate/signal-casing), PR #44 (admin route repath), PR #45 (unified dedup threshold), PR #46 (Explorer counts + pagination).

---

## 1. Purpose

Define the **language-agnostic architecture** for MasterAgent Memory's knowledge hygiene — replacing pairwise-cosine consolidation with **semantic clustering + structured canonical records**.

The Python package is the **canonical reference implementation**, not a prototype. A future TypeScript package will reproduce the same concepts, data models, APIs, and behaviors by implementing the **same interfaces and algorithms** defined here. Therefore every architectural decision maximizes **portability, simplicity, deterministic behavior, ease of implementation, and long-term maintainability** — over sophisticated language-specific algorithms.

This revision is grounded in the actual code (all file/line anchors verified 2026-07-09) and:
- corrects places the original draft diverged from the code (§6),
- right-sizes the machinery to real volume and de-risks the dependency chain (§9, §16),
- defines stable, language-neutral module boundaries both runtimes will follow (§4),
- gives an implementation-grade phase spec another agent can execute without re-discovering the codebase (§17),
- acceptance criteria, tests, rollback per phase (§18),
- resolved decisions for every open question (§19),
- per-module portability notes for the future TS impl (§20).

---

## 2. Architectural principles

These principles are normative — they constrain every decision below.

1. **Python-first.** The production Python implementation is the primary target. We do **not** redesign around edge runtimes. Future TS support is achieved by preserving the architecture, not by changing today's implementation.
2. **Language-neutral core.** Every core component is implementable almost identically in Python and TypeScript.
   - **Prefer:** graph traversal, connected components, union-find, cosine similarity, centroid calculation, deterministic serialization, JSON/YAML, Markdown rendering, BFS/DFS, simple threshold graphs.
   - **Avoid in core:** HDBSCAN, scipy, sklearn pipelines, FAISS, pickle serialization, native compiled extensions, runtime-specific optimizations. These may exist later as **optional adapters** (Python-only extras) but MUST NOT be part of the core architecture or required for behavioral parity.
3. **Stable core modules** (§4): Models, Serialization, Embeddings, Clustering, Canonicalization, Retrieval, Storage, Migration. These boundaries remain stable across implementations.
4. **Clustering = graph-based connected components** as the default, behind a swappable interface (§9). Deterministic, dependency-free, portable.
5. **Structured knowledge is tri-partite** (§7): distinguish the **canonical object** (in-memory typed record), the **storage format** (Markdown serialization), and the **embedding representation** (deterministic serialized text). Markdown is a serialization/rendering format, **not** the canonical in-memory representation.
6. **Centralized embedding pipeline** (§8): all embeddings flow through one function (`serialize_for_embedding` → embedder). No duplicate embedding logic anywhere.
7. **Production upgrade path** (§15): small, incremental, reversible, production-safe migration. **No rewrite.**
8. **Minimize infrastructure** (§12): recompute clusters, deterministic graph construction, lightweight metadata, **derived state over persisted state** wherever practical. No serialized cluster models, no pickled models, no `approximate_predict`.
9. **Future portability** (§20): the TS implementation reproduces behavior by implementing the same interfaces and algorithms. Optional Python-only adapters (e.g., HDBSCAN) are not required for parity because the **default** algorithm is portable.

---

## 3. Objective (from the spec, with one explicit deviation)

When performing knowledge consolidation/de-dup:

1. **Use semantic clustering**, not pairwise similarity as the primary grouping mechanism.
2. Cluster related records; allow unrelated records to remain unclustered ("noise" / singletons).
3. Process each cluster independently → produce one high-quality **canonical** knowledge record.
4. Pairwise cosine similarity is permitted **only within an existing cluster** (exact-dup detection, cohesion/outlier detection, merge decisions). It MUST NOT be the primary clustering algorithm.
5. Knowledge is stored as **structured, typed objects** (not freeform text). The **entire structured record** is the embedding input (not title/summary, not raw source).
6. Per cluster: validate cohesion → eject unrelated → merge duplicates → preserve all unique info → remove duplicated info → resolve contradictions → emit one canonical record → record merged source IDs (traceability).

**Explicit deviation from the spec wording (recorded, not silent):** the spec says *"prefer HDBSCAN or another density-based clustering algorithm."* Per Principle 2, **the default core algorithm is graph-based connected components, not density-based HDBSCAN.** Rationale: density-based libraries (HDBSCAN/scipy/sklearn) are Python-ecosystem, native-compiled, and not portable to a future edge-native TS runtime. Connected components (union-find over a cosine threshold graph) is deterministic, dependency-free, and trivially reproducible in TS. Density-based clustering remains available as an **optional Python-only adapter** behind the `Clusterer` interface (§9) — not core, not required for parity.

**Guiding principle:** knowledge as structured, typed semantic objects; clustering over the semantic meaning of those structured objects.

---

## 4. Module architecture (the stable spine)

Both implementations organize around these eight modules. Interfaces below are written in a neutral IDL Python and TypeScript can both implement.

### 4.1 Models
The typed **canonical** knowledge object (in-memory source of truth), the category enum, the cluster assignment, and settings.
```
KnowledgeRecord: { id, category, name, summary, structured: CanonicalObject, status, metadata, ... }
CanonicalObject: declarative schema fields (§7) — the parsed, typed record
Category: "best_practices" | "lessons_learned" | "trade_knowledge" | "playbook" | "skill"
ClusterAssignment: { label: int, member_ids: string[], centroid: number[] | null }
```
*Portability:* plain data shapes — TS interfaces mirror Python dataclasses/TypedDicts exactly.

### 4.2 Serialization
Convert between the **canonical object** and the **storage format** (KNOWLEDGE.md / SKILL.md Markdown) and JSON. Deterministic, round-trippable.
```
render(canonical) -> markdown        # canonical object -> .md storage format
parse(markdown)   -> canonical       # .md -> canonical object
to_json(canonical) -> string         # storage/transport
from_json(string)  -> canonical
```
*Portability:* the Markdown grammar (frontmatter + fixed H2 sections) and the parse contract (§7) are identical in both runtimes.

### 4.3 Embeddings
One chokepoint. Produces the **embedding representation** (deterministic text) and the vector.
```
serialize_for_embedding(record) -> string   # a.k.a. build_embedding_document()
embed(record) -> number[]                    # serialize_for_embedding -> EmbedderProvider
```
`EmbedderProvider` is an interface (OpenAI adapter today; swappable). *No other call site builds the embedding string.*

### 4.4 Clustering
```
interface Clusterer { cluster(records: {id, vector}[], opts) -> ClusterAssignment[] }
GraphClusterer implements Clusterer   # default (§9)
# Future optional adapters (Python-only, not parity-required):
# AgglomerativeClusterer, HDBSCANClusterer
```
Deterministic. Output is **derived state** — always rebuildable from embeddings (§12).

### 4.5 Canonicalization
Cluster → one canonical record.
```
canonicalize(cluster: ClusterAssignment) -> CanonicalResult
CanonicalResult: { canonical: KnowledgeRecord | null, ejected: string[], contradictions: [...], confidence: float, action: "merged"|"skipped_low_confidence"|"singletons" }
```
Pipeline: deterministic cosine ejection → preservation-first LLM merge → confidence gate (§10). The LLM is invoked through a `GeneratorProvider` interface (provider-agnostic).

### 4.6 Retrieval
`get_context(...)` — unchanged routing; benefits from richer embeddings for free (§19 Q9).

### 4.7 Storage
The `knowledge` table (records) + `knowledge_clusters` (derived cluster map) + traceability columns. SQL/pgvector — the same DB and queries serve both runtimes.

### 4.8 Migration
Incremental, flagged, resumable backfills + schema `ALTER`s following the existing idempotent ALTER-after-CREATE pattern (§6 C5).

---

## 5. Current state (code-verified 2026-07-09)

### 5.1 Storage (`backend/memory_db.py`, knowledge table ~line 273)
- Live columns at CREATE TABLE: `id, seq_id, source_intelligence_ids, signals, name, content, summary, embedding (vector), visibility, tags, created_at, updated_at`. The richer columns (`category, metadata, quality_score, merge_count, source_pathway, evidence_breadth, status, version, last_merged_at, outcome_signal, extraction_confidence`) are added by **`ALTER TABLE ADD COLUMN`** after the CREATE block (schema is additive-migrated in-place). Indexes for `category/status/signals` are created after those ALTERs.
- `category` ∈ {`skill`, `playbook`, `best_practices`, `lessons_learned`, `trade_knowledge`} (5).
- **`embedding` is an untyped `vector`** (no dimension pinned) → **no HNSW/IVF index** (commented out at ~243–269 "to support flexible embedding sizes"). All similarity is a brute-force sequential scan via `<=>`.
- `content` for `skill`/`playbook` = a **SKILL.md** document. For the 3 declarative categories `content` = **freeform text**.

### 5.2 Structured-doc helpers (`backend/memory_skill_md.py`) — already broader than the original draft claimed
- `SKILL_MD_CATEGORIES = ("skill","playbook")`, `render_skill_md`, `parse_skill_md`, `is_skill_md`, `slugify`.
- **`render_knowledge_md` (line 114) and `render_any_knowledge_md` (line 159) already exist** for declarative categories — but they are **export-only, flat**: frontmatter + `# Title` + the raw `content` blob. There is **no sectioned schema and no parser** for declarative records. This is the real gap; the new format must **supersede `render_knowledge_md`**, not sit beside it.

### 5.3 Embedding (`backend/services/embeddings.py`)
- `generate_embedding(text)` (line 12) and `generate_embeddings_batch(texts)` (line 43). Model from admin config, default `text-embedding-3-small`. 30s / 60s timeouts. Returns `[]` on missing config.
- **Embedding input is `f"{name}. {summary or content}"` — duplicated in 5 call sites**, not one:
  - `memory_knowledge.py:224` (generate) and `:315` (promote)
  - `memory_dedup.py:155` (refine-on-merge re-embed)
  - `memory_telemetry.py:177` (telemetry→knowledge)
  - `memory_playbooks.py:415` (skill embedding; `:261` uses a **centroid** vector, not text)
- There is **no shared "embed a knowledge record" function** — the string is hand-built at each site. This is the single biggest source of future drift, and the first thing to fix (§8, Phase 1).

### 5.4 De-dup / consolidation (current) — four creation-time pathways, one weekly job
Creation-time guard (`memory_dedup.find_similar_existing`, line 11 → `refine_or_increment_merge`, line 67) is invoked from **all four** creation paths:
1. `memory_knowledge.py:238` (intelligence→knowledge)
2. `memory_telemetry.py:183` (telemetry→knowledge)
3. `memory_playbooks.py:261` (playbook, matched on **centroid**)
4. `memory_playbooks.py:423` (skill)

All use `1 - (embedding <=> new) > dedup_similarity_threshold` (0.85, PR #45), same-category, `status != 'retired'`, `ORDER BY … LIMIT 1`. `refine_or_increment_merge` LLM-refines content (gated by `knowledge_refine_on_merge`) and **re-embeds with the same `name+summary` string** (dedup.py:155) — so even the merge path perpetuates the shallow embedding.

Weekly consolidation (`memory_consolidation.run_consolidation`, line 23 → `_consolidate_duplicates`, line 35): pairwise self-join (`a.id < b.id`, same category, both active), top-50 by similarity, greedy keep-higher-`merge_count`, retire loser, `_refine_playbook` if kept is a playbook. Then `_apply_decay` + `_recompute_quality_scores`.

**No clustering. No cluster map. No back-pointer from a retired record to its survivor** (retirement is a bare `status='retired'`; the only lineage is `source_intelligence_ids` + `merge_count`).

### 5.5 Volume (measured 2026-07-09)
- ~591 active: 250 `best_practices`, 256 `lessons_learned`, 62 `trade_knowledge`, 15 `playbook`, 9 `skill`.
- A consolidation run at 0.85 found **zero duplicate pairs** → today's records are content-distinct on the current shallow embedding. (The earlier "384 near-duplicates" was a misread — those were 384 distinct records created 2026-07-08.)

---

## 6. Corrections to the original draft (read before building)

| # | Draft said | Reality | Consequence |
|---|---|---|---|
| C1 | "Add new `memory_knowledge_md.py`, adapted from skill_md" | `render_knowledge_md`/`render_any_knowledge_md` already live in `memory_skill_md.py` (flat, export-only, no parser) | Build the sectioned format **into `memory_skill_md.py`** (or a new module the old renderer delegates to). **Delete/replace** the flat `render_knowledge_md`. Do not ship two declarative renderers. |
| C2 | Embedding input change touches "embeddings.py, memory_knowledge.py, memory_dedup.py" | Input string is built at **5 sites across 4 files**, incl. telemetry + skill + the re-embed inside merge | Introduce **one `serialize_for_embedding()` + `embed()` choke-point** and route all 5 sites through it, or the fix is partial. |
| C3 | Phase 5 "replaces `find_similar_existing` guard" (singular, in memory_knowledge.py) | **4** creation-time guards call it (knowledge, telemetry, playbook-centroid, skill) | Overlay-guard rollout must cover the declarative paths; keep `find_similar_existing` as the within-cluster fallback and wrap it. |
| C4 | "record merged source IDs" as if a field exists | **No `merged_from`/`merged_into` column exists** | Add columns (§12, §17 Phase 4). Cheap, high-value traceability. |
| C5 | Schema table implied columns live in CREATE TABLE | They're added via `ALTER TABLE ADD COLUMN` after CREATE | New columns/tables follow the **same ALTER-after-CREATE idempotent pattern**. |
| C6 | `get_context` open question | Retrieval already renders via `render_any_knowledge_md` | The new format slots into that dispatcher; no retrieval rewrite. |

---

## 7. Structured knowledge model (tri-partite — Principle 5)

Three concepts, kept distinct:

1. **Canonical object** — the in-memory typed record (the source of truth code manipulates). For declarative categories it has the fields below. For skill/playbook it is the parsed SKILL.md object.
2. **Storage format** — the canonical object serialized to **Markdown** (KNOWLEDGE.md / SKILL.md) stored in the `content` column. **Markdown is a serialization format, not the canonical representation.** `render`/`parse` (§4.2) convert between them. Parsed fields are mirrored into `metadata` for programmatic access (existing skill/playbook pattern).
3. **Embedding representation** — `serialize_for_embedding(canonical)` → deterministic text of populated fields → embedder (§8). This is distinct from the storage Markdown (cleaner, populated-only, stable order).

### 7.1 KNOWLEDGE.md schema (declarative: best_practices, lessons_learned, trade_knowledge)

**Frontmatter (YAML):**
```yaml
---
name: <slug>                 # slugify(title)
description: <summary>       # 1–2 sentences: what + when it applies
metadata:
  source: masteragent
  category: best_practices | lessons_learned | trade_knowledge
  version: <int>
  quality_score: <float?>
  signals: [ ... ]
  tags: [ ... ]
  subcategories: [ ... ]
  topics: [ ... ]
  keywords: [ ... ]
  entities: [ ... ]
---
```

**Body — fixed section order (H2 headings are the parse contract):**
```
# <Title>
## Problem
## Knowledge
## Best Practices
## Lessons Learned
## Common Mistakes
## Recommendations
## Related Concepts
## Examples
## References
## Source Content
```

### 7.2 Parse contract (`parse_knowledge_md`)
- Reuse the frontmatter reader from `parse_skill_md` (top-level scalars + one nested `metadata:` map — extend it to read the list fields).
- Body: split on `^## ` headings; map heading → section key (lowercased, spaces→`_`). **Unknown headings are preserved verbatim** in a `_extra` bucket (forward-compatible). Missing sections → empty string, never an error.
- **Round-trip guarantee:** `parse(render(x)) == x` for all populated fields (unit test, §18).
- `render_knowledge_md` is rewritten to emit these sections from the parsed canonical object / `metadata`; the old flat signature is kept as a thin shim for one release (deprecation warning), then removed.
- **All sections ship in the schema; empty sections are allowed.** The embedding serializer (§8) skips empty sections so they never dilute the vector.

### 7.3 SKILL.md field expansion (skill/playbook) — DEFERRED
The spec lists fields absent from today's SKILL.md (`prerequisites`, `required_tools`, `inputs/outputs`, `decision_points`, `success_criteria`, …). **Deferred:** SKILL.md already renders/parses and skill/playbook are out of clustering scope (§9.4). Non-blocking; track separately. Do not gate this plan on it.

---

## 8. Embedding pipeline (Principle 6 — one chokepoint)

- **`serialize_for_embedding(record) -> str`** (working name `build_embedding_document`): concatenates **populated** frontmatter values + each non-empty body section as `"<Section>: <text>"`, newline-joined, whitespace-collapsed, **deterministic field order**. This is the embedding input — not raw Markdown, not `name+summary`.
- **`embed(record) -> number[]`**: `serialize_for_embedding` → `EmbedderProvider.embed` (OpenAI adapter today; swappable). Records `metadata.embedding_version = 2`.
- **All 5 call sites (§5.3) route through `embed(record)`.** In `memory_playbooks.py:261` (centroid path) the centroid math is unchanged; only the per-record text-embed sites switch.
- **Fallback:** if a record is still unstructured (no `.md`), serialize `name + summary + content` (never regress to `name+summary` only).
- Re-embed on create, merge, edit. One-time batch backfill via `generate_embeddings_batch`, resumable (`WHERE metadata->>'embedding_version' IS DISTINCT FROM '2'`).
- `text-embedding-3-small`: 8191-token context; a full record ≈ 1–3k tokens → **no truncation**.
- **Pin `embedding` to `vector(1536)`** (Phase 1). HNSW index is a separate later enhancement (note, don't block).

---

## 9. Clustering (Principle 4 — graph-based default, behind an interface)

### 9.1 Clusterer interface
```
interface Clusterer {
  cluster(records: { id: string, vector: number[] }[], opts: ClusterOpts) -> ClusterAssignment[]
}
ClusterOpts: { edge_threshold: float, min_size: int }
```
Output: `{ label, member_ids, centroid }`. Singletons/noise get their own label and are left alone.

### 9.2 Default implementation — `GraphClusterer` (language-neutral)
The algorithm both runtimes implement identically:
1. Take the active records' vectors for one category.
2. Compute pairwise **cosine similarity** (`1 - (a·b)/(|a||b|)`).
3. Build an undirected graph: edge between `i,j` iff `cosine(i,j) ≥ edge_threshold` (**0.80** start).
4. **Connected components via union-find** (deterministic, O(n·α(n))).
5. Components with `size < min_size` (**2**) → treated as singletons (noise).
6. **Centroid** per component = L2-normalized mean of member vectors.

Properties: **deterministic** (same vectors → same clusters), **zero dependencies** beyond vector math, O(n²) cosine (trivial at ~568 declarative records, sub-second), trivially portable to TypeScript.

### 9.3 Swappable — optional adapters only
`AgglomerativeClusterer` (sklearn), `HDBSCANClusterer` (hdbscan) may be added later as **Python-only adapters** behind the same interface. They are **not** part of core, **not** required for TS parity, and **not** on the default path. The TS implementation ships `GraphClusterer` only — which is the documented default, so parity holds.

### 9.4 Scope — declarative only
Cluster `best_practices` / `lessons_learned` / `trade_knowledge`. Leave `skill` (9) and `playbook` (15) on their existing path in `memory_playbooks.py` (`_process_cluster` @191, centroid match @261, skill dedup @423). Too few per-category for meaningful grouping, and they already have their own dedup.

### 9.5 Derived state — recompute, never persist a model
Clusters are recomputed every consolidation run from current embeddings. `knowledge_clusters` (§12) stores the result for audit + centroid lookup but is **always rebuildable**. **No fitted-model object, no pickle, no `approximate_predict`** (Principle 8).

### 9.6 Chaining risk (the one real weakness of connected components) — and its mitigations
Connected components can chain: A~B (0.85), B~C (0.82), A≁C (0.70) → all three fused. Mitigations, in order:
1. **Rich full-record embeddings** (Phase 1) separate records more than today's `name+summary`, lowering false edges.
2. **Deterministic cosine ejection** in Canonicalization (§10) catches chain-bridged members (mean intra-cluster cosine below floor → ejected to singleton).
3. **High edge threshold** (0.80) keeps edges meaningful.
This is explicitly accepted: connected-components + ejection is the portable, good-enough design; density-based is available as an adapter if a future probe (§15 Phase P) proves ejection insufficient.

---

## 10. Canonicalization (the destructive step — engineered for safety)

Canonicalization is the one irreversible-ish operation (retired sources are recoverable via `merged_into`, but the canonical record is what agents retrieve). Design = **bias-to-preserve + auditable + gated on uncertainty**. Language-neutral.

### 10.1 Pipeline
1. **Deterministic cosine ejection** (no LLM): for each member, compute mean pairwise cosine to the rest of the cluster; below the **0.70 floor → eject to singleton**. Spec-compliant ("pairwise… identify outlier records"). This targets exactly the chaining failure mode (a record that rode in on one 0.81 edge but is ~0.50 to the majority).
2. **Preservation-first LLM merge** (the synthesis): emit one canonical KNOWLEDGE.md from the cohesive remainder.
3. **Confidence gate**: apply the merge only if `confidence ≥ 0.6`; else skip + log.

### 10.2 Merge prompt principles (in priority order)
1. **Lossless** — every unique fact, step, example, reference, caveat survives. Loss is a failure.
2. **Dedup only verbatim/near-verbatim overlaps** — never collapse two merely-similar points.
3. **Contradictions** (same field, different values) → **preserve both + flag** inline ("Note: sources disagree — X / Y"). Never silently pick one.
4. **Include-don't-drop default** — if unsure whether something belongs, include it.
5. **Structured output** — KNOWLEDGE.md sections; serialize populated-only.
6. **No invention** — never fabricate facts/examples/references.

Return JSON: `{ title, summary, sections:{…}, contradictions:[{section, conflict}], confidence: 0–1 }`.

### 10.3 Confidence gate (safety valve)
`confidence < 0.6` → **skip the merge**, leave records unmerged, log `low_confidence_skip` to `pipeline_runs` with the contradictions array. Worst case = "no merge," never "lost data." Records stay retrievable; the cluster can be reviewed or re-attempted after more evidence.

### 10.4 Contingencies
- **Large clusters (> ~8 members):** hierarchical sub-merge (merge small sub-groups, then merge partials). Unlikely at current scale; defined for safety.
- **Singletons/noise:** no merge, no LLM call.

### 10.5 Traceability (§12)
- Canonical: `merged_from TEXT[]` = all absorbed source IDs; `metadata.contradictions` = flagged conflicts (audit).
- Retired sources: `status='retired'`, `merged_into = canonical_id`. **Nothing hard-deleted** → fully reversible.

---

## 11. Creation-time overlay (centroid assignment — no `approximate_predict`)

1. New declarative record → render KNOWLEDGE.md → `embed(record)`.
2. Load `knowledge_clusters` centroids for the record's category; compute **max cosine** to any centroid.
3. Decision:
   - `≥ assign_threshold` (**0.82**) → consolidate into that cluster's `canonical_record_id` via the existing `refine_or_increment_merge` (now deep-embedding).
   - `< assign_threshold` → insert as standalone (a future run may cluster it).
4. `skill`/`playbook` (§9.4): unchanged (`find_similar_existing` path).
5. **No `approximate_predict`, no pickled model** (Principle 8). Centroids are derived from the last run; stale-but-acceptable between runs; borderline cases defer to the next run.

---

## 12. Storage & cluster map (minimized infrastructure — Principle 8)

### 12.1 `knowledge` table additions (idempotent ALTER-after-CREATE)
- `merged_from TEXT[] DEFAULT '{}'` (on canonical — absorbed source IDs).
- `merged_into TEXT` (on retired — back-pointer to canonical).
- Pin `embedding vector(1536)` (Phase 1).

### 12.2 `knowledge_clusters` (derived, recomputed each run)
```
category TEXT, cluster_label INT, member_ids TEXT[],
canonical_record_id TEXT, centroid vector, updated_at TIMESTAMPTZ
```
Index on `(category, cluster_label)`. **No `knowledge_cluster_models` table, no BYTEA/pickle.** The table is always rebuildable from embeddings (§9.5).

### 12.3 Cold start
Empty map → creation-time guard falls back to `find_similar_existing`/insert; the next consolidation run builds the map.

---

## 13. Settings / dials (extend the existing settings map)

Reuse `get_memory_settings`. Safe defaults:
- `knowledge_structured_embedding_enabled` (default **true** after Phase 1 backfill; false during rollout) — routes embeds through `serialize_for_embedding`.
- `knowledge_clustering_enabled` (default **false** until Phase P passes).
- `cluster_algorithm` = `connected_components` (default). `agglomerative` / `hdbscan` are **optional Python-only adapters**, selectable but not required for parity.
- `cluster_edge_threshold` (graph cosine cutoff; start **0.80**).
- `cluster_assign_threshold` (creation-time centroid cosine; start **0.82**).
- `cluster_ejection_floor` (mean intra-cluster cosine to eject; start **0.70**).
- `canonical_min_confidence` (apply merge only above; start **0.6**).
- `cluster_min_size` (drop clusters smaller than this to singletons; start **2**).
- Keep `dedup_similarity_threshold` (0.85) for **within-cluster** exact-dup detection.

All surface in the existing admin settings UI.

---

## 14. Data volume reality check (drives every sizing decision)

| Category | Active | Clustered here? | Notes |
|---|---:|---|---|
| best_practices | 250 | ✅ | primary clustering target |
| lessons_learned | 256 | ✅ | primary clustering target |
| trade_knowledge | 62 | ✅ | small but viable |
| playbook | 15 | ❌ (§9.4) | own path in `memory_playbooks.py` |
| skill | 9 | ❌ (§9.4) | own path in `memory_playbooks.py` |

Re-fit cost at this scale is sub-second; migration is ~591 one-time LLM calls (batchable). No index needed for clustering (vectors load into memory). Nothing here justifies persisted models or `approximate_predict`.

---

## 15. Phased plan (sequence & PR grouping)

| Phase | Scope | Key files | Risk |
|---|---|---|---|
| **1 — Centralized deep embedding** | `serialize_for_embedding()` + `embed()`; route all 5 sites; batch re-embed backfill; pin `vector(1536)` | `services/embeddings.py`, new embedding-input helper (in `memory_skill_md.py` or `memory_embedding_input.py`), `memory_knowledge.py`, `memory_dedup.py`, `memory_telemetry.py`, `memory_playbooks.py`, `memory_db.py` | Low (fallback) |
| **0 — KNOWLEDGE.md format** | Sectioned `render_knowledge_md`/`parse_knowledge_md`; tri-partite model; supersede flat renderer | `memory_skill_md.py` (+ tests) | None (shim old signature) |
| **P — Probe & calibrate** | After 0+1 backfill: re-run consolidation + throwaway `GraphClusterer` probe; **calibrate thresholds** (edge/min_size/ejection/assign) on real data; confirm cohesion is acceptable | scratch script; short written finding | None (analysis) |
| **2 — Structured creation** | Prompts emit KNOWLEDGE.md for declarative; zero-regression freeform fallback | `memory_knowledge.py`, `memory_telemetry.py`, seeded prompts | Low (fallback) |
| **3 — Cluster map** | `Clusterer` interface + `GraphClusterer` (declarative-only); `knowledge_clusters` table; recompute | new `memory_clustering.py`, `memory_db.py` | Low (additive) |
| **4 — Cluster canonicalization + traceability** | Deterministic ejection + preservation-first LLM merge + confidence gate; `merged_from`/`merged_into`; replace `_consolidate_duplicates` (declarative) | `memory_clustering.py`, `memory_consolidation.py`, `memory_db.py` | Medium |
| **5 — Creation-time centroid overlay** | Centroid assignment for declarative creation; skill/playbook unchanged | `memory_knowledge.py`, `memory_telemetry.py`, `memory_clustering.py` | Medium |
| **6 — Migration backfill** | LLM re-structure declarative → KNOWLEDGE.md; re-embed all; guarded/resumable | queue/job + `memory_db.py` | Low (one-time) |
| **7 — Frontend** | Render KNOWLEDGE.md sections; optional cluster-review UI | `KnowledgeInspector.jsx`, `KnowledgeTab.jsx` | None |

**PR 1:** Phase 1 + Phase 0 (embedding chokepoint + KNOWLEDGE.md format + backfill). Independently valuable, zero-regression, prerequisite for all else.
**Gate:** Phase P probe → confirm thresholds on real data (note: this is **threshold calibration, not an algorithm swap** — connected-components is the chosen default).
**PR 2:** Phases 3–5 (map + canonicalization + overlay), declarative-only.
**PR 3+:** Phase 2 (structured creation), Phase 6 (migration), Phase 7 (frontend).

> Phase 1 ships before Phase 0's parser is wired into creation: the embedding chokepoint + backfill is what unblocks the probe, and the fallback path keeps unstructured records working.

---

## 16. Risks & mitigations

- **Mixed-embedding drift** (old `name+summary` vs new full-record) skews clustering. → Backfill re-embed **before** enabling clustering (`knowledge_clustering_enabled=false` until backfill done); or filter the map to `metadata.embedding_version = 2`.
- **Connected-components chaining** (A~B~C fusion). → Rich embeddings (Phase 1) + deterministic ejection (§10.1) + high edge threshold (§9.6). Accepted; density-based is an optional adapter if a probe proves ejection insufficient.
- **Canonicalization data loss** (LLM drops unique info). → Preservation-first prompt (§10.2); confidence gate (§10.3) skips low-certainty merges; retired sources retained (`status='retired'` + `merged_into`); never hard-delete; `merged_from` for audit/undo.
- **Contradiction handling.** → Prompt: "preserve both, flag the contradiction"; stored in `metadata.contradictions`.
- **Re-embed cost / rate limits.** → `generate_embeddings_batch`, resumable cursor, guard flag.
- **Round-trip parser regressions.** → Property test `parse(render(x))==x` in CI before Phase 2 wires it into creation.
- **Stale centroids at creation time.** → Accepted; borderline records insert as singletons and get pulled in on the next run.
- **TS-portability drift.** → Core uses only portable primitives (§2, §20). Optional adapters (HDBSCAN/agglomerative) are Python-only and clearly marked; the default `GraphClusterer` is the parity contract.

---

## 17. Implementation build-spec (for the implementing agent)

### Phase 1 — `serialize_for_embedding` + `embed` (do first)
1. New `serialize_structured(record: dict) -> str` (place in `memory_skill_md.py` or new `memory_embedding_input.py`):
   - If `category in SKILL_MD_CATEGORIES` and `is_skill_md(content)`: parse via `parse_skill_md`, serialize frontmatter scalars + body.
   - Elif KNOWLEDGE.md (Phase 0 present): parse via `parse_knowledge_md`, serialize frontmatter + **non-empty** sections.
   - Else (unstructured): `f"{name}\n{summary}\n{content}"`.
   - Collapse whitespace; deterministic order; **skip empty fields**.
2. New `async embed(record: dict) -> list[float]` in `services/embeddings.py`: `serialize_structured` → `generate_embedding`. Set `metadata.embedding_version = 2`.
3. Replace the raw `generate_embedding(f"{name}. {summary or content}")` at **all 5 sites** (§5.3) with `embed(record_dict)`. Centroid math at `memory_playbooks.py:261` unchanged.
4. Batch backfill: page active knowledge, `embed` per row (or serialize → `generate_embeddings_batch`), `UPDATE … SET embedding=…, metadata=jsonb_set(metadata,'{embedding_version}','2')`. Resumable.
5. `memory_db.py`: migrate `embedding` to `vector(1536)` (ALTER; guard existing rows). **Do not** add HNSW yet.
6. Gate behind `knowledge_structured_embedding_enabled`.

### Phase 0 — KNOWLEDGE.md
1. In `memory_skill_md.py`: rewrite `render_knowledge_md` to emit §7.1 sections from a parsed dict / `metadata`; add `parse_knowledge_md` (frontmatter reader extended for list fields + `## `-section splitter with `_extra` bucket).
2. Keep old `render_knowledge_md(...)` call sites working via a shim that maps `content`→`## Source Content` and logs deprecation.
3. `render_any_knowledge_md` (line 159) dispatches declarative → new renderer.
4. Tests: round-trip, missing-section tolerance, unknown-heading preservation, empty record.

### Phase 3 — Clusterer interface + GraphClusterer + cluster map
1. `memory_db.py`: `CREATE TABLE IF NOT EXISTS knowledge_clusters (...)` per §12.2 (ALTER-after-CREATE idempotent style). Index `(category, cluster_label)`.
2. `memory_clustering.py`:
   - `interface Clusterer` + `class GraphClusterer` (§9.2): `_load_vectors(category) -> (ids, ndarray)`; build cosine graph `≥ cluster_edge_threshold`; union-find; drop `< cluster_min_size` to singletons; L2-normalized centroids. Pure Python/numpy — **no sklearn/hdbscan**.
   - `build_cluster_map(category)` → upsert `knowledge_clusters`.
   - Return `{label → {member_ids, centroid}}`.
3. Wire into `run_consolidation` behind `knowledge_clustering_enabled`.

### Phase 4 — Canonicalization + traceability
1. `memory_db.py`: `ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS merged_from TEXT[] DEFAULT '{}'`, `ADD COLUMN IF NOT EXISTS merged_into TEXT`.
2. `canonicalize_cluster(member_ids)` in `memory_clustering.py`:
   - Eject: mean intra-cluster cosine `< cluster_ejection_floor` → back to singleton.
   - Merge: preservation-first LLM (§10.2) → one KNOWLEDGE.md + `summary` + `contradictions` + `confidence`.
   - Confidence gate (`< canonical_min_confidence` → skip + log `low_confidence_skip`).
   - Write canonical (reuse highest-`quality_score` member as survivor, or new row); `merged_from = [others]`; each retired source `status='retired', merged_into=<canonical>`; re-embed canonical via `embed(record)`.
3. In `memory_consolidation._consolidate_duplicates`: declarative categories delegate to clustering canonicalization; skill/playbook keep the pairwise path (`_refine_playbook` untouched).

### Phase 5 — Creation-time overlay
1. `assign_to_cluster(category, vector) -> canonical_id | None` in `memory_clustering.py`: load `knowledge_clusters` centroids, max cosine; `≥ cluster_assign_threshold` → return that cluster's `canonical_record_id`.
2. In `memory_knowledge.py` + `memory_telemetry.py` declarative creation guards: try `assign_to_cluster` first; hit → `refine_or_increment_merge(canonical_id, …)`; miss → fall through to `find_similar_existing` then insert. Skill/playbook unchanged.

### Phase 6 — Migration
1. Resumable job: for each declarative record without `## ` sections, LLM re-structure freeform `content` → KNOWLEDGE.md (§7.1), store, re-embed. Guard flag + cursor. Batch. Log per-record to `log_pipeline_run`.

### Phase 7 — Frontend
1. `KnowledgeInspector.jsx` / `KnowledgeTab.jsx`: render KNOWLEDGE.md sections (reuse existing SKILL.md rendering). Optional: cluster-review view listing `knowledge_clusters` with member/canonical + `merged_from`.

---

## 18. Acceptance criteria, tests, rollback (per phase)

- **Phase 1** — *Accept:* all 5 sites call `embed`; backfill sets `embedding_version=2` on 100% active; no record embeds to `[]` silently. *Test:* unit for `serialize_structured` per category incl. empty-field skipping; integration: create a record, assert deep embedding differs from `name+summary`. *Rollback:* flip `knowledge_structured_embedding_enabled=false`.
- **Phase 0** — *Accept:* `parse(render(x))==x` for populated fields; unknown headings preserved. *Test:* the round-trip/tolerance suite. *Rollback:* renderer shim keeps old output.
- **Phase P** — *Accept:* written finding recommends thresholds (edge/min_size/ejection/assign) with the observed cluster-size histogram and cohesion metrics at the new embedding. *No code to roll back.*
- **Phase 3** — *Accept:* `GraphClusterer` is deterministic (same vectors → same labels); `knowledge_clusters` populated for 3 declarative categories; singletons excluded; re-run idempotent. *Rollback:* `knowledge_clustering_enabled=false`.
- **Phase 4** — *Accept:* a known duplicate pair collapses to one canonical with correct `merged_from`/`merged_into`; a synthetic contradiction is preserved-both + flagged; a low-confidence cluster is skipped+logged (not merged); retired sources still queryable; no unique fact lost (spot-check). *Rollback:* disable flag; retired records recoverable; nothing hard-deleted.
- **Phase 5** — *Accept:* a new near-dup record merges into the cluster canonical; a novel record inserts standalone. *Rollback:* disable overlay → existing `find_similar_existing` resumes.
- **Phase 6** — *Accept:* 100% declarative records have KNOWLEDGE.md sections + `embedding_version=2`; resumable after interrupt. *Rollback:* records retain original `content` (write new format additively, keep original in `## Source Content`).

---

## 19. Resolved decisions (was: open questions)

1. **KNOWLEDGE.md body fields** → ship all §7.1 sections; missing render empty; unknown headings preserved in `_extra`; **embedding serializer skips empty fields**.
2. **Expand SKILL.md?** → No (defer; skill/playbook out of clustering scope). Track separately.
3. **Clustering scope** → **per-category, declarative-only** (best_practices/lessons_learned/trade_knowledge); skill/playbook unchanged.
4. **Algorithm** → **`GraphClusterer` (connected components over a cosine ≥ 0.80 threshold graph via union-find)** — the portable default. Density-based (HDBSCAN)/agglomerative are **optional Python-only adapters**, not core, not required for TS parity (Principle 2/4).
5. **"Nearby" radius at creation** → **centroid cosine ≥ `cluster_assign_threshold` (0.82)**. No `approximate_predict` (Principle 8).
6. **Cluster-map persistence** → **centroids-only in `knowledge_clusters`, recomputed each run (derived state)**. No pickled model, no `knowledge_cluster_models` table.
7. **Canonicalization** → **deterministic cosine ejection (0.70 floor) + preservation-first LLM merge + confidence gate (≥ 0.6 to apply, else skip+log)**. Lossless; contradictions preserved-both-and-flagged.
8. **Traceability** → new columns `merged_from TEXT[]` (canonical) + `merged_into TEXT` (retired). Queryable, indexable. Not metadata.
9. **`get_context` retrieval** → no change; already routes through `render_any_knowledge_md`. Richer embedding improves recall for free.
10. **Migration ordering** → **re-embed backfill (Phase 1) first**, then re-structure to KNOWLEDGE.md (Phase 6); enable clustering only after both (avoids mixed-embedding drift).

---

## 20. Portability notes (for the future TypeScript implementation)

The TS package reproduces **behavior** by implementing the **same interfaces and algorithms**, not by calling Python. Per module:

- **Models** — mirror the typed shapes (§4.1) as TS interfaces.
- **Serialization** — implement the exact KNOWLEDGE.md/SKILL.md grammar and the `parse` contract (§7.2): same frontmatter rules, same H2 section keys, same `_extra` preservation, same round-trip guarantee. `render` must be deterministic (same field order).
- **Embeddings** — implement `serialize_for_embedding` identically (same populated-only, same deterministic text); `EmbedderProvider` is an HTTP adapter (OpenAI or compatible) — provider-agnostic, no native dep.
- **Clustering** — implement `GraphClusterer` in pure TS: cosine + threshold graph + union-find + L2-normalized centroid (§9.2). **No native dependencies.** This is the parity contract; optional adapters (HDBSCAN/agglomerative) are Python extras and intentionally absent in TS — acceptable because they are not the default.
- **Canonicalization** — implement the same ejection math (cosine) and the same LLM prompt contract (§10.2) over the same provider HTTP adapter. Deterministic ejection must produce identical eject decisions given identical vectors.
- **Retrieval / Storage** — same DB (Postgres + pgvector), same SQL/queries. pgvector is runtime-agnostic.
- **Migration** — same phased flags and backfill cursors.

**Parity boundary:** the default path (Models → Serialization → Embeddings → `GraphClusterer` → Canonicalization → Storage) is fully reproducible in TS. Anything Python-only (HDBSCAN/agglomerative adapters) is explicitly out of the parity contract.

---

## 21. Code references (verified 2026-07-09)

- `backend/memory_db.py` — knowledge CREATE ~273, `embedding vector` line 281 (untyped), HNSW commented 243–269, columns/indexes added via ALTER after CREATE.
- `backend/memory_skill_md.py` — `SKILL_MD_CATEGORIES` 17, `render_skill_md` 38, **`render_knowledge_md` 114**, **`render_any_knowledge_md` 159**, `parse_skill_md` 204, `is_skill_md` 27, `slugify` 20.
- `backend/memory_dedup.py` — `find_similar_existing` 11, `increment_merge` 40, `_REFINE_PROMPT` 54, `refine_or_increment_merge` 67 (re-embeds `name+summary` at **155**), `compute_quality_score` 186.
- `backend/memory_consolidation.py` — `run_consolidation` 23, `_consolidate_duplicates` 35 (pairwise self-join), `_refine_playbook` 87, `_apply_decay` 159, `_recompute_quality_scores` 194.
- `backend/memory_knowledge.py` — `generate_knowledge_from_intelligence` 113, embed **224**, creation guard **235–250**, `promote_to_knowledge` 273 (embed **315**).
- `backend/memory_telemetry.py` — embed **177**, `find_similar_existing` **183**, `refine_or_increment_merge` **185**.
- `backend/memory_playbooks.py` — `_process_cluster` 191, centroid `find_similar_existing` **261**, `_generate_skills_from_playbook` 366, skill embed **415**, skill dedup **423**.
- `backend/services/embeddings.py` — `generate_embedding` 12, `generate_embeddings_batch` 43.
- `frontend/src/components/memory/KnowledgeTab.jsx`, `KnowledgeInspector.jsx` — display.
