# Memory System Models and Database Schema
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

# ============================================
# LLM Integration Configuration Models
# ============================================

class LLMTaskType(str, Enum):
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"
    VISION = "vision"
    ENTITY_EXTRACTION = "entity_extraction"
    PII_SCRUBBING = "pii_scrubbing"

class LLMProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CUSTOM = "custom"
    GLINER = "gliner"  # For entity extraction
    ZENDATA = "zendata"  # For PII scrubbing

class LLMConfigCreate(BaseModel):
    task_type: str  # summarization, embedding, vision, entity_extraction, pii_scrubbing
    provider: str  # openai, anthropic, gemini, custom, gliner, zendata
    name: str
    api_base_url: Optional[str] = ""
    api_key: Optional[str] = ""
    model_name: Optional[str] = ""
    is_active: bool = True
    extra_config: Optional[Dict[str, Any]] = {}

class LLMConfigResponse(BaseModel):
    id: str
    task_type: str
    provider: str
    name: str
    api_base_url: Optional[str]
    api_key_preview: Optional[str]  # Only show preview, not full key
    model_name: Optional[str]
    is_active: bool
    extra_config: Dict[str, Any]
    created_at: str
    updated_at: str

class LLMConfigUpdate(BaseModel):
    name: Optional[str] = None
    api_base_url: Optional[str] = None
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    is_active: Optional[bool] = None
    extra_config: Optional[Dict[str, Any]] = None

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
    description: Optional[str]
    icon: Optional[str]
    created_at: str

class EntitySubtypeCreate(BaseModel):
    entity_type_id: str
    name: str
    description: Optional[str] = ""

class EntitySubtypeResponse(BaseModel):
    id: str
    entity_type_id: str
    name: str
    description: Optional[str]
    created_at: str

class LessonTypeCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    color: Optional[str] = "#22C55E"

class LessonTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    color: Optional[str]
    created_at: str

class ChannelTypeCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "message-circle"

class ChannelTypeResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    created_at: str

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    access_level: str = "private"  # private, shared, or custom per settings

class AgentResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    api_key_preview: str
    access_level: str
    is_active: bool
    created_at: str
    last_used: Optional[str]

class AgentCreateResponse(AgentResponse):
    api_key: str  # Full key only on creation

class SystemPromptCreate(BaseModel):
    prompt_type: str  # summarization, lesson_extraction, entity_extraction, pii_detection
    name: str
    prompt_text: str
    is_active: bool = True

class SystemPromptResponse(BaseModel):
    id: str
    prompt_type: str
    name: str
    prompt_text: str
    is_active: bool
    created_at: str
    updated_at: str

class MemorySettingsUpdate(BaseModel):
    # Chunking settings
    chunk_size: Optional[int] = 400  # tokens
    chunk_overlap: Optional[int] = 80  # tokens
    # Lesson settings
    auto_lesson_enabled: Optional[bool] = True
    auto_lesson_threshold: Optional[int] = 5  # min interactions to trigger
    lesson_approval_required: Optional[bool] = True
    # PII settings
    pii_scrubbing_enabled: Optional[bool] = True
    auto_share_scrubbed: Optional[bool] = False
    # OpenClaw sync
    openclaw_sync_enabled: Optional[bool] = False
    openclaw_sync_path: Optional[str] = ""
    openclaw_sync_type: Optional[str] = "filesystem"  # filesystem, git
    openclaw_sync_frequency: Optional[int] = 5  # minutes
    # Rate limits
    rate_limit_enabled: Optional[bool] = False
    rate_limit_per_minute: Optional[int] = 60
    # Agent access
    default_agent_access: Optional[str] = "private"

class MemorySettingsResponse(BaseModel):
    chunk_size: int
    chunk_overlap: int
    auto_lesson_enabled: bool
    auto_lesson_threshold: int
    lesson_approval_required: bool
    pii_scrubbing_enabled: bool
    auto_share_scrubbed: bool
    openclaw_sync_enabled: bool
    openclaw_sync_path: str
    openclaw_sync_type: str
    openclaw_sync_frequency: int
    rate_limit_enabled: bool
    rate_limit_per_minute: int
    default_agent_access: str

# Interaction/Memory Models
class RelatedEntity(BaseModel):
    entity_type: str
    entity_id: str
    role: Optional[str] = ""  # e.g., "primary", "mentioned", "cc"

class InteractionCreate(BaseModel):
    text: str
    channel: str  # must match a channel_type
    entities: List[RelatedEntity] = []
    metadata: Optional[Dict[str, Any]] = {}
    # Files are handled separately via multipart upload

class InteractionResponse(BaseModel):
    id: str
    timestamp: str
    channel: str
    summary_text: Optional[str]
    has_documents: bool
    entities: List[RelatedEntity]
    metadata: Dict[str, Any]

class MemoryDetailResponse(BaseModel):
    id: str
    timestamp: str
    channel: str
    raw_text: str
    summary_text: Optional[str]
    pii_stripped_text: Optional[str]
    has_documents: bool
    is_shared: bool
    entities: List[RelatedEntity]
    metadata: Dict[str, Any]
    documents: List[Dict[str, Any]]

# Lesson Models
class LessonCreate(BaseModel):
    lesson_type: str
    name: str
    body: str  # Markdown
    related_entities: List[RelatedEntity] = []
    source_memory_ids: List[str] = []

class LessonResponse(BaseModel):
    id: str
    lesson_type: str
    name: str
    body: str
    summary: Optional[str]
    status: str  # draft, approved, archived
    is_shared: bool
    related_entities: List[RelatedEntity]
    source_memory_ids: List[str]
    created_at: str
    updated_at: str

class LessonUpdate(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    related_entities: Optional[List[RelatedEntity]] = None

# Search Models
class SearchRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = {}
    types: str = "both"  # interactions, lessons, both
    shared_only: bool = False
    limit: int = 20
    offset: int = 0

class SearchResult(BaseModel):
    id: str
    type: str  # interaction or lesson
    score: float
    snippet: str
    timestamp: str
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    results: List[SearchResult]
    total: int
    query: str

# Timeline Models
class TimelineRequest(BaseModel):
    entity_type: str
    entity_id: str
    since: Optional[str] = None
    until: Optional[str] = None
    channel: Optional[str] = None
    limit: int = 50
    offset: int = 0

class TimelineEntry(BaseModel):
    id: str
    timestamp: str
    type: str  # interaction or lesson
    channel: Optional[str]
    summary_text: str
    has_documents: bool
    is_shared: bool
