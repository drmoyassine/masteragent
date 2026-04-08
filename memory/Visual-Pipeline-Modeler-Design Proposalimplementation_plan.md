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

### 3. Analytics Pipeline (Tiers 2 & 3: Insights & Lessons)
*Governs high-level deductions.*
- **Insight Sweep Rules**: 
  - Trigger: E.g., "Run every Sunday" or "Run after user receives 3 new Memories".
  - Prompt Editor: Customize the Analyst Persona.
- **Lesson Mining Rules**:
  - Threshold triggers (e.g., "5 matching insights = 1 Global Protocol").
  - Auto-Approve vs Draft toggles.

## Future: AI-Assisted Configuration
Because the platform is fundamentally schema-driven, we can eventually add a **"Pipeline Architect AI"**. It would be a chat window where you say: *"I'm hooking up an Intercom webhook. I want strict PII filtering, simple daily summaries, and I want to extract feature requests into insights."* The AI will automatically patch the JSON config in Postgres, dynamically turning on the necessary nodes.

## Open Questions for the Brainstorm
1. **Visual Style**: Do you prefer a simple Tabbed Form layout (like the current settings panel but deeper), or a literal Node-Graph (boxes connected by lines like in tools such as n8n / Voiceflow) to represent the pipeline flow?
2. **Granularity**: Do we build one global pipeline that applies to all data, or do you want to define specific pipelines *per source* (e.g., WhatsApp ingestion follows a different set of ML rules than Email ingestion)?

> [!TIP]
> The easiest path forward is to build a Tab-based interface first, iterating on the raw configuration logic in Postgres, before ever attempting a complex drag-and-drop Node UI.
