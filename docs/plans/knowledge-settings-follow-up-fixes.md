# Knowledge Settings — Follow-up Fixes

**Status:** In implementation — first runtime/UI slice validated locally; offline skill evaluation remains a later sub-workstream
**Created:** 2026-07-11
**Baseline:** Knowledge settings and pipeline refactor delivered in commit `48b1dbf`
**Historical specification:** `archived/knowledge-settings-and-pipeline-refactor-implementation-plan.md`

## Locked decisions

### KF-001 — Remove the redundant global-card entity override

**Decision:** Remove **Entity-specific evidence threshold overrides** from the **Global generation controls** card.

The existing control is misleadingly positioned as global. It writes the legacy per-entity `knowledge_extraction_threshold` value, which affects the Declarative Knowledge pathway rather than every Knowledge generation pathway.

The supported configuration hierarchy is:

```text
entity-specific pathway override
    → pathway override
    → global generation default
```

Required behavior for the follow-up implementation:

1. Keep **Global generation controls** limited to defaults shared by all pathways.
2. Place entity-specific settings only inside the applicable **Knowledge Generation Pathway** accordion.
3. Expose the entity-specific evidence-threshold override inside **Declarative Knowledge**.
4. Show only settings that the selected pathway actually consumes.
5. Do not expose a second entity override for the same effective setting elsewhere in the page.
6. Preserve backward compatibility by migrating or resolving an existing `knowledge_extraction_threshold` as the Declarative Knowledge entity-level `evidence_threshold` override.
7. Do not discard or silently reset existing production values during migration.
8. After migration, use the canonical pathway override as the authoritative value; retain legacy reads only for the defined compatibility window.
9. Display inheritance clearly: **Use global**, **Use pathway default**, or an explicit entity value, as applicable.

Acceptance criteria:

- The Global card contains no entity-specific controls.
- Declarative Knowledge contains the entity evidence-threshold override.
- Other pathway accordions do not show an evidence-threshold override unless that pathway consumes it.
- Existing entity thresholds continue to produce the same effective Declarative Knowledge threshold after deployment.
- API and database migration tests cover legacy value preservation, canonical precedence, and idempotent reruns.
- The UI has only one location for editing any given entity/pathway setting.

### KF-002 — Add contextual help to every Knowledge configuration field

**Decision:** Every configurable field in the three Knowledge settings subtabs must have a small circular **?** help control beside its label. Activating it opens a concise tooltip or popover explaining what the setting controls and how to interpret its value.

Scope:

- **Knowledge Generation** global controls;
- generation pathway overrides;
- entity-specific pathway overrides;
- prompt, provider, model, and execution controls inside pathway accordions;
- **Knowledge Maintenance** hygiene, consolidation, evidence-routing, and maintenance settings;
- category-specific consolidation policies;
- **Knowledge Retrieval** context retrieval and governed-facet settings;
- future fields added to any of these three subtabs.

Required interaction behavior:

1. Use one reusable Knowledge setting-help component rather than implementing field-specific tooltip markup repeatedly.
2. Render a recognizable circular **?** control immediately beside the field label.
3. Open on mouse hover and keyboard focus where hover is available.
4. Open on click/tap so help remains usable on touch devices.
5. Keep the help open long enough to read; clicking elsewhere, pressing `Escape`, or activating the control again closes it.
6. The control must be keyboard reachable and expose an accessible name such as `Help: Candidate similarity`.
7. Tooltip content must be readable by assistive technology and associate with the field through accessible description semantics where practical.
8. Do not rely on the browser `title` attribute as the only implementation.
9. Position responsively and prevent the popover from being clipped by cards, accordions, tabs, or the viewport.
10. Use the same icon size, spacing, typography, and maximum content width throughout the page.

Each help description must explain, in plain language:

- what the setting controls;
- when it takes effect;
- what higher/lower values or each available choice mean;
- whether it discovers candidates, invokes an LLM, changes records, affects retrieval, or only changes display/analysis;
- its unit and valid range where applicable;
- its default value;
- its inheritance behavior when the field is an override;
- important safety implications, especially for automatic consolidation and activation.

Content rules:

- Do not expose internal variable names as the primary explanation.
- Distinguish similarly named concepts, including generation confidence, consolidation confidence, candidate similarity, evidence-routing similarity, cohesion, and relevance floor.
- State explicitly that embedding similarity discovers candidates and does not independently authorize consolidation.
- Explain **Approved** versus **Draft** using the user-facing terms while noting the retrieval consequence.
- Explain that always-on Knowledge is injected in full and ordinary matches are injected as index entries.
- For JSON editors such as Facet schema and Profile-to-facet map, include a short valid example or a link/button that reveals one without replacing the current value.
- Keep the first paragraph concise; longer warnings or examples may appear in a secondary section inside the popover.

