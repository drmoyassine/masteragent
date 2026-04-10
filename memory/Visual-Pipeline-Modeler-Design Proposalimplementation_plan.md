# Visual Memory Pipeline Modeler: Design Proposal

This document outlines a blueprint for transforming the static "Advanced Settings" page into a highly flexible, visual, node-based or tab-based **No-Code Memory Modeler**.

## Question 1: How to test the current pipeline?
Right now, your processing pipeline is executed by the background worker defined in `backend/memory_tasks.py`. 

To safely test it without waiting for the 2:00 AM chron job:
1. **Manual Endpoint Trigger**: You have an admin endpoint (typically `POST /api/memory/admin/compact/{entity_type}/{entity_id}` and `POST /api/memory/admin/generate-daily-memories`) created to manually force a sweep of the database. 
2. **Postman/cURL**: Send a POST to that endpoint, and then watch the Docker logs (`docker compose logs -f backend`) to see the steps executed (NER extraction → PII scrubbing → Summary generation → DB Commit). 

## Proposal: Configuration-Driven Memory Modeler

To achieve maximum flexibility, we shift from a single global logic block to **Pipeline Templates**. You can visually map how data flows across the 4 tiers.

We will rebuild the Memory Settings UI into a horizontal tabbed interface matching your memory architecture:

### 1. Ingestion Pipeline (Tier 0)
*Governs how raw data enters the system and is prepped.*
- **Gateways**: Universal On/Off switch for accepting generic API payloads.
- **PII Shielding**: 
  - Toggle: `[ON/OFF]`
  - Dropdown: Select LLM Provider (e.g., Zendata API vs Local Regex).
- **Vectorization**:
  - Toggle: `[Auto-Embed Raw Interactions]`
  - Defines if raw interactions should be chunked and vectorized instantly, or only processed at the memory tier.
  - Controls: Chunk Size (400), Chunk Overlap (80), Model (OpenAI `text-embedding-3`).

### 2. Generalization Pipeline (Tier 1: Memories)
*Governs how interactions are aggregated into daily snapshots.*
- **Trigger Condition**: 
  - Scheduled (Cron script editor, e.g., "02:00 AM") OR Threshold-based (e.g., "Every 10 pending interactions").
- **Entity Extraction (NER)**:
  - Toggle: `[Run NER on Pending Interactions]`
  - Model Selector: Fast Local (GLiNER) vs Intelligent (GPT-4o-mini).
  - Schema Editor: A visual tag-input where you define allowed classes (`Person`, `Company`, `Product`, `Emotion_State`).
- **Synthesis Engine**:
  - Form: Editable system prompt (e.g., "You are an AI rolling up interactions...").
  - Schema Mapper: Allows mapping the LLM output to custom JSON fields.
- **Prior Memory Context Injection** *(NEW — see detailed section below)*:
  - Toggle: `[Inject Prior Memories into Generation Context]`
  - Slider/Input: Chronological Memory Count (0–5, default 2)
  - Slider/Input: Semantic Memory Count (0–5, default 2)
  - Input: LLM Context Window Hard Cap (characters, default 10000)
  - Editable Prompt: Prior context instructions for the LLM

### 3. Analytics Pipeline (Tiers 2 & 3: Insights & Lessons)
*Governs high-level deductions.*
- **Insight Sweep Rules**: 
  - Trigger: E.g., "Run every Sunday" or "Run after user receives 3 new Memories".
  - Prompt Editor: Customize the Analyst Persona.
- **Lesson Mining Rules**:
  - Threshold triggers (e.g., "5 matching insights = 1 Global Protocol").
  - Auto-Approve vs Draft toggles.

---

## Prior Memory Context Injection: Full Design

### Problem Statement

Currently, each daily memory is generated in **total isolation**. The LLM sees only today's raw interactions + NER signals. It has zero awareness of what it already knows about this entity. This causes three concrete failure modes:

1. **Fact Repetition**: The same background facts (name, nationality, goals) are redundantly restated in every memory because the LLM doesn't know it already captured them.
2. **Lost Continuity**: Follow-up messages like *"I sent the documents you asked for"* produce shallow summaries because the LLM doesn't know what documents were requested.
3. **No Progression Tracking**: Status changes (e.g., "Fresh → Contacted → Qualified") can't be detected without prior state awareness.

### Solution: Hybrid Prior Context Injection

