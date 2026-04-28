# Playbooks — Procedural Memory for MasterAgent

> **Status**: Implementation Plan (Draft)
> **Created**: 2026-04-27
> **Inspired by**: Hermes Agent Skills system — adapted for MasterAgent's structured pipeline architecture

---

## 1. Problem Statement

MasterAgent's memory pipeline excels at **declarative knowledge** — understanding *what is known* about entities. But it lacks **procedural knowledge** — understanding *what to do* when patterns are recognized.

When intelligence signals fire across multiple entities (e.g., "qualification concern" appears for 5+ contacts), the system stores each observation independently but never synthesizes the **action pattern** that works best when this signal appears.

**Playbooks** close this gap by auto-extracting reusable action procedures from cross-entity intelligence patterns.

---

## 2. How Playbooks Differ From Knowledge

| | Knowledge (Tier 3) | Playbooks (new) |
|---|---|---|
| **Question answered** | "What do we know?" | "What should we do?" |
| **Content type** | Declarative observations | Ordered action steps |
| **Scope** | PII-scrubbed, generalized facts | Entity-type-scoped procedures |
| **Source** | Batch of confirmed intelligence | Cluster of semantically similar intelligence across entities |
| **Lifecycle** | Static once created | Versioned, refined by feedback |
| **Retrieval** | Semantic search (agent pulls) | Proactive matching on trigger conditions (system pushes) |

---

## 3. Data Model

### 3.1 New Table: `playbooks`

```sql
CREATE TABLE IF NOT EXISTS playbooks (
    id                      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    seq_id                  BIGSERIAL,
    name                    TEXT NOT NULL,
    description             TEXT,
    entity_type             TEXT NOT NULL,              -- which entity type this applies to
    signal_type             TEXT,                       -- primary intelligence signal category (nullable for cross-signal)
    trigger_conditions      JSONB DEFAULT '[]',         -- semantic trigger keywords/phrases
    steps                   JSONB DEFAULT '[]',         -- ordered procedure steps
    source_intelligence_ids TEXT[] DEFAULT '{}',        -- intelligence records that sourced this playbook
    source_entity_ids       TEXT[] DEFAULT '{}',        -- distinct entities the pattern was observed across
    success_count           INT DEFAULT 0,
    failure_count           INT DEFAULT 0,
    feedback_notes          JSONB DEFAULT '[]',         -- [{agent_id, entity_id, outcome, notes, timestamp}]
    embedding               vector,
    status                  TEXT DEFAULT 'draft',       -- draft | active | retired
    version                 INT DEFAULT 1,
    parent_id               TEXT,                       -- previous version's id (for version chain)
    tags                    TEXT[] DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbooks_entity_type ON playbooks (entity_type);
CREATE INDEX IF NOT EXISTS idx_playbooks_status ON playbooks (status);
CREATE INDEX IF NOT EXISTS idx_playbooks_signal ON playbooks (signal_type);
```

### 3.2 Schema Design Rationale

- **`entity_type`** (required): Playbooks are scoped to an entity type because procedures that work for contacts won't necessarily apply to institutions. This mirrors how `intelligence_signals_prompt` is defined per entity type in `memory_entity_type_config`.

- **`signal_type`** (nullable): The primary intelligence signal category this playbook addresses (e.g., "Qualification & Fit"). `NULL` means it's a cross-signal playbook derived from multiple signal types.

- **`trigger_conditions`** (JSONB array): Semantic keywords/phrases that trigger this playbook's suggestion. Example:
  ```json
  ["qualification concern", "program rejection", "pathway mismatch", "entry requirements unclear"]
  ```
  These are matched against incoming intelligence content via embedding similarity, NOT exact string matching.

- **`steps`** (JSONB array): Ordered action procedure. Example:
  ```json
  [
    {"order": 1, "action": "Acknowledge the concern and validate the student's goals"},
    {"order": 2, "action": "Identify 2-3 alternative programs matching their profile"},
    {"order": 3, "action": "Present fee structure and scholarship options upfront"},
    {"order": 4, "action": "Set a 48-hour follow-up reminder to check decision status"}
  ]
  ```

- **`parent_id`**: When a playbook is refined (new version), the old version is marked `retired` and the new version links back via `parent_id`. This creates an audit chain.