Implementation direction:

- Create a reusable component equivalent to `SettingHelp({ label, description, details, example })` using the repository's existing accessible tooltip/popover primitives.
- Maintain tooltip copy in a centralized Knowledge settings help registry keyed by stable semantic field identifiers.
- In development and tests, warn or fail when a rendered Knowledge setting lacks a registered help entry.
- Keep explanatory helper text below fields only when it provides essential always-visible guidance; remove duplicated helper text when the tooltip fully replaces it.

Acceptance criteria:

- Every editable Knowledge setting visible in the supplied Generation, Maintenance, and Retrieval screens has a **?** help control.
- Pathway and entity override help explains the effective precedence: entity → pathway → global.
- All controls work with mouse, keyboard, and touch interaction.
- Automated component tests cover open, close, focus, `Escape`, accessible naming, and representative content.
- A coverage test enumerates Knowledge setting labels/registry keys and fails when a field is missing help content.
- Tooltips remain visible within narrow/mobile viewports and inside expanded pathway accordions.
- No tooltip description contradicts the implemented runtime behavior or the locked decisions in this document.

### KF-003 — Keep facets broad; represent intake as one human-readable value

**Decision:** Governed facets remain broad retrieval and grouping dimensions. Do not turn deadlines, validity periods, or other detailed facts into facets by default.

For intake-specific knowledge, use one human-readable facet containing the period and year when both are explicitly supported:

```json
{
  "intake": "September 2026"
}
```

Locked boundaries:

1. `intake` may contain a month or named academic term plus its year, such as `September 2026`, `January 2027`, or `Fall 2026`.
2. Do not split intake into separate period and year facets in the initial implementation.
3. Exact application deadlines belong in the Knowledge record content, including their qualifications and context.
4. `valid_from` and `valid_until` also remain Knowledge content unless a separate machine-readable validity or expiry feature is explicitly approved.
5. Do not seed `deadline_date`, `valid_from`, or `valid_until` as governed facets.
6. The generation LLM may emit the `intake` facet only when the source evidence explicitly supports the complete value; it must not infer a year.
7. Institution-specific dates, exceptions, application conditions, and supporting evidence remain in canonical content rather than being reduced to facet values.

Acceptance criteria:

- The seeded facet schema contains `intake` with examples that include a year.
- The seeded facet schema does not contain deadline or validity-date keys.
- Generated records can be retrieved using a complete intake value such as `September 2026`.
- Generation validation rejects unsupported facet keys and preserves deadline/validity details in content.
- Help text explains that facets support broad filtering and do not replace the full Knowledge record.

### KF-004 — Upgrade pathway prompts and Agent Skills interoperability

**Decision:** Replace the current shallow Knowledge Generation Pathway prompts with versioned, category-aware structured contracts. Strengthen skill and playbook generation using the Agent Skills specification and the design principles of Anthropic's `skill-creator`, without invoking its interactive evaluation workflow in the automatic generation hot path.

Authoritative external references:

- Agent Skills specification: `https://agentskills.io/specification`
- Anthropic skill-creator: `https://github.com/anthropics/skills/tree/main/skills/skill-creator`

#### Product boundaries

1. `best_practices`, `lessons_learned`, and `trade_knowledge` remain normal Knowledge records. They are not stored internally as SKILL.md.
2. `skill` and `playbook` use the Agent Skills SKILL.md representation. A playbook is represented as a procedural skill because the Agent Skills specification has no separate playbook document type.
3. Automatic generation produces structured JSON first. Deterministic code validates it and renders SKILL.md; the LLM does not generate authoritative frontmatter directly.
4. The full interactive Anthropic skill-creator loop—interview, user confirmation, baseline runs, evaluation viewer, and iterative feedback—is not executed for every automatic generation event.
5. Skill-creator principles are adopted in prompt design and in a separate offline/review workflow for important Approved skills and playbooks.
6. Do not describe current interoperability as fully standard-compliant until package layout, frontmatter, and official validation requirements pass.

#### Future agent-harness architecture

MasterAgent is evolving into a complete agent harness. Skills and playbooks are therefore native executable assets, not merely documents exported for compatibility.

Preserve two distinct layers:

