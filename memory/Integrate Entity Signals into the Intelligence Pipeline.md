# Integrate Entity Signals into the Intelligence Pipeline

This plan outlines the changes needed to wire the structured signals we just created into the `memory_tasks.py` pipeline, effectively replacing the obsolete "Knowledge Types" system.

## User Review Required

> [!IMPORTANT]
> The AI pipeline will now strictly categorize intelligence based on the signal names you define in the Entity Designer. 
> Example: If the LLM observes a pricing objection, it will map it to the signal name `"Objections & Risk"`, which acts as the `knowledge_type`.

## Proposed Changes

### Backend

#### [MODIFY] `memory_tasks.py`
We will update the `_compact_memories_intelligence` function (and the knowledge generation equivalent, if applicable) to inject the structured signals:

1. **Fetch Config:** Inside the task worker, fetch the `memory_entity_type_config` for the active `entity_type`.
2. **Format Signals:** Parse the `intelligence_signals_prompt` JSON array. If it exists, format it into a clear markdown instruction block mapping each signal name to its description.
   *Example Output to LLM:*
   ```markdown
   Available Target Signals:
   - "Budget & Readiness": Evidence of confirmed budget, approved spending...
   - "Risk & Blockers": Pricing pushback, integration concerns...
   ```
3. **Prompt Injection:** Add these instructions to the LLM's `system_prompt`.
4. **Auto-Tag Instruction:** Explicitly instruct the LLM to output the exact `name` of the matching signal in the JSON `knowledge_type` field. Provide instructions to use "other" if no signals match.

#### [MODIFY] `memory_db.py`
* Update the fallback system prompts seeded in DB migrations to reflect the new dynamic signal tagging structure, ensuring the LLM knows to expect dynamic categories rather than guessing.

## Verification Plan

### Automated/Manual Testing
- Manually trigger an intelligence generation task for a `contact` entity that has our new default signals configured.
- Verify the task successfully executes.
- Inspect the resulting `intelligence` database record to ensure the `knowledge_type` field is correctly populated with one of the specific signal names (e.g., "Budget & Readiness") instead of generic terms or "other".
- Validate the generated insight is factually mapped to the mapped category description.