- **`feedback_notes`** (JSONB array): Raw feedback from agents who followed this playbook:
  ```json
  [
    {
      "agent_id": "abc-123",
      "entity_id": "contact-456",
      "outcome": "success",
      "notes": "Student re-engaged after suggesting alternative pathway",
      "timestamp": "2026-04-27T12:00:00Z"
    }
  ]
  ```

### 3.3 Entity Type Config Addition

Add to `memory_entity_type_config`:

```sql
ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS playbook_extraction_threshold INT DEFAULT 3;
ALTER TABLE memory_entity_type_config ADD COLUMN IF NOT EXISTS playbook_auto_activate BOOLEAN DEFAULT FALSE;
```

- **`playbook_extraction_threshold`**: Minimum number of semantically similar intelligence records across different entities before a playbook is extracted. Default: 3.
- **`playbook_auto_activate`**: If true, new playbooks go directly to `active`. If false (default), they go to `draft` for admin review.

### 3.4 Settings Addition

Add to `memory_settings`:

```sql
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS playbook_extraction_threshold INT DEFAULT 3;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS playbook_refinement_threshold INT DEFAULT 5;
```

- **`playbook_refinement_threshold`**: Number of new intelligence records matching an existing playbook's domain before triggering re-synthesis (version bump).

---

## 4. Extraction Pipeline

### 4.1 New Module: `memory_playbooks.py`

Located at: `backend/memory_playbooks.py` (following the pattern of `memory_compaction.py` and `memory_knowledge.py`)

```
memory_playbooks.py
├── run_playbook_check()           — Entry point from background loop
├── _find_playbook_clusters()      — Semantic clustering of intelligence records
├── _generate_playbook()           — LLM call to extract playbook from cluster
├── _check_playbook_refinement()   — Check if existing playbooks need updating
└── _refine_playbook()             — LLM call to update an existing playbook
```

### 4.2 Extraction Flow

```
run_playbook_check()
│
├─ 1. Query confirmed intelligence NOT yet linked to any playbook
│     GROUP BY primary_entity_type
│
├─ 2. For each entity_type with >= threshold unlinked intelligence:
│     │
│     ├─ 2a. Generate embeddings for each intelligence record (already exist)
│     │
│     ├─ 2b. Cluster by cosine similarity
│     │       - Use pgvector: for each intelligence, find the N nearest neighbors
│     │       - Group records that are within similarity_threshold (e.g., 0.82) of each other
│     │       - Filter: cluster must span >= playbook_extraction_threshold DISTINCT entity_ids
│     │
│     ├─ 2c. For each qualifying cluster:
│     │       │
│     │       ├─ Check: does an existing active/draft playbook's embedding
│     │       │         have similarity > 0.85 with cluster centroid?
│     │       │
│     │       ├─ YES → Route to _check_playbook_refinement()
│     │       │         (add new evidence, potentially bump version)
│     │       │
│     │       └─ NO  → Route to _generate_playbook()
│     │                (create new draft playbook)
│     │
│     └─ 2d. Mark processed intelligence as linked (via source_intelligence_ids)
│
└─ 3. Log results
```

### 4.3 Clustering Strategy

Rather than implementing a full clustering algorithm (DBSCAN, k-means), we leverage pgvector's existing infrastructure:

```sql
-- For each unlinked intelligence record, find semantically similar peers
-- across DIFFERENT entities of the same type
SELECT a.id AS anchor_id, b.id AS neighbor_id,
       a.primary_entity_id AS anchor_entity,
       b.primary_entity_id AS neighbor_entity,
       1 - (a.embedding <=> b.embedding) AS similarity
FROM intelligence a
JOIN intelligence b ON a.id < b.id
  AND a.primary_entity_type = b.primary_entity_type
  AND a.primary_entity_id != b.primary_entity_id  -- MUST be different entities
  AND a.status = 'confirmed' AND b.status = 'confirmed'
  AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
WHERE a.primary_entity_type = %s
  AND 1 - (a.embedding <=> b.embedding) > 0.80    -- similarity threshold
  AND NOT EXISTS (
      SELECT 1 FROM playbooks p WHERE a.id = ANY(p.source_intelligence_ids)
  )
ORDER BY similarity DESC
LIMIT 100;
```

Then in Python, we use Union-Find (disjoint set) to group the pairwise results into clusters, and filter for clusters that span >= N distinct entities.

### 4.4 LLM Prompt for Playbook Generation