1. **Portable Agent Skill package**
   - standards-compatible `SKILL.md`;
   - optional `scripts/`, `references/`, and `assets/`;
   - portable description, instructions, compatibility, and declared tool needs.
2. **MasterAgent runtime contract**
   - typed inputs and outputs;
   - resolved tool/MCP bindings;
   - permissions and approval requirements;
   - applicable agents, environments, tenants, and entities;
   - side effects and risk classification;
   - execution policy, timeouts, retries, and idempotency;
   - failure, recovery, rollback, and compensation behavior;
   - safety constraints and data-handling policy;
   - activation policy and runtime state;
   - telemetry, outcome evidence, evaluation history, versioning, and audit.

Locked constraints:

- SKILL.md is the portable instruction package, not the complete internal execution model.
- A skill may declare that it needs a capability, but it cannot grant itself a tool, credential, permission, or MCP scope.
- Runtime capability resolution and authorization occur after skill selection and before execution.
- The harness must fail closed when a required capability, credential, permission, or safety approval is unavailable.
- Portable imports map into a Draft runtime contract and require validation/review before executable activation.
- Internal runtime-only governance fields must not be forced into non-standard SKILL.md frontmatter.
- Execution telemetry and outcomes feed evaluation and future Knowledge hygiene without silently rewriting or approving executable skills.

The intended future flow is:

```text
conversation + entity context + agent state
    → retrieve applicable knowledge
    → select skill/playbook candidates
    → resolve tools and MCP capabilities
    → enforce permissions, credentials, policy, and safety
    → plan and execute
    → capture results, side effects, telemetry, and outcomes
    → evaluate and improve through governed review
```

#### Shared prompt requirements

Every pathway prompt must:

- return only the declared structured response;
- include an explicit schema/version identifier;
- distinguish zero valid candidates from generation failure;
- use only source-supported information;
- preserve qualifications, exceptions, jurisdiction, scope, and contradictions;
- avoid converting separate incidents into one fabricated event;
- emit `confidence`, governed `facets`, and applicable `signals` in the primary call;
- omit unsupported facets rather than guessing;
- explain the intended category and reject incoherent category choices;
- identify information that is missing or unresolved rather than inventing it;
- remain compatible with configurable global/pathway token and confidence policies.

Use typed, category-discriminated Pydantic response models. Do not rely only on permissive dictionary parsing.

#### Declarative Knowledge contract

The Declarative Knowledge response must include:

- `decision`: `create` or `no_candidate`;
- `name`;
- `category`: `best_practices`, `lessons_learned`, or `trade_knowledge`;
- `summary`;
- `content`;
- `signals`;
- `tags`;
- `facets`;
- `confidence`;
- `qualifications`;
- `contradictions`;
- `source_support` or equivalent traceability to the supplied intelligence records.

Category behavior:

- `best_practices`: preserve recommendation, conditions, exceptions, and scope;
- `lessons_learned`: preserve causal context and keep separate incidents distinct;
- `trade_knowledge`: preserve jurisdiction, product, institution, intake, environment, and other contextual distinctions when explicitly supported.

#### Telemetry Reflection contract

Telemetry reflection must return a discriminated list whose candidate structure depends on category. Zero candidates remains valid.

- declarative candidates use the Declarative Knowledge preservation fields;
- skill candidates use the complete Skill contract below;
- playbook candidates use the complete Playbook contract below.

The prompt must distinguish:

- observed agent behavior;
- tool output or discovered facts;
- conversation outcome evidence;
- unsupported internal speculation.

Internal thoughts alone are not sufficient evidence for durable trade knowledge unless corroborated by an outcome, tool result, or other reliable source.

#### Skill contract

Generated skills must include:

- purpose;
- trigger description explaining both what the skill does and when to use it;
- expected inputs;
- expected outputs;
- tools and integrations;
- prerequisites;
- permissions;
- applicable environments and agents;
- side effects;
- imperative execution instructions;
- failure conditions;
- recovery behavior;
- safety requirements;
- examples and edge cases where the evidence supports them;
- confidence, facets, signals, and source traceability.

The trigger description is the primary discovery mechanism and must include realistic task/context keywords. Do not place essential trigger information only in the SKILL.md body.

#### Playbook contract

Generated playbooks must include:

- purpose and expected outcome;
- trigger conditions;
- prerequisites and required inputs;
- responsible roles;
- tools and integrations;
- ordered steps;
- branches and decision points;
- escalation rules;
- failure handling;
- rollback or recovery;
- safety constraints;
- completion and exit criteria;
- confidence, facets, signals, and source traceability.