Before calling the summarization LLM, fetch a **deduplicated** set of prior memories for the same entity and inject them as a `--- Prior Context ---` section in the prompt. The hybrid approach combines:

- **Chronological**: Last N memories ordered by date (captures narrative flow)
- **Semantic**: Top N memories by pgvector cosine similarity to today's raw interactions (captures topically relevant history even if weeks old)

After fetching both sets, deduplicate by memory ID. The result is typically 3-4 unique memories from 2+2 inputs, since recent memories are often also semantically similar.

### Recommended Defaults

| Parameter | Default | Range | Rationale |
|-----------|---------|-------|-----------|
| `prior_memory_enabled` | `TRUE` | Boolean | Feature toggle |
| `prior_memory_chronological_count` | `2` | 0–5 | Last 2 covers immediate narrative thread |
| `prior_memory_semantic_count` | `2` | 0–5 | Top 2 semantic matches surface relevant distant history |
| `llm_context_char_limit` | `10000` | 5000–30000 | Hard cap on total characters sent to LLM |

**Why 2+2 and not 3+3?** With GLM-5's tokenizer (or similar non-Western-optimized models), 10K characters of English text can consume 3K–4K tokens. Each prior memory averages ~400 chars. 2+2 (deduplicated to ~3 unique = ~1,200 chars) leaves ~8,800 chars for raw interactions and NER signals. At 3+3, the prior context section grows to ~2,000 chars and starts cannibalizing the primary input budget.

### Database Schema Changes

```sql
-- Add to memory_settings table
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS prior_memory_enabled BOOLEAN DEFAULT TRUE;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS prior_memory_chronological_count INT DEFAULT 2;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS prior_memory_semantic_count INT DEFAULT 2;
ALTER TABLE memory_settings ADD COLUMN IF NOT EXISTS llm_context_char_limit INT DEFAULT 10000;
```

### Backend Implementation (`memory_tasks.py`)

Insert between steps 5 (Build LLM context) and 6 (LLM generates memory) in `generate_memory_for_entity_date()`:

```python
# 5.5 Fetch prior memories for context continuity
prior_context = ""
if settings.get("prior_memory_enabled", True):
    chrono_count = settings.get("prior_memory_chronological_count", 2)
    semantic_count = settings.get("prior_memory_semantic_count", 2)
    
    with get_memory_db_context() as conn:
        cursor = conn.cursor()
        
        # Chronological: last N memories for this entity
        prior_memories = {}
        if chrono_count > 0:
            cursor.execute("""
                SELECT id, date, content_summary FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND date < %s AND content_summary IS NOT NULL
                  AND LENGTH(TRIM(content_summary)) > 20
                ORDER BY date DESC LIMIT %s
            """, (entity_type, entity_id, interaction_date, chrono_count))
            for row in cursor.fetchall():
                prior_memories[row["id"]] = row
        
        # Semantic: top N most similar (requires embedding of today's content)
        if semantic_count > 0 and embedding is not None:  
            # Use the NER payload embedding or raw text embedding
            cursor.execute("""
                SELECT id, date, content_summary FROM memories
                WHERE primary_entity_type = %s AND primary_entity_id = %s
                  AND date < %s AND content_summary IS NOT NULL
                  AND LENGTH(TRIM(content_summary)) > 20
                  AND embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector LIMIT %s
            """, (entity_type, entity_id, interaction_date, 
                  str(today_embedding), semantic_count))
            for row in cursor.fetchall():
                if row["id"] not in prior_memories:
                    prior_memories[row["id"]] = row
        
        # Format deduplicated prior memories
        if prior_memories:
            sorted_priors = sorted(prior_memories.values(), key=lambda m: m["date"])
            prior_lines = [f"[{m['date']}] {m['content_summary']}" for m in sorted_priors]
            prior_context = "\n".join(prior_lines)
```

The prior context is then injected into the LLM payload:

```python
llm_context = (
    f"Entity: {entity_type} / {entity_id}\n"
    f"Date: {interaction_date}\n"
    f"Interaction count: {len(interactions)}\n\n"
    f"--- Prior Context (established facts, do NOT repeat) ---\n{prior_context}\n\n"
    f"--- Raw Interactions ---\n{raw_text}\n\n"
    f"--- Extracted Signals ---\n{ner_summary}"
)
```