```
You are a procedural knowledge extractor for a CRM memory system.

You are given a cluster of intelligence signals that were independently observed
across multiple different {{ entity_type }} entities. These signals share a common
pattern — your job is to extract the ACTIONABLE PROCEDURE that works best when
this pattern is recognized.

RULES:
- Extract 3-7 concrete, ordered action steps
- Steps must be actionable (start with a verb)
- Steps must be generalizable (no specific entity names)
- Include trigger conditions: what keywords/phrases indicate this playbook applies
- Name the playbook descriptively

Return JSON:
{
  "name": "...",
  "description": "...",
  "signal_type": "..." or null,
  "trigger_conditions": ["keyword1", "keyword2", ...],
  "steps": [
    {"order": 1, "action": "..."},
    {"order": 2, "action": "..."}
  ],
  "tags": ["..."]
}
```

### 4.5 LLM Prompt for Playbook Refinement

```
You are updating an existing procedural playbook based on new evidence.

EXISTING PLAYBOOK (v{{ version }}):
Name: {{ playbook.name }}
Steps: {{ playbook.steps }}
Based on {{ playbook.source_intelligence_ids | length }} intelligence records
Success: {{ playbook.success_count }}, Failures: {{ playbook.failure_count }}

AGENT FEEDBACK (if any):
{{ playbook.feedback_notes }}

NEW EVIDENCE ({{ new_intelligence | length }} additional intelligence records):
{{ new_intelligence_context }}

RULES:
- Preserve steps that have high success rates
- Modify or add steps based on new evidence and failure feedback
- Do NOT remove steps unless feedback explicitly indicates they are harmful
- Update trigger_conditions if new intelligence reveals additional trigger patterns

Return the same JSON format as initial generation.
```

---

## 5. Pipeline Integration

### 5.1 Pipeline Stage

Add a new pipeline stage: `playbooks` — runs AFTER the intelligence pipeline and PARALLEL to knowledge.

```
interactions → memories → intelligence ──┬──→ knowledge
                                         └──→ playbooks (NEW)
```

### 5.2 LLM Config Seeding

Add to `_seed_defaults()` in `memory_db.py`:

```python
("playbook_generation", "openai", "gpt-4o-mini", "playbooks", 0,
 "You are a procedural knowledge extractor...",  # full prompt above
 ""),
```

### 5.3 Background Loop Integration

In `memory_tasks.py`, add to the background loop after `run_compaction_check()`:

```python
# In _background_loop(), after the daily pipeline:
await run_playbook_check()
```

### 5.4 Queue Integration

Add a new job type in `memory/queue.py`:

```python
elif job.name == "generate_playbook":
    from memory_playbooks import run_playbook_check
    await run_playbook_check()
```

Triggered from the knowledge queue after `generate_lesson`:

```python
# In _background_loop():
await knowledge_queue.add("generate_playbook", {}, {"priority": 2})
```

---

## 6. API Endpoints

### 6.1 Agent-Facing (in `memory/agent.py`)

#### Proactive Retrieval — Enhance `/has-context`

The existing `/has-context` endpoint already returns intelligence and knowledge for an entity. Extend it to include matching playbooks:

```python
# In get_has_context(), after fetching knowledge:
cursor.execute("""
    SELECT id, name, description, steps, signal_type, success_count, status
    FROM playbooks
    WHERE entity_type = %s AND status = 'active'
    ORDER BY success_count DESC
""", (entity_type,))
playbook_rows = cursor.fetchall()

# Additionally: semantic match against entity's latest intelligence
# to surface the MOST RELEVANT playbooks, not just all active ones
```

Add to `ContextStatusResponse`:
```python
playbooks_count: int = 0
playbooks: List[PlaybookContextItem] = []
```

#### Semantic Search — Extend `/search/semantic`

Add `"playbooks"` as a valid layer in `SearchRequest.layers`:

```python
if "playbooks" in request.layers:
    hits = await search_playbooks_by_vector(query_embedding, request.entity_type, request.limit)
    for hit in hits:
        results.append(SearchResult(
            id=hit["id"], layer="playbook", score=float(hit.get("score", 0)),
            name=hit.get("name"), snippet=(hit.get("description") or "")[:200],
            entity_id=None, entity_type=hit.get("entity_type"),
            created_at=str(hit.get("created_at", ""))
        ))
```

#### Playbook Detail

```
GET /api/memory/playbooks/{id}
```
Returns the full playbook with steps. Agents call this after seeing a playbook in context or search results.

#### Feedback Submission

