# Memory System Models and Database Schema
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from pydantic import model_validator
from enum import Enum

# Timestamp type: accepts both str and datetime from psycopg2 TIMESTAMPTZ columns.
Timestamp = Optional[Any]

# ============================================
# LLM Integration Configuration Models
# ============================================

class LLMTaskType(str, Enum):
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"
    VISION = "vision"
    ENTITY_EXTRACTION = "entity_extraction"
    PII_SCRUBBING = "pii_scrubbing"
    Intelligence_GENERATION = "Intelligence_generation"

class LLMProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    CUSTOM = "custom"
    GLINER = "gliner"   # For entity extraction
    ZENDATA = "zendata"  # For PII scrubbing

class LLMProviderCreate(BaseModel):
    name: str
    provider: str
    api_base_url: Optional[str] = ""
    api_key: Optional[str] = ""
    rate_limit_rpm: Optional[int] = 60
    max_retries: Optional[int] = 3
    retry_delay_ms: Optional[int] = 1000

class LLMProviderResponse(BaseModel):
    id: str
    name: str
    provider: str
    api_base_url: Optional[str] = None
    api_key_preview: Optional[str] = None
    rate_limit_rpm: int
    max_retries: int
    retry_delay_ms: int
    created_at: Timestamp
    updated_at: Timestamp

class LLMProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    rate_limit_rpm: Optional[int] = None
    max_retries: Optional[int] = None
    retry_delay_ms: Optional[int] = None

class LLMConfigCreate(BaseModel):
    task_type: str
    pipeline_stage: Optional[str] = None
    execution_order: int = 0
    provider_id: Optional[str] = None
    model_name: Optional[str] = ""
    is_active: bool = True
    extra_config: Optional[Dict[str, Any]] = {}

class LLMConfigResponse(BaseModel):
    id: str
    task_type: str
    pipeline_stage: Optional[str] = None
    execution_order: int = 0
    provider_id: Optional[str] = None
    model_name: Optional[str] = None
    prompt_id: Optional[str] = None
    inline_system_prompt: Optional[str] = None
    inline_schema: Optional[str] = None
    is_active: bool = True
    extra_config: Dict[str, Any] = {}
    created_at: Timestamp
    updated_at: Timestamp

class LLMConfigUpdate(BaseModel):
    pipeline_stage: Optional[str] = None
    execution_order: Optional[int] = None
    provider_id: Optional[str] = None
    model_name: Optional[str] = None
    prompt_id: Optional[str] = None
    inline_system_prompt: Optional[str] = None
    inline_schema: Optional[str] = None
    is_active: Optional[bool] = None
    extra_config: Optional[Dict[str, Any]] = None

class PipelineReorderRequest(BaseModel):
    pipeline_stage: str
    ordered_ids: List[str]

class FetchModelsRequest(BaseModel):
    provider: str
    api_key: Optional[str] = ""
    api_base_url: Optional[str] = ""
    provider_id: Optional[str] = None  # If set, backend looks up stored key as fallback

class FetchModelsResponse(BaseModel):
    models: List[str]
    provider: str

# ============================================
# Pydantic Models for API
# ============================================

# Config Models
class EntityTypeCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "folder"

class EntityTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    created_at: Timestamp

class EntitySubtypeCreate(BaseModel):
    entity_type_id: str
    name: str
    description: Optional[str] = ""

class EntitySubtypeResponse(BaseModel):
    id: str
    entity_type_id: str
    name: str
    description: Optional[str] = None
    created_at: Timestamp

class KnowledgeTypeCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#22C55E"

class KnowledgeTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    created_at: Timestamp

class ChannelTypeCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "message-circle"

class ChannelTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    created_at: Timestamp

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    access_level: str = "private"  # private, shared, or custom per settings

class AgentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    api_key_preview: str
    access_level: str
    is_active: bool
    created_at: Timestamp
    last_used: Timestamp

class AgentCreateResponse(AgentResponse):
    api_key: str  # Full key only on creation

class SystemPromptCreate(BaseModel):
    prompt_type: str  # summarization, knowledge_generation, intelligence_generation, entity_extraction, pii_scrubbing
    name: str
    prompt_text: str
    is_active: bool = True

class SystemPromptResponse(BaseModel):
    id: str
    prompt_type: str
    name: str
    prompt_text: str
    is_active: bool
    created_at: Timestamp
    updated_at: Timestamp

class MemorySettingsUpdate(BaseModel):
    # Chunking settings
    chunk_size: Optional[int] = 400         # tokens
    chunk_overlap: Optional[int] = 80       # tokens
    # Memory generation schedule
    memory_generation_time: Optional[str] = "02:00"       # HH:MM UTC
    memory_generation_mode: Optional[str] = "ner_and_raw" # 'ner_only' | 'ner_and_raw'
    # Knowledge settings
    auto_knowledge_enabled: Optional[bool] = True
    auto_knowledge_threshold: Optional[int] = 5
    knowledge_threshold: Optional[int] = 5             # N confirmed Intelligences → Knowledge
    intelligence_extraction_threshold: Optional[int] = 10
    # Rate limits
    rate_limit_enabled: Optional[bool] = False
    rate_limit_per_minute: Optional[int] = 60
    # Agent access
    default_agent_access: Optional[str] = "private"