### System Prompt Update

The default memory generation prompt must be expanded to instruct the LLM on how to handle prior context:

```
You are an AI memory system. Based on the provided interaction data, write a concise 
factual memory record.

PRIOR CONTEXT RULES:
- Previous memories for this entity are provided under "Prior Context"
- These represent ESTABLISHED facts. Do NOT repeat them.
- Focus EXCLUSIVELY on NEW information from today's interactions.
- Note any progressions, status changes, or contradictions with prior records.
- If today's interactions contain no new information beyond what's in prior context, 
  write a brief note stating "No significant new information recorded."

OUTPUT RULES:
- Return only the summary text, 2-5 sentences.
- Focus on key facts, decisions, named entities, and action items.
```

### UI/UX Controls (`GeneralMemorySettings.jsx`)

Add a new Card inside the existing Memory Generation grid, placed directly after the existing "Memory Generation" card:

```
┌─────────────────────────────────────────────────────┐
│ 🧠 Prior Memory Context                    [ON/OFF] │
│ Inject previous memories when generating new ones   │
│                                                     │
│ Chronological Memories    ──●──────── 2             │
│ Most recent N memories for narrative continuity     │
│                                                     │
│ Semantic Memories         ──●──────── 2             │
│ Top N most relevant prior memories (pgvector)       │
│                                                     │
│ Context Window Limit      [10000___] chars           │
│ Hard cap on total characters sent to the LLM        │
│                                                     │
│ ┌─ System Prompt ─────────────────────────────────┐ │
│ │ You are an AI memory system. Based on the       │ │
│ │ provided interaction data, write a concise...   │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Control Types:**
- **Toggle (Switch)**: `prior_memory_enabled` — master on/off. Disables all controls below when OFF.
- **Slider or NumberInput**: `prior_memory_chronological_count` — range 0 to 5, step 1.
- **Slider or NumberInput**: `prior_memory_semantic_count` — range 0 to 5, step 1.
- **NumberInput**: `llm_context_char_limit` — range 5000 to 30000, step 1000.
- **Textarea**: Editable system prompt, loaded from `memory_system_prompts` table with `prompt_type = 'memory_generation'`.

### Quality Gate: Memory Injection Filter

Not all prior memories should be injected. A memory qualifies for injection only if:
1. `content_summary IS NOT NULL`
2. `LENGTH(TRIM(content_summary)) > 20` — filters out truncated/failed generations like "She"
3. `date < current_interaction_date` — never inject today's own memory (circular reference)

This prevents error propagation from broken memories polluting future generations.

### Implementation Phases

**Phase 1 (Hardcoded Patch — DONE):**
- Hardcode 2+2 chronological+semantic injection directly in `generate_memory_for_entity_date()`
- Bump context char limit from 8K to 10K
- Update default system prompt inline
- No database schema changes, no UI controls
- Ship immediately

**Phase 2 (Configurable — Future):**
- Add `prior_memory_*` columns to `memory_settings` via migration in `memory_db.py`
- Add `llm_context_char_limit` column
- Replace hardcoded values in `memory_tasks.py` with `settings.get()` lookups
- Build UI Card in `GeneralMemorySettings.jsx` with sliders, inputs, and prompt editor
- Add API endpoint for saving/loading the system prompt
- Test with multiple entity types and verify deduplication logic

---

## Future: AI-Assisted Configuration
Because the platform is fundamentally schema-driven, we can eventually add a **"Pipeline Architect AI"**. It would be a chat window where you say: *"I'm hooking up an Intercom webhook. I want strict PII filtering, simple daily summaries, and I want to extract feature requests into insights."* The AI will automatically patch the JSON config in Postgres, dynamically turning on the necessary nodes.

## Open Questions for the Brainstorm
1. **Visual Style**: Do you prefer a simple Tabbed Form layout (like the current settings panel but deeper), or a literal Node-Graph (boxes connected by lines like in tools such as n8n / Voiceflow) to represent the pipeline flow?
2. **Granularity**: Do we build one global pipeline that applies to all data, or do you want to define specific pipelines *per source* (e.g., WhatsApp ingestion follows a different set of ML rules than Email ingestion)?

> [!TIP]
> The easiest path forward is to build a Tab-based interface first, iterating on the raw configuration logic in Postgres, before ever attempting a complex drag-and-drop Node UI.