```
POST /api/memory/playbooks/{id}/feedback
{
    "entity_id": "contact-123",
    "outcome": "success" | "failure" | "partial",
    "notes": "Optional free text about what worked or didn't"
}
```

Appends to `feedback_notes` JSONB array and increments `success_count` or `failure_count`.

### 6.2 Admin-Facing (in `memory/admin.py`)

#### List / CRUD

```
GET    /api/memory/admin/playbooks?entity_type=contact&status=active&limit=20&offset=0
GET    /api/memory/admin/playbooks/{id}
PATCH  /api/memory/admin/playbooks/{id}     — edit name, steps, status, trigger_conditions
DELETE /api/memory/admin/playbooks/{id}
```

#### Status Transitions

```
PATCH /api/memory/admin/playbooks/{id}
{ "status": "active" }    — activate a draft playbook
{ "status": "retired" }   — retire a playbook
```

#### Manual Creation

```
POST /api/memory/admin/playbooks
{
    "name": "...",
    "entity_type": "contact",
    "signal_type": "qualification",
    "trigger_conditions": [...],
    "steps": [...],
    "status": "active"
}
```

Admins can create playbooks manually based on domain expertise, not just auto-extraction.

#### Version History

```
GET /api/memory/admin/playbooks/{id}/history
```

Returns the version chain via `parent_id` traversal.

---

## 7. DB Write Helper

### New function in `memory_db_writes.py`

```python
def insert_playbook(
    *,
    playbook_id: str,
    name: str,
    description: str,
    entity_type: str,
    signal_type: Optional[str],
    trigger_conditions: list,
    steps: list,
    source_intelligence_ids: list,
    source_entity_ids: list,
    embedding: Optional[list],
    auto_activate: bool,
    parent_id: Optional[str] = None,
    version: int = 1,
    tags: list = [],
) -> None:
    """INSERT a row into playbooks."""
    status = "active" if auto_activate else "draft"
    now = datetime.now(timezone.utc).isoformat()
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO playbooks (
                id, name, description, entity_type, signal_type,
                trigger_conditions, steps, source_intelligence_ids, source_entity_ids,
                embedding, status, version, parent_id, tags, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            playbook_id, name, description, entity_type, signal_type,
            json.dumps(trigger_conditions), json.dumps(steps),
            source_intelligence_ids, source_entity_ids,
            embedding, status, version, parent_id, tags, now, now,
        ))
```

---

## 8. Pydantic Models

### New models in `memory_models.py`

```python
# ============================================
# Playbook Models
# ============================================

class PlaybookStep(BaseModel):
    order: int
    action: str

class PlaybookCreate(BaseModel):
    name: str
    description: Optional[str] = None
    entity_type: str
    signal_type: Optional[str] = None
    trigger_conditions: List[str] = []
    steps: List[PlaybookStep] = []
    source_intelligence_ids: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    status: str = "draft"

class PlaybookUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    signal_type: Optional[str] = None
    trigger_conditions: Optional[List[str]] = None
    steps: Optional[List[PlaybookStep]] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None

class PlaybookResponse(BaseModel):
    id: str
    seq_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    entity_type: str
    signal_type: Optional[str] = None
    trigger_conditions: List[str]
    steps: List[PlaybookStep]
    source_intelligence_ids: List[str]
    source_entity_ids: List[str]
    success_count: int
    failure_count: int
    status: str
    version: int
    parent_id: Optional[str] = None
    tags: List[str]
    created_at: str
    updated_at: str

class PlaybookFeedback(BaseModel):
    entity_id: str
    outcome: str  # "success" | "failure" | "partial"
    notes: Optional[str] = None

class PlaybookContextItem(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    signal_type: Optional[str] = None
    steps: List[PlaybookStep]
    success_count: int
    failure_count: int
```

---

## 9. Re-exports in `memory_tasks.py`

```python
# ── Playbooks ─────────────────────────────────────────────────────────────────
from memory_playbooks import (  # noqa: E402, F401
    run_playbook_check,
)
```

---

## 10. Frontend Integration (Future Phase)

### 10.1 Memory Explorer — Playbooks Tab

A new tab alongside Interactions | Memories | Intelligence | Knowledge:

```
📋 Playbooks
```

Table columns:
| # | Name | Entity Type | Signal | Steps | Success | Failure | Status | Created | Actions |
|---|---|---|---|---|---|---|---|---|---|

### 10.2 Memory Settings — Playbook Configuration