class MemorySettingsResponse(BaseModel):
    chunk_size: int
    chunk_overlap: int
    memory_generation_time: str = "02:00"
    memory_generation_mode: str = "ner_and_raw"
    auto_knowledge_enabled: bool
    auto_knowledge_threshold: int
    knowledge_threshold: int = 5
    intelligence_extraction_threshold: int = 10
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    default_agent_access: str

# ============================================
# Tier 0: Interaction Models
# ============================================

class RelatedEntity(BaseModel):
    entity_type: str
    entity_id: str
    name: Optional[str] = ""
    role: Optional[str] = ""  # primary, mentioned, cc, participant, etc.

class InteractionCreate(BaseModel):
    interaction_type: str = Field(..., description="An identifier for the event (e.g., email_sent, whatsapp_received, crm_note, ai_conversation, webhook_event)")
    content: Union[str, Dict[str, Any], List[Any]] = Field(..., description="The raw content of the interaction. Can be a string or a JSON object/array which will be auto-stringified.")
    primary_entity_type: str = Field(..., description="The category over which this memory is stored (e.g., contact, institution, program, supplier, product)")
    primary_entity_id: str = Field(..., description="The unique ID of the entity from your source system")
    primary_entity_subtype: Optional[str] = Field(None, description="Optional sub-categorization for the entity")
    agent_name: Optional[str] = Field(None, description="An optional override for the name of the agent/source logging this")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Arbitrary JSON dictionary for passing a continuous snapshot or contextual metadata")
    metadata_field_map: Optional[Dict[str, str]] = Field(default_factory=dict, description="Used for mapping specific fields inside metadata")
    has_attachments: bool = Field(False, description="Flag indicating if attachments exist")
    attachment_refs: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="List of attachment objects. Supports type=base64 or type=url.")
    processing_errors: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Dictionary tracking pipeline execution failures (vision, embedding, etc)")
    source: str = Field("api", description="Source of ingestion (api, webhook, pull, ui)")

    @model_validator(mode='before')
    @classmethod
    def serialize_content_blob(cls, data: Any) -> Any:
        if isinstance(data, dict) and "content" in data:
            if not isinstance(data["content"], str):
                data["content"] = json.dumps(data["content"], indent=2, ensure_ascii=False)
        return data

class InteractionResponse(BaseModel):
    id: str
    seq_id: Optional[int] = None
    timestamp: str
    interaction_type: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    primary_entity_type: str
    primary_entity_id: str
    primary_entity_subtype: Optional[str]
    has_attachments: bool
    source: str
    status: str
    processing_errors: Optional[Dict[str, Any]] = None
    created_at: str

class InteractionUpdate(BaseModel):
    interaction_type: Optional[str] = None
    primary_entity_type: Optional[str] = None
    primary_entity_id: Optional[str] = None
    primary_entity_subtype: Optional[str] = None
    content: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None

# ============================================
# Tier 1: Memory Models
# ============================================

class MemoryCreate(BaseModel):
    date: str
    primary_entity_type: str
    primary_entity_id: str
    interaction_count: int = 1
    content_summary: str
    related_entities: Optional[List[RelatedEntity]] = []
    intents: Optional[List[str]] = []
    interaction_ids: Optional[List[str]] = []

class MemoryUpdate(BaseModel):
    content_summary: Optional[str] = None
    related_entities: Optional[List[RelatedEntity]] = None
    intents: Optional[List[str]] = None
    compacted: Optional[bool] = None

class MemoryResponse(BaseModel):
    id: str
    seq_id: Optional[int] = None
    date: str
    primary_entity_type: str
    primary_entity_id: str
    interaction_count: int
    content_summary: Optional[str]
    related_entities: List[RelatedEntity]
    intents: List[str]
    compacted: bool
    created_at: str

# ============================================
# Tier 2: Intelligence Models
# ============================================

class IntelligenceCreate(BaseModel):
    primary_entity_type: str
    primary_entity_id: str
    Intelligence_type: Optional[str] = None  # behavior_pattern, risk_signal, opportunity,
                                        # relationship_shift, preference, milestone
    name: str
    content: str                         # Markdown
    summary: Optional[str] = None
    source_memory_ids: Optional[List[str]] = []

class IntelligenceResponse(BaseModel):
    id: str
    seq_id: Optional[int] = None
    primary_entity_type: str
    primary_entity_id: str
    source_memory_ids: List[str]
    Intelligence_type: Optional[str]
    name: str
    content: str
    summary: Optional[str]
    status: str                          # draft | confirmed | archived
    created_by: str
    confirmed_by: Optional[str]
    confirmed_at: Optional[str]
    created_at: str
    updated_at: str

class IntelligenceUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    Intelligence_type: Optional[str] = None
    status: Optional[str] = None

# ============================================
# Tier 3: Knowledge Models
# ============================================

class KnowledgeCreate(BaseModel):
    knowledge_type: Optional[str] = None
    name: str
    content: str                         # PII-stripped Markdown
    summary: Optional[str] = None
    source_Intelligence_ids: Optional[List[str]] = []
    visibility: str = "shared"           # shared | team | private
    tags: Optional[List[str]] = []

class KnowledgeResponse(BaseModel):
    id: str
    seq_id: Optional[int] = None
    source_Intelligence_ids: List[str]
    knowledge_type: Optional[str]
    name: str
    content: str
    summary: Optional[str]
    visibility: str
    tags: List[str]
    created_at: str
    updated_at: str

class KnowledgeUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    knowledge_type: Optional[str] = None
    visibility: Optional[str] = None
    tags: Optional[List[str]] = None

# ============================================
# Per Entity Type Configuration
# ============================================

class EntityTypeConfig(BaseModel):
    entity_type: str
    intelligence_extraction_threshold: int = 10
    knowledge_extraction_threshold: Optional[int] = None
    Intelligence_auto_approve: bool = False
    knowledge_auto_promote: bool = False
    ner_enabled: bool = True
    ner_confidence_threshold: float = 0.5
    ner_schema: Optional[Dict[str, Any]] = None
    embedding_enabled: bool = True
    pii_scrub_knowledge: bool = True
    metadata_field_map: Dict[str, Any] = {}
    intelligence_signals_prompt: Optional[List[Dict[str, str]]] = None
    knowledge_signals_prompt: Optional[List[Dict[str, str]]] = None
    discovered_schema: Optional[List[str]] = None

class EntityTypeConfigUpdate(BaseModel):
    intelligence_extraction_threshold: Optional[int] = None
    knowledge_extraction_threshold: Optional[int] = None
    Intelligence_auto_approve: Optional[bool] = None
    knowledge_auto_promote: Optional[bool] = None
    ner_enabled: Optional[bool] = None
    ner_confidence_threshold: Optional[float] = None
    ner_schema: Optional[Dict[str, Any]] = None
    embedding_enabled: Optional[bool] = None
    pii_scrub_knowledge: Optional[bool] = None
    metadata_field_map: Optional[Dict[str, Any]] = None
    intelligence_signals_prompt: Optional[List[Dict[str, str]]] = None
    knowledge_signals_prompt: Optional[List[Dict[str, str]]] = None
    discovered_schema: Optional[List[str]] = None

# ============================================
# Search Models
# ============================================

class SearchRequest(BaseModel):
    query: str
    layers: List[str] = Field(default_factory=lambda: ["interactions", "memories", "Intelligences", "knowledge"])
    entity_type: Optional[str] = None
    entity_subtype: Optional[str] = None
    entity_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 20
    offset: int = 0

class SearchResult(BaseModel):
    id: str
    layer: str                      # memory | Intelligence | Knowledge
    score: float
    name: Optional[str]
    snippet: str
    entity_id: Optional[str]
    entity_type: Optional[str]
    created_at: str

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str

# ============================================
# Timeline Models
# ============================================

class TimelineRequest(BaseModel):
    entity_type: str
    entity_id: str
    since: Optional[str] = None
    until: Optional[str] = None
    interaction_type: Optional[str] = None
    limit: int = 50
    offset: int = 0

class TimelineEntry(BaseModel):
    id: str
    seq_id: Optional[int] = None
    timestamp: str
    interaction_type: str
    content_preview: str
    source: str
    status: str

class ContextStatusResponse(BaseModel):
    has_context: bool
    interactions_count: int
    last_interaction_date: Optional[str] = None
    interactions_ids: List[str] = []
    memories_count: int
    last_memory_date: Optional[str] = None
    memories_ids: List[str] = []
    Intelligences_count: int
    last_Intelligence_date: Optional[str] = None
    Intelligences_ids: List[str] = []

# ============================================
# Outbound Webhook Models
# ============================================

class OutboundWebhookCreate(BaseModel):
    name: str
    url: str
    debounce_ms: Optional[int] = 60000
    conditions: Optional[Dict[str, Any]] = {}
    payload_mode: Optional[str] = "trigger_only" # "trigger_only" or "all_window"
    include_latest_memory: Optional[bool] = True
    is_active: Optional[bool] = True

class OutboundWebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    debounce_ms: Optional[int] = None
    conditions: Optional[Dict[str, Any]] = None
    payload_mode: Optional[str] = None
    include_latest_memory: Optional[bool] = None
    is_active: Optional[bool] = None

class OutboundWebhookResponse(BaseModel):
    id: str
    name: str
    url: str
    debounce_ms: int
    conditions: Dict[str, Any]
    payload_mode: str
    include_latest_memory: bool
    is_active: bool
    created_at: str
    updated_at: str