Do not impose a universal 3–7 step limit. Require the minimum coherent number of steps and enforce the configured output/token boundary.

#### SKILL.md rendering and package compliance

Upgrade deterministic rendering and export as follows:

1. Continue enforcing the official `name` and `description` constraints.
2. Add `compatibility` only when environment requirements exist.
3. Add experimental `allowed-tools` only when tools are explicitly pre-approved; naming a tool in generated content must not grant permission.
4. Ensure custom frontmatter metadata uses string keys and string values as required by the Agent Skills specification. Encode structured arrays in the Knowledge database rather than non-standard frontmatter arrays.
5. Render operational sections from the validated contract, including inputs, outputs, prerequisites, procedure, failures, recovery, safety, and examples where present.
6. Export each skill/playbook as `<slug>/SKILL.md`, ensuring the frontmatter name matches its parent directory.
7. Preserve optional package support for `scripts/`, `references/`, and `assets/`; do not fabricate bundled resources during automatic generation.
8. Keep declarative Knowledge export separate and accurately label it as Knowledge Markdown rather than SKILL.md.
9. Strengthen imports beyond the current minimal parser and validate constraints before accepting a package.
10. Integrate the official `skills-ref validate` tool or an equivalently tested validation adapter. Reject invalid imports and generated packages before approval/export.

#### Prompt seeding and backward compatibility

Prompt improvements must reach existing installations without overwriting administrator customizations.

Implement:

- a stable prompt template identifier;
- a prompt template version per pathway;
- a stored seeded-template hash or equivalent provenance;
- an idempotent migration that upgrades only prompts still matching a known prior seed or left empty;
- preservation of customized prompts;
- an admin-visible notice when a custom prompt is based on an older contract;
- an explicit **Review new default** and **Adopt new default** action;
- schema compatibility validation when saving a custom prompt.

Do not silently replace a production-customized prompt.

#### Offline skill quality workflow

Add an optional review workflow inspired by Anthropic's skill-creator:

1. Generate realistic should-trigger and should-not-trigger queries.
2. Review trigger coverage and false positives.
3. Execute representative tasks with and without the skill where the environment supports evaluation.
4. Compare correctness, omissions, token use, and execution behavior.
5. Present human-reviewable results.
6. Revise the skill or trigger description and retain evaluation history.

This workflow is asynchronous and review-oriented. It must not block normal Knowledge generation or automatically approve a skill.

#### Implementation sequence

1. Add versioned structured response models and validators.
2. Replace the four canonical seeded prompts: Declarative Knowledge, Telemetry Reflection, Playbook Extraction, and Skill Decomposition.
3. Route every pathway through its typed validator before persistence.
4. Expand structured skill/playbook metadata and deterministic SKILL.md rendering.
5. Add package-layout export and official/equivalent validation.
6. Add versioned, customization-safe seed migration.
7. Add the optional offline skill evaluation workflow.
8. Update UI help copy and operator documentation.

#### Required tests

- declarative `no_candidate` response;
- missing `signals`, `confidence`, or facet contract rejection;
- category-specific preservation of conditions and exceptions;
- separate lessons are not rewritten as one incident;
- unsupported jurisdiction/intake values are not invented;
- telemetry speculation without corroboration is rejected as durable trade knowledge;
- complete Skill operational contract round-trip;
- complete Playbook procedural contract round-trip;
- skill description contains what-and-when trigger information;
- tools do not become permissions automatically;
- generated SKILL.md passes official/equivalent validation;
- frontmatter name matches exported parent directory;
- metadata values comply with the specification;
- import rejects invalid names, descriptions, frontmatter, and package layout;
- existing customized prompts survive migration unchanged;
- unchanged historical seed prompts upgrade exactly once;
- custom old-version prompts receive a visible compatibility warning;
- offline evaluation never blocks generation or grants approval;
- all existing Knowledge records and APIs remain backward compatible.

Acceptance criteria:

- All four generation pathways use versioned, typed response contracts.
- Skill and playbook prompts preserve the complete operational/procedural requirements.
- Seed upgrades safely reach default installations and preserve custom prompts.
- Generated skill packages validate against the Agent Skills requirements.
- Declarative exports are no longer described as standard SKILL.md.
- The application accurately states that it supports Agent Skills interoperability.
- Anthropic skill-creator principles are used for optional evaluation, not misrepresented as a runtime dependency.

## Open follow-up items

None recorded yet.