In `MemorySettings.jsx`, under entity type config:

- **Playbook Extraction Threshold**: slider (default 3)
- **Auto-activate Playbooks**: toggle (default off)

### 10.3 Playbook Detail Panel

Clicking a playbook opens a side panel showing:
- Steps (ordered, editable)
- Trigger conditions (editable tags)
- Source intelligence records (linked)
- Feedback history (timeline)
- Version chain

---

## 11. Implementation Order

### Phase 1: Data Layer (Day 1)
1. Add `playbooks` table to `memory_db.py` (`_create_memory_tier_tables`)
2. Add migration columns to `memory_entity_type_config` and `memory_settings`
3. Add `insert_playbook` to `memory_db_writes.py`
4. Add Pydantic models to `memory_models.py`
5. Seed default LLM config for `playbook_generation` pipeline stage

### Phase 2: Extraction Pipeline (Day 2)
1. Create `memory_playbooks.py` with `run_playbook_check()`, `_find_playbook_clusters()`, `_generate_playbook()`
2. Add `playbook_generation` to pipeline configs
3. Wire into `_background_loop` in `memory_tasks.py`
4. Add `generate_playbook` job type in `memory/queue.py`
5. Add re-exports in `memory_tasks.py`

### Phase 3: API Endpoints (Day 3)
1. Add agent-facing endpoints: `GET /playbooks/{id}`, `POST /playbooks/{id}/feedback`
2. Extend `/has-context` to include matching playbooks
3. Extend `/search/semantic` to include playbooks layer
4. Add admin CRUD endpoints in `memory/admin.py`
5. Add search helper `search_playbooks_by_vector` to `services/search.py`

### Phase 4: Refinement Loop (Day 4)
1. Implement `_check_playbook_refinement()` and `_refine_playbook()`
2. Add version chain logic (parent_id, status transitions)
3. Implement feedback-driven auto-retirement (failure_count > threshold)
4. Test end-to-end: intelligence accumulation → playbook extraction → feedback → refinement

### Phase 5: Frontend (Day 5-6)
1. Playbooks tab in Memory Explorer
2. Playbook detail panel
3. Settings integration
4. Admin CRUD UI

---

## 12. Testing Strategy

### Unit Tests (in `backend/tests/`)
- `test_playbook_extraction.py` — cluster detection, LLM prompt construction
- `test_playbook_api.py` — CRUD endpoints, feedback submission

### Integration Tests
- Seed 5+ intelligence records with similar content across different entities
- Run `run_playbook_check()`
- Verify a draft playbook is created
- Submit feedback via API
- Run refinement check
- Verify playbook version increments

### Manual Verification
- Use existing intelligence data (your contact entity type has qualification, budget, etc.)
- Verify playbooks appear in `/has-context` response
- Verify playbooks appear in semantic search results

---

## 13. Files Changed Summary

| File | Change |
|---|---|
| `memory_db.py` | Add `playbooks` table, config columns, migration |
| `memory_db_writes.py` | Add `insert_playbook()` |
| `memory_models.py` | Add Playbook* Pydantic models, extend ContextStatusResponse |
| `memory_playbooks.py` | **NEW** — extraction pipeline |
| `memory_tasks.py` | Add re-exports, wire into background loop |
| `memory/queue.py` | Add `generate_playbook` job handler |
| `memory/agent.py` | Extend `/has-context`, `/search/semantic`, add playbook endpoints |
| `memory/admin.py` | Add playbook admin CRUD |
| `memory/__init__.py` | No change needed (uses existing routers) |
| `services/search.py` | Add `search_playbooks_by_vector()` |
| `memory_helpers.py` | No change needed |

---

## 14. Open Questions

1. **Similarity threshold for clustering**: Starting with 0.80 cosine similarity. Should this be configurable per entity type?

2. **Cross-entity-type playbooks**: Should playbooks ever span entity types? (e.g., a procedure that works for both contacts and institutions?) Current design scopes to single entity type.

3. **Playbook injection format**: When injecting into agent context via `/has-context`, should we include full steps or just name + description with a link to fetch details? (Progressive disclosure vs. full context injection.)

4. **Maximum playbooks per entity type**: Should there be a cap? Hermes has no formal limit on skills but memory pressure naturally limits them. We could cap at 20-30 active playbooks per entity type.

5. **Feedback attribution**: Should feedback be tied to specific agent interactions (interaction_id) for traceability, or is entity_id + outcome sufficient?
