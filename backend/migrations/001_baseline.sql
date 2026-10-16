 -- TASK-257 §3 — migration 001: the frozen deployed schema.
 -- Verbatim pg_dump --schema-only of a freshly-initialized memory database
 -- (pgvector/pgvector:pg16, backend/memory_system/store/db.py init path), 2026-10-16.
 -- Applied only to EMPTY databases; existing deployments are stamped as applied.
 -- The memory_provider_batch_* tables and memory_settings.supabase_* columns are
 -- deliberately INCLUDED (deployed-schema verbatim) even though deprecated; 002 drops them.
--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13 (Debian 16.13-1.pgdg12+1)
-- Dumped by pg_dump version 16.13 (Debian 16.13-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: entity_profiles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.entity_profiles (
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    display_name text,
    subtype text,
    status text,
    properties jsonb DEFAULT '{}'::jsonb,
    first_seen_at timestamp with time zone DEFAULT now(),
    last_synced_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.entity_profiles OWNER TO postgres;

--
-- Name: intelligence; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.intelligence (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    seq_id bigint NOT NULL,
    primary_entity_type text NOT NULL,
    primary_entity_id text NOT NULL,
    source_memory_ids text[] DEFAULT '{}'::text[] NOT NULL,
    signals text[] DEFAULT '{}'::text[] NOT NULL,
    name text NOT NULL,
    content text NOT NULL,
    summary text,
    embedding public.vector,
    status text DEFAULT 'draft'::text,
    created_by text DEFAULT 'auto'::text,
    confirmed_by text,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    embedded_at timestamp with time zone
);


ALTER TABLE public.intelligence OWNER TO postgres;

--
-- Name: intelligence_seq_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.intelligence_seq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.intelligence_seq_id_seq OWNER TO postgres;

--
-- Name: intelligence_seq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.intelligence_seq_id_seq OWNED BY public.intelligence.seq_id;


--
-- Name: interaction_ingestion_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.interaction_ingestion_requests (
    agent_id text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    interaction_ids text[] NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.interaction_ingestion_requests OWNER TO postgres;

--
-- Name: interactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.interactions (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    seq_id bigint NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    interaction_type text NOT NULL,
    agent_id text,
    agent_name text,
    content text NOT NULL,
    primary_entity_type text NOT NULL,
    primary_entity_subtype text,
    primary_entity_id text NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    metadata_field_map jsonb DEFAULT '{}'::jsonb,
    has_attachments boolean DEFAULT false,
    attachment_refs jsonb DEFAULT '[]'::jsonb,
    embedding public.vector,
    processing_errors jsonb DEFAULT '{}'::jsonb,
    source text DEFAULT 'api'::text,
    status text DEFAULT 'pending'::text,
    created_at timestamp with time zone DEFAULT now(),
    is_enriched boolean DEFAULT false,
    outbound_webhooks_fired text[] DEFAULT '{}'::text[],
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    embedded_at timestamp with time zone
);


ALTER TABLE public.interactions OWNER TO postgres;

--
-- Name: interactions_seq_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.interactions_seq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.interactions_seq_id_seq OWNER TO postgres;

--
-- Name: interactions_seq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.interactions_seq_id_seq OWNED BY public.interactions.seq_id;


--
-- Name: knowledge; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    seq_id bigint NOT NULL,
    source_intelligence_ids text[] DEFAULT '{}'::text[] NOT NULL,
    signals text[] DEFAULT '{}'::text[] NOT NULL,
    name text NOT NULL,
    content text NOT NULL,
    summary text,
    embedding public.vector,
    visibility text DEFAULT 'shared'::text,
    tags text[] DEFAULT '{}'::text[],
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    category text DEFAULT 'trade_knowledge'::text,
    metadata jsonb DEFAULT '{}'::jsonb,
    merge_count integer DEFAULT 0,
    last_merged_at timestamp with time zone,
    quality_score double precision,
    evidence_breadth integer DEFAULT 1,
    outcome_signal double precision DEFAULT 0.0,
    extraction_confidence double precision DEFAULT 0.5,
    source_pathway text DEFAULT 'experiential'::text,
    source_ai_interaction_ids text[] DEFAULT '{}'::text[],
    success_count integer DEFAULT 0,
    failure_count integer DEFAULT 0,
    feedback_notes jsonb DEFAULT '[]'::jsonb,
    version integer DEFAULT 1,
    parent_id text,
    status text DEFAULT 'confirmed'::text,
    merged_into text,
    merged_from text[] DEFAULT '{}'::text[] NOT NULL,
    consolidation_event_id text,
    consolidation_protected boolean DEFAULT false NOT NULL,
    approved_at timestamp with time zone,
    approved_by_type text,
    approved_by_id text,
    approval_origin text,
    quality_version integer,
    quality_components jsonb DEFAULT '{}'::jsonb,
    facet_schema_version integer,
    facet_status text,
    facet_provenance jsonb DEFAULT '{}'::jsonb,
    generation_state text DEFAULT 'ready'::text,
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    embedded_at timestamp with time zone
);


ALTER TABLE public.knowledge OWNER TO postgres;

--
-- Name: knowledge_attachments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_attachments (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    knowledge_id text,
    filename text NOT NULL,
    mime_type text NOT NULL,
    size_bytes integer NOT NULL,
    sha256 text NOT NULL,
    content bytea NOT NULL,
    extracted_text text DEFAULT ''::text,
    extraction jsonb DEFAULT '{}'::jsonb,
    status text DEFAULT 'queued'::text NOT NULL,
    created_by text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone DEFAULT (now() + '24:00:00'::interval)
);


ALTER TABLE public.knowledge_attachments OWNER TO postgres;

--
-- Name: knowledge_consolidation_event_sources; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_consolidation_event_sources (
    event_id text NOT NULL,
    knowledge_id text NOT NULL,
    role text,
    original_snapshot jsonb DEFAULT '{}'::jsonb,
    source_traceability jsonb DEFAULT '{}'::jsonb,
    merged_into text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_consolidation_event_sources OWNER TO postgres;

--
-- Name: knowledge_consolidation_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_consolidation_events (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    preview_id text,
    action text,
    origin text,
    actor_type text,
    actor_id text,
    category text,
    canonical_id text,
    canonical_strategy text,
    model_provider text,
    model_name text,
    prompt_version text,
    similarity_threshold double precision,
    settings_snapshot jsonb DEFAULT '{}'::jsonb,
    proposed_output jsonb DEFAULT '{}'::jsonb,
    approved_output jsonb DEFAULT '{}'::jsonb,
    user_edits jsonb DEFAULT '{}'::jsonb,
    warnings jsonb DEFAULT '[]'::jsonb,
    contradictions jsonb DEFAULT '[]'::jsonb,
    reversed_event_id text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_consolidation_events OWNER TO postgres;

--
-- Name: knowledge_consolidation_preview_sources; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_consolidation_preview_sources (
    preview_id text NOT NULL,
    knowledge_id text NOT NULL,
    source_version integer,
    source_updated_at timestamp with time zone,
    source_status text,
    source_snapshot jsonb DEFAULT '{}'::jsonb
);


ALTER TABLE public.knowledge_consolidation_preview_sources OWNER TO postgres;

--
-- Name: knowledge_consolidation_previews; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_consolidation_previews (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    origin text,
    actor_type text,
    actor_id text,
    category text,
    state text DEFAULT 'created'::text,
    source_ids text[] DEFAULT '{}'::text[],
    source_snapshot jsonb DEFAULT '{}'::jsonb,
    metrics jsonb DEFAULT '{}'::jsonb,
    options jsonb DEFAULT '{}'::jsonb,
    settings_snapshot jsonb DEFAULT '{}'::jsonb,
    model_provider text,
    model_name text,
    prompt_version text,
    raw_response jsonb,
    proposal jsonb,
    validation_errors jsonb DEFAULT '[]'::jsonb,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    applied_event_id text
);


ALTER TABLE public.knowledge_consolidation_previews OWNER TO postgres;

--
-- Name: knowledge_evidence_bundle_members; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_evidence_bundle_members (
    bundle_id text NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    source_role text DEFAULT 'primary'::text NOT NULL,
    ordinal integer,
    entity_type text,
    entity_id text,
    source_timestamp timestamp with time zone,
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_evidence_bundle_members OWNER TO postgres;

--
-- Name: knowledge_evidence_bundles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_evidence_bundles (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    pathway text NOT NULL,
    source_types text[] DEFAULT '{}'::text[] NOT NULL,
    source_digest text NOT NULL,
    entity_type text,
    entity_ids text[] DEFAULT '{}'::text[],
    window_started_at timestamp with time zone,
    window_ended_at timestamp with time zone,
    aggregate_embedding public.vector,
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    context_digest text,
    outcome_signature jsonb DEFAULT '{}'::jsonb,
    status text DEFAULT 'pending'::text NOT NULL,
    route text,
    route_metrics jsonb DEFAULT '{}'::jsonb,
    matched_bundle_ids text[] DEFAULT '{}'::text[],
    matched_knowledge_ids text[] DEFAULT '{}'::text[],
    canonical_knowledge_id text,
    generation_run_id text,
    error jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_evidence_bundles OWNER TO postgres;

--
-- Name: knowledge_evidence_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_evidence_events (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    bundle_id text,
    knowledge_id text,
    event_type text NOT NULL,
    actor_type text,
    actor_id text,
    origin text,
    similarity_settings jsonb DEFAULT '{}'::jsonb,
    route_metrics jsonb DEFAULT '{}'::jsonb,
    source_ids text[] DEFAULT '{}'::text[],
    previous_snapshot jsonb DEFAULT '{}'::jsonb,
    approved_output jsonb DEFAULT '{}'::jsonb,
    model_provider text,
    model_name text,
    prompt_version text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_evidence_events OWNER TO postgres;

--
-- Name: knowledge_hygiene_cluster_members; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_hygiene_cluster_members (
    cluster_id text NOT NULL,
    knowledge_id text NOT NULL,
    run_id text,
    similarity_to_centroid double precision,
    min_member_similarity double precision,
    role text,
    decision_reason text
);


ALTER TABLE public.knowledge_hygiene_cluster_members OWNER TO postgres;

--
-- Name: knowledge_hygiene_clusters; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_hygiene_clusters (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    run_id text,
    category text,
    member_ids text[] DEFAULT '{}'::text[],
    centroid public.vector,
    min_similarity double precision,
    avg_similarity double precision,
    max_similarity double precision,
    cohesion double precision,
    weak_links jsonb DEFAULT '[]'::jsonb,
    split_reason text,
    proposal_id text,
    status text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_hygiene_clusters OWNER TO postgres;

--
-- Name: knowledge_hygiene_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_hygiene_runs (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    origin text,
    mode text,
    status text,
    settings_snapshot jsonb DEFAULT '{}'::jsonb,
    embedding_version integer,
    categories text[] DEFAULT '{}'::text[],
    records_scanned integer DEFAULT 0,
    clusters_found integer DEFAULT 0,
    proposals_created integer DEFAULT 0,
    applied_count integer DEFAULT 0,
    failed_count integer DEFAULT 0,
    error text,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone,
    created_by text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_hygiene_runs OWNER TO postgres;

--
-- Name: knowledge_seq_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.knowledge_seq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.knowledge_seq_id_seq OWNER TO postgres;

--
-- Name: knowledge_seq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.knowledge_seq_id_seq OWNED BY public.knowledge.seq_id;


--
-- Name: knowledge_source_links; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.knowledge_source_links (
    knowledge_id text NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    bundle_id text,
    source_role text DEFAULT 'primary'::text NOT NULL,
    linked_by_event_id text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.knowledge_source_links OWNER TO postgres;

--
-- Name: memories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memories (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    seq_id bigint NOT NULL,
    date date NOT NULL,
    primary_entity_type text NOT NULL,
    primary_entity_id text NOT NULL,
    interaction_ids text[] DEFAULT '{}'::text[] NOT NULL,
    interaction_count integer DEFAULT 0 NOT NULL,
    content_summary text,
    related_entities jsonb DEFAULT '[]'::jsonb,
    intents text[] DEFAULT '{}'::text[],
    relationships jsonb DEFAULT '[]'::jsonb,
    embedding public.vector,
    compaction_count integer DEFAULT 0,
    compacted boolean DEFAULT false,
    processing_errors jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    compacted_at timestamp with time zone,
    embedding_model text,
    embedding_version integer,
    embedding_dimensions integer,
    embedded_at timestamp with time zone
);


ALTER TABLE public.memories OWNER TO postgres;

--
-- Name: memories_seq_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.memories_seq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.memories_seq_id_seq OWNER TO postgres;

--
-- Name: memories_seq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.memories_seq_id_seq OWNED BY public.memories.seq_id;


--
-- Name: memory_agent_entities; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_agent_entities (
    agent_id text NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_agent_entities OWNER TO postgres;

--
-- Name: memory_agents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_agents (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    description text,
    api_key_hash text NOT NULL,
    api_key_preview text,
    access_level text DEFAULT 'standard'::text,
    is_active boolean DEFAULT true,
    last_used timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_agents OWNER TO postgres;

--
-- Name: memory_audit_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_audit_log (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    agent_id text,
    action text NOT NULL,
    resource_type text,
    resource_id text,
    details jsonb DEFAULT '{}'::jsonb,
    "timestamp" timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_audit_log OWNER TO postgres;

--
-- Name: memory_channel_types; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_channel_types (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    description text,
    icon text,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_channel_types OWNER TO postgres;

--
-- Name: memory_entity_subtypes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_entity_subtypes (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    entity_type_id text NOT NULL,
    name text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    description text
);


ALTER TABLE public.memory_entity_subtypes OWNER TO postgres;

--
-- Name: memory_entity_type_config; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_entity_type_config (
    entity_type text NOT NULL,
    intelligence_extraction_threshold integer DEFAULT 10,
    intelligence_auto_approve boolean DEFAULT false,
    knowledge_auto_promote boolean DEFAULT false,
    ner_enabled boolean DEFAULT true,
    ner_confidence_threshold double precision DEFAULT 0.5,
    ner_schema jsonb,
    knowledge_extraction_threshold integer,
    embedding_enabled boolean DEFAULT true,
    pii_scrub_knowledge boolean DEFAULT true,
    metadata_field_map jsonb DEFAULT '{}'::jsonb,
    updated_at timestamp with time zone DEFAULT now(),
    intelligence_signals_prompt jsonb,
    knowledge_signals_prompt jsonb,
    discovered_schema jsonb,
    knowledge_generation_overrides jsonb DEFAULT '{}'::jsonb,
    extraction_min_entities integer DEFAULT 3,
    outcome_positive_threshold double precision DEFAULT 0.7,
    auto_activate_score_threshold double precision,
    decay_max_inactive_days integer DEFAULT 90,
    decay_min_interactions_since_trigger integer DEFAULT 100,
    playbook_auto_activate boolean DEFAULT false,
    skill_auto_activate boolean DEFAULT false
);


ALTER TABLE public.memory_entity_type_config OWNER TO postgres;

--
-- Name: memory_entity_types; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_entity_types (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    icon text,
    created_at timestamp with time zone DEFAULT now(),
    description text
);


ALTER TABLE public.memory_entity_types OWNER TO postgres;

--
-- Name: memory_job_controls; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_job_controls (
    job text NOT NULL,
    command text DEFAULT 'run'::text NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    updated_by text
);


ALTER TABLE public.memory_job_controls OWNER TO postgres;

--
-- Name: memory_job_locks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_job_locks (
    job_name text NOT NULL,
    locked_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


ALTER TABLE public.memory_job_locks OWNER TO postgres;

--
-- Name: memory_job_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_job_log (
    job_name text NOT NULL,
    last_run timestamp with time zone,
    last_date date,
    status text,
    last_error text,
    completed_at timestamp with time zone
);


ALTER TABLE public.memory_job_log OWNER TO postgres;

--
-- Name: memory_llm_configs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_llm_configs (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    task_type text NOT NULL,
    pipeline_stage text,
    execution_order integer DEFAULT 0,
    provider_id text,
    model_name text,
    prompt_id text,
    prompt_version text DEFAULT 'v1'::text,
    inline_system_prompt text,
    inline_schema text,
    extra_config_json text DEFAULT '{}'::text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_llm_configs OWNER TO postgres;

--
-- Name: memory_llm_providers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_llm_providers (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    provider text NOT NULL,
    api_base_url text,
    api_key_encrypted text,
    api_key_preview text DEFAULT ''::text,
    rate_limit_rpm integer DEFAULT 60,
    max_retries integer DEFAULT 3,
    retry_delay_ms integer DEFAULT 1000,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_llm_providers OWNER TO postgres;

--
-- Name: memory_operation_metrics; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_operation_metrics (
    operation_key text NOT NULL,
    eligible_count bigint,
    status text DEFAULT 'unavailable'::text NOT NULL,
    calculated_at timestamp with time zone,
    refresh_started_at timestamp with time zone,
    last_error text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_operation_metrics OWNER TO postgres;

--
-- Name: memory_operation_previews; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_operation_previews (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    operation_key text NOT NULL,
    execution_mode text NOT NULL,
    origin text DEFAULT 'admin'::text NOT NULL,
    actor_id text,
    options jsonb DEFAULT '{}'::jsonb NOT NULL,
    settings_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_snapshot jsonb DEFAULT '[]'::jsonb NOT NULL,
    request_manifest jsonb DEFAULT '[]'::jsonb NOT NULL,
    estimates jsonb DEFAULT '{}'::jsonb NOT NULL,
    exclusions jsonb DEFAULT '{}'::jsonb NOT NULL,
    warnings jsonb DEFAULT '[]'::jsonb NOT NULL,
    manifest_checksum text NOT NULL,
    state text DEFAULT 'previewed'::text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    submitted_at timestamp with time zone
);


ALTER TABLE public.memory_operation_previews OWNER TO postgres;

--
-- Name: memory_outbound_webhooks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_outbound_webhooks (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    url text NOT NULL,
    debounce_ms integer DEFAULT 60000,
    conditions jsonb DEFAULT '{}'::jsonb,
    payload_mode text DEFAULT 'trigger_only'::text,
    include_latest_memory boolean DEFAULT true,
    payload_interaction_types jsonb,
    payload_interaction_types_mode text DEFAULT 'include'::text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_outbound_webhooks OWNER TO postgres;

--
-- Name: memory_pipeline_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_pipeline_runs (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    seq_id bigint NOT NULL,
    job text NOT NULL,
    outcome text NOT NULL,
    reason_code text,
    records_created integer DEFAULT 0,
    detail jsonb DEFAULT '{}'::jsonb,
    trigger text DEFAULT 'scheduled'::text,
    created_at timestamp with time zone DEFAULT now(),
    status text DEFAULT 'queued'::text,
    progress_total integer DEFAULT 0,
    progress_completed integer DEFAULT 0,
    progress_failed integer DEFAULT 0,
    estimated_tokens bigint,
    estimated_cost_usd numeric(12,6),
    started_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone
);


ALTER TABLE public.memory_pipeline_runs OWNER TO postgres;

--
-- Name: memory_pipeline_runs_seq_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.memory_pipeline_runs_seq_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.memory_pipeline_runs_seq_id_seq OWNER TO postgres;

--
-- Name: memory_pipeline_runs_seq_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.memory_pipeline_runs_seq_id_seq OWNED BY public.memory_pipeline_runs.seq_id;


--
-- Name: memory_provider_batch_request_sources; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_provider_batch_request_sources (
    request_id text NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    source_version text,
    source_updated_at timestamp with time zone,
    source_role text DEFAULT 'primary'::text NOT NULL,
    source_metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public.memory_provider_batch_request_sources OWNER TO postgres;

--
-- Name: memory_provider_batch_requests; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_provider_batch_requests (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    batch_run_id text,
    custom_id text NOT NULL,
    operation_key text NOT NULL,
    pathway text,
    ordinal integer NOT NULL,
    request_hash text NOT NULL,
    source_hash text NOT NULL,
    request_body jsonb NOT NULL,
    apply_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    attempt integer DEFAULT 1 NOT NULL,
    provider_request_id text,
    response_body jsonb,
    usage jsonb DEFAULT '{}'::jsonb NOT NULL,
    error jsonb DEFAULT '{}'::jsonb NOT NULL,
    output_references jsonb DEFAULT '{}'::jsonb NOT NULL,
    validated_at timestamp with time zone,
    applied_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_provider_batch_requests OWNER TO postgres;

--
-- Name: memory_provider_batch_runs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_provider_batch_runs (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    pipeline_run_id text,
    preview_id text,
    parent_run_id text,
    operation_key text NOT NULL,
    pathway text,
    provider text NOT NULL,
    endpoint text NOT NULL,
    model text NOT NULL,
    completion_window text DEFAULT '24h'::text NOT NULL,
    local_status text DEFAULT 'preparing'::text NOT NULL,
    provider_status text,
    provider_batch_id text,
    provider_input_file_id text,
    provider_output_file_id text,
    provider_error_file_id text,
    request_count integer DEFAULT 0 NOT NULL,
    completed_count integer DEFAULT 0 NOT NULL,
    failed_count integer DEFAULT 0 NOT NULL,
    applied_count integer DEFAULT 0 NOT NULL,
    estimated_usage jsonb DEFAULT '{}'::jsonb NOT NULL,
    actual_usage jsonb DEFAULT '{}'::jsonb NOT NULL,
    manifest_checksum text NOT NULL,
    pause_requested boolean DEFAULT false NOT NULL,
    cancel_requested boolean DEFAULT false NOT NULL,
    provider_error jsonb DEFAULT '{}'::jsonb NOT NULL,
    last_polled_at timestamp with time zone,
    next_poll_at timestamp with time zone,
    submitted_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_coordinator boolean DEFAULT false NOT NULL,
    target_source_count bigint DEFAULT 0 NOT NULL,
    prepared_source_count bigint DEFAULT 0 NOT NULL,
    child_count integer DEFAULT 0 NOT NULL,
    preparation_complete boolean DEFAULT false NOT NULL,
    run_options jsonb DEFAULT '{}'::jsonb NOT NULL,
    pricing_snapshot jsonb DEFAULT '{}'::jsonb NOT NULL
);


ALTER TABLE public.memory_provider_batch_runs OWNER TO postgres;

--
-- Name: memory_settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_settings (
    id integer NOT NULL,
    chunk_size integer DEFAULT 400,
    chunk_overlap integer DEFAULT 80,
    auto_knowledge_enabled boolean DEFAULT true,
    auto_knowledge_threshold integer DEFAULT 5,
    rate_limit_enabled boolean DEFAULT true,
    rate_limit_per_minute integer DEFAULT 60,
    supabase_url text,
    supabase_db_url text,
    supabase_connected boolean DEFAULT false,
    memory_generation_time text DEFAULT '02:00'::text,
    memory_generation_mode text DEFAULT 'ner_and_raw'::text,
    knowledge_threshold integer DEFAULT 5,
    intelligence_extraction_threshold integer DEFAULT 10,
    updated_at timestamp with time zone DEFAULT now(),
    prior_context_chrono_count integer DEFAULT 2,
    prior_context_semantic_count integer DEFAULT 2,
    prior_intelligence_chrono_count integer DEFAULT 3,
    prior_intelligence_semantic_count integer DEFAULT 2,
    prior_knowledge_semantic_count integer DEFAULT 3,
    prior_knowledge_in_intelligence_count integer DEFAULT 2,
    memory_generation_max_tokens integer DEFAULT 1200,
    intelligence_max_tokens integer DEFAULT 1200,
    knowledge_max_tokens integer DEFAULT 1200,
    context_knowledge_count integer DEFAULT 30,
    context_knowledge_min_similarity double precision DEFAULT 0.0,
    knowledge_refine_on_merge boolean DEFAULT true,
    context_knowledge_mode text DEFAULT 'full'::text,
    facet_extraction_enabled boolean DEFAULT true,
    knowledge_facets_schema jsonb,
    profile_facet_map jsonb,
    intelligence_schedule_enabled boolean DEFAULT true,
    intelligence_generation_time text DEFAULT '02:30'::text,
    intelligence_schedule_floor integer DEFAULT 2,
    knowledge_schedule_enabled boolean DEFAULT true,
    knowledge_generation_time text DEFAULT '03:00'::text,
    knowledge_schedule_floor integer DEFAULT 2,
    playbook_schedule_enabled boolean DEFAULT true,
    playbook_generation_time text DEFAULT '03:30'::text,
    interaction_retention_days integer DEFAULT 30,
    interaction_retain_until_processed boolean DEFAULT true,
    telemetry_reflection_enabled boolean DEFAULT true,
    telemetry_reflection_time text DEFAULT '04:00'::text,
    telemetry_reflection_confidence_min double precision DEFAULT 0.6,
    telemetry_reflection_max_tokens integer DEFAULT 1200,
    knowledge_auto_activate boolean DEFAULT true,
    knowledge_creation_dedup_enabled boolean DEFAULT true,
    knowledge_creation_dedup_threshold double precision DEFAULT 0.90,
    knowledge_drafts_backfilled boolean DEFAULT false,
    knowledge_signals_lowercased boolean DEFAULT false,
    knowledge_hygiene_enabled boolean DEFAULT true,
    knowledge_hygiene_enabled_categories jsonb DEFAULT '["best_practices", "lessons_learned", "trade_knowledge", "skill", "playbook"]'::jsonb,
    knowledge_hygiene_similarity_threshold double precision DEFAULT 0.82,
    knowledge_hygiene_min_cluster_size integer DEFAULT 2,
    knowledge_hygiene_max_cluster_size integer DEFAULT 5,
    knowledge_hygiene_min_cluster_cohesion double precision DEFAULT 0.72,
    knowledge_hygiene_weak_link_threshold double precision DEFAULT 0.65,
    knowledge_hygiene_embedding_version integer DEFAULT 2,
    knowledge_hygiene_mode text DEFAULT 'manual_only'::text,
    knowledge_hygiene_preview_ttl_minutes integer DEFAULT 60,
    knowledge_hygiene_min_auto_confidence double precision DEFAULT 0.90,
    knowledge_hygiene_contradiction_policy text DEFAULT 'manual_review'::text,
    knowledge_hygiene_default_canonical_strategy text DEFAULT 'update_existing'::text,
    knowledge_hygiene_creation_time_enabled boolean DEFAULT false,
    knowledge_hygiene_category_policies jsonb DEFAULT '{"skill": "manual_only", "playbook": "manual_only", "best_practices": "manual_only", "lessons_learned": "manual_only", "trade_knowledge": "manual_only"}'::jsonb,
    knowledge_generation_enabled boolean DEFAULT true,
    knowledge_generation_max_tokens integer DEFAULT 1200,
    knowledge_generation_min_confidence double precision DEFAULT 0.60,
    knowledge_generation_evidence_threshold integer DEFAULT 5,
    knowledge_generation_approval_policy text DEFAULT 'approve_immediately'::text,
    knowledge_generation_pathway_overrides jsonb DEFAULT '{}'::jsonb,
    knowledge_evidence_routing_enabled boolean DEFAULT true,
    knowledge_evidence_routing_mode text DEFAULT 'analysis_only'::text,
    knowledge_evidence_low_threshold double precision DEFAULT 0.78,
    knowledge_evidence_high_threshold double precision DEFAULT 0.95,
    knowledge_evidence_high_coverage double precision DEFAULT 0.90,
    knowledge_quality_version integer DEFAULT 2,
    knowledge_facet_schema_version integer DEFAULT 1,
    knowledge_policy_migrated boolean DEFAULT false,
    memory_threshold integer DEFAULT 0,
    memory_safe_boundary_types jsonb DEFAULT '["outgoing_whatsapp_message"]'::jsonb,
    dedup_similarity_threshold double precision DEFAULT 0.85,
    extraction_confidence_threshold double precision DEFAULT 0.6,
    consolidation_similarity_threshold double precision DEFAULT 0.80,
    consolidation_run_interval_days integer DEFAULT 7,
    memory_generation_interaction_types jsonb DEFAULT '["internal_ai_thought", "internal_ai_tool_call"]'::jsonb,
    playbook_extraction_interval_days integer DEFAULT 7,
    playbook_extraction_evidence_threshold integer DEFAULT 20,
    CONSTRAINT memory_settings_id_check CHECK ((id = 1))
);


ALTER TABLE public.memory_settings OWNER TO postgres;

--
-- Name: memory_system_alerts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_system_alerts (
    code text NOT NULL,
    severity text NOT NULL,
    title text NOT NULL,
    message text NOT NULL,
    source text,
    detail jsonb DEFAULT '{}'::jsonb,
    active boolean DEFAULT true NOT NULL,
    expires_at timestamp with time zone,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.memory_system_alerts OWNER TO postgres;

--
-- Name: memory_system_prompts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_system_prompts (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    prompt_type text NOT NULL,
    name text NOT NULL,
    prompt_text text NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_system_prompts OWNER TO postgres;

--
-- Name: memory_webhook_sources; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memory_webhook_sources (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    source_system text NOT NULL,
    secret_hash text NOT NULL,
    secret_encrypted text,
    event_types text[] DEFAULT '{}'::text[],
    metadata_field_map jsonb DEFAULT '{}'::jsonb,
    default_interaction_type text DEFAULT 'webhook_event'::text,
    default_entity_type text DEFAULT 'contact'::text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.memory_webhook_sources OWNER TO postgres;

--
-- Name: playbook_processed_interactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.playbook_processed_interactions (
    interaction_id text NOT NULL,
    processed_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.playbook_processed_interactions OWNER TO postgres;

--
-- Name: telemetry_reflection_log; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.telemetry_reflection_log (
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    reflection_date date NOT NULL,
    candidates_created integer DEFAULT 0,
    outcome text DEFAULT 'knowledge_created'::text,
    reflected_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.telemetry_reflection_log OWNER TO postgres;

--
-- Name: vision_completion_webhooks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.vision_completion_webhooks (
    id text DEFAULT (gen_random_uuid())::text NOT NULL,
    name text NOT NULL,
    url text NOT NULL,
    is_active boolean DEFAULT true,
    doc_type_filter jsonb,
    source_filter jsonb,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.vision_completion_webhooks OWNER TO postgres;

--
-- Name: intelligence seq_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.intelligence ALTER COLUMN seq_id SET DEFAULT nextval('public.intelligence_seq_id_seq'::regclass);


--
-- Name: interactions seq_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interactions ALTER COLUMN seq_id SET DEFAULT nextval('public.interactions_seq_id_seq'::regclass);


--
-- Name: knowledge seq_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge ALTER COLUMN seq_id SET DEFAULT nextval('public.knowledge_seq_id_seq'::regclass);


--
-- Name: memories seq_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memories ALTER COLUMN seq_id SET DEFAULT nextval('public.memories_seq_id_seq'::regclass);


--
-- Name: memory_pipeline_runs seq_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_pipeline_runs ALTER COLUMN seq_id SET DEFAULT nextval('public.memory_pipeline_runs_seq_id_seq'::regclass);


--
-- Name: entity_profiles entity_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.entity_profiles
    ADD CONSTRAINT entity_profiles_pkey PRIMARY KEY (entity_type, entity_id);


--
-- Name: intelligence intelligence_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.intelligence
    ADD CONSTRAINT intelligence_pkey PRIMARY KEY (id);


--
-- Name: interaction_ingestion_requests interaction_ingestion_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interaction_ingestion_requests
    ADD CONSTRAINT interaction_ingestion_requests_pkey PRIMARY KEY (agent_id, idempotency_key);


--
-- Name: interactions interactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.interactions
    ADD CONSTRAINT interactions_pkey PRIMARY KEY (id);


--
-- Name: knowledge_attachments knowledge_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_attachments
    ADD CONSTRAINT knowledge_attachments_pkey PRIMARY KEY (id);


--
-- Name: knowledge_consolidation_event_sources knowledge_consolidation_event_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_event_sources
    ADD CONSTRAINT knowledge_consolidation_event_sources_pkey PRIMARY KEY (event_id, knowledge_id);


--
-- Name: knowledge_consolidation_events knowledge_consolidation_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_events
    ADD CONSTRAINT knowledge_consolidation_events_pkey PRIMARY KEY (id);


--
-- Name: knowledge_consolidation_preview_sources knowledge_consolidation_preview_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_preview_sources
    ADD CONSTRAINT knowledge_consolidation_preview_sources_pkey PRIMARY KEY (preview_id, knowledge_id);


--
-- Name: knowledge_consolidation_previews knowledge_consolidation_previews_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_previews
    ADD CONSTRAINT knowledge_consolidation_previews_pkey PRIMARY KEY (id);


--
-- Name: knowledge_evidence_bundle_members knowledge_evidence_bundle_members_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_evidence_bundle_members
    ADD CONSTRAINT knowledge_evidence_bundle_members_pkey PRIMARY KEY (bundle_id, source_type, source_id, source_role);


--
-- Name: knowledge_evidence_bundles knowledge_evidence_bundles_pathway_source_digest_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_evidence_bundles
    ADD CONSTRAINT knowledge_evidence_bundles_pathway_source_digest_key UNIQUE (pathway, source_digest);


--
-- Name: knowledge_evidence_bundles knowledge_evidence_bundles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_evidence_bundles
    ADD CONSTRAINT knowledge_evidence_bundles_pkey PRIMARY KEY (id);


--
-- Name: knowledge_evidence_events knowledge_evidence_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_evidence_events
    ADD CONSTRAINT knowledge_evidence_events_pkey PRIMARY KEY (id);


--
-- Name: knowledge_hygiene_cluster_members knowledge_hygiene_cluster_members_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_hygiene_cluster_members
    ADD CONSTRAINT knowledge_hygiene_cluster_members_pkey PRIMARY KEY (cluster_id, knowledge_id);


--
-- Name: knowledge_hygiene_clusters knowledge_hygiene_clusters_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_hygiene_clusters
    ADD CONSTRAINT knowledge_hygiene_clusters_pkey PRIMARY KEY (id);


--
-- Name: knowledge_hygiene_runs knowledge_hygiene_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_hygiene_runs
    ADD CONSTRAINT knowledge_hygiene_runs_pkey PRIMARY KEY (id);


--
-- Name: knowledge knowledge_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge
    ADD CONSTRAINT knowledge_pkey PRIMARY KEY (id);


--
-- Name: knowledge_source_links knowledge_source_links_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_source_links
    ADD CONSTRAINT knowledge_source_links_pkey PRIMARY KEY (knowledge_id, source_type, source_id, source_role);


--
-- Name: memories memories_date_primary_entity_type_primary_entity_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_date_primary_entity_type_primary_entity_id_key UNIQUE (date, primary_entity_type, primary_entity_id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (id);


--
-- Name: memory_agent_entities memory_agent_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_agent_entities
    ADD CONSTRAINT memory_agent_entities_pkey PRIMARY KEY (agent_id, entity_type, entity_id);


--
-- Name: memory_agents memory_agents_api_key_hash_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_agents
    ADD CONSTRAINT memory_agents_api_key_hash_key UNIQUE (api_key_hash);


--
-- Name: memory_agents memory_agents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_agents
    ADD CONSTRAINT memory_agents_pkey PRIMARY KEY (id);


--
-- Name: memory_audit_log memory_audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_audit_log
    ADD CONSTRAINT memory_audit_log_pkey PRIMARY KEY (id);


--
-- Name: memory_channel_types memory_channel_types_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_channel_types
    ADD CONSTRAINT memory_channel_types_name_key UNIQUE (name);


--
-- Name: memory_channel_types memory_channel_types_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_channel_types
    ADD CONSTRAINT memory_channel_types_pkey PRIMARY KEY (id);


--
-- Name: memory_entity_subtypes memory_entity_subtypes_entity_type_id_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_subtypes
    ADD CONSTRAINT memory_entity_subtypes_entity_type_id_name_key UNIQUE (entity_type_id, name);


--
-- Name: memory_entity_subtypes memory_entity_subtypes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_subtypes
    ADD CONSTRAINT memory_entity_subtypes_pkey PRIMARY KEY (id);


--
-- Name: memory_entity_type_config memory_entity_type_config_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_type_config
    ADD CONSTRAINT memory_entity_type_config_pkey PRIMARY KEY (entity_type);


--
-- Name: memory_entity_types memory_entity_types_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_types
    ADD CONSTRAINT memory_entity_types_name_key UNIQUE (name);


--
-- Name: memory_entity_types memory_entity_types_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_types
    ADD CONSTRAINT memory_entity_types_pkey PRIMARY KEY (id);


--
-- Name: memory_job_controls memory_job_controls_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_job_controls
    ADD CONSTRAINT memory_job_controls_pkey PRIMARY KEY (job);


--
-- Name: memory_job_locks memory_job_locks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_job_locks
    ADD CONSTRAINT memory_job_locks_pkey PRIMARY KEY (job_name);


--
-- Name: memory_job_log memory_job_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_job_log
    ADD CONSTRAINT memory_job_log_pkey PRIMARY KEY (job_name);


--
-- Name: memory_llm_configs memory_llm_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_llm_configs
    ADD CONSTRAINT memory_llm_configs_pkey PRIMARY KEY (id);


--
-- Name: memory_llm_providers memory_llm_providers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_llm_providers
    ADD CONSTRAINT memory_llm_providers_pkey PRIMARY KEY (id);


--
-- Name: memory_operation_metrics memory_operation_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_operation_metrics
    ADD CONSTRAINT memory_operation_metrics_pkey PRIMARY KEY (operation_key);


--
-- Name: memory_operation_previews memory_operation_previews_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_operation_previews
    ADD CONSTRAINT memory_operation_previews_pkey PRIMARY KEY (id);


--
-- Name: memory_outbound_webhooks memory_outbound_webhooks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_outbound_webhooks
    ADD CONSTRAINT memory_outbound_webhooks_pkey PRIMARY KEY (id);


--
-- Name: memory_pipeline_runs memory_pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_pipeline_runs
    ADD CONSTRAINT memory_pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: memory_provider_batch_request_sources memory_provider_batch_request_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_request_sources
    ADD CONSTRAINT memory_provider_batch_request_sources_pkey PRIMARY KEY (request_id, source_type, source_id, source_role);


--
-- Name: memory_provider_batch_requests memory_provider_batch_requests_batch_run_id_custom_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_requests
    ADD CONSTRAINT memory_provider_batch_requests_batch_run_id_custom_id_key UNIQUE (batch_run_id, custom_id);


--
-- Name: memory_provider_batch_requests memory_provider_batch_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_requests
    ADD CONSTRAINT memory_provider_batch_requests_pkey PRIMARY KEY (id);


--
-- Name: memory_provider_batch_runs memory_provider_batch_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_runs
    ADD CONSTRAINT memory_provider_batch_runs_pkey PRIMARY KEY (id);


--
-- Name: memory_settings memory_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_settings
    ADD CONSTRAINT memory_settings_pkey PRIMARY KEY (id);


--
-- Name: memory_system_alerts memory_system_alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_system_alerts
    ADD CONSTRAINT memory_system_alerts_pkey PRIMARY KEY (code);


--
-- Name: memory_system_prompts memory_system_prompts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_system_prompts
    ADD CONSTRAINT memory_system_prompts_pkey PRIMARY KEY (id);


--
-- Name: memory_webhook_sources memory_webhook_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_webhook_sources
    ADD CONSTRAINT memory_webhook_sources_pkey PRIMARY KEY (id);


--
-- Name: playbook_processed_interactions playbook_processed_interactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.playbook_processed_interactions
    ADD CONSTRAINT playbook_processed_interactions_pkey PRIMARY KEY (interaction_id);


--
-- Name: telemetry_reflection_log telemetry_reflection_log_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.telemetry_reflection_log
    ADD CONSTRAINT telemetry_reflection_log_pkey PRIMARY KEY (entity_type, entity_id, reflection_date);


--
-- Name: vision_completion_webhooks vision_completion_webhooks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.vision_completion_webhooks
    ADD CONSTRAINT vision_completion_webhooks_pkey PRIMARY KEY (id);


--
-- Name: idx_agent_entities_entity; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_agent_entities_entity ON public.memory_agent_entities USING btree (entity_type, entity_id);


--
-- Name: idx_audit_agent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_agent ON public.memory_audit_log USING btree (agent_id);


--
-- Name: idx_audit_timestamp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_timestamp ON public.memory_audit_log USING btree ("timestamp");


--
-- Name: idx_consolidation_event_sources_kid; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_event_sources_kid ON public.knowledge_consolidation_event_sources USING btree (knowledge_id);


--
-- Name: idx_consolidation_events_canonical; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_events_canonical ON public.knowledge_consolidation_events USING btree (canonical_id);


--
-- Name: idx_consolidation_events_preview; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_events_preview ON public.knowledge_consolidation_events USING btree (preview_id);


--
-- Name: idx_consolidation_preview_sources_kid; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_preview_sources_kid ON public.knowledge_consolidation_preview_sources USING btree (knowledge_id);


--
-- Name: idx_consolidation_previews_sources; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_previews_sources ON public.knowledge_consolidation_previews USING gin (source_ids);


--
-- Name: idx_consolidation_previews_state; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_consolidation_previews_state ON public.knowledge_consolidation_previews USING btree (state, expires_at);


--
-- Name: idx_entity_profiles_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entity_profiles_type ON public.entity_profiles USING btree (entity_type);


--
-- Name: idx_evidence_bundles_canonical; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evidence_bundles_canonical ON public.knowledge_evidence_bundles USING btree (canonical_knowledge_id);


--
-- Name: idx_evidence_bundles_route; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evidence_bundles_route ON public.knowledge_evidence_bundles USING btree (pathway, status, route);


--
-- Name: idx_evidence_events_bundle; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evidence_events_bundle ON public.knowledge_evidence_events USING btree (bundle_id, created_at DESC);


--
-- Name: idx_evidence_events_knowledge; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evidence_events_knowledge ON public.knowledge_evidence_events USING btree (knowledge_id, created_at DESC);


--
-- Name: idx_evidence_members_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_evidence_members_source ON public.knowledge_evidence_bundle_members USING btree (source_type, source_id);


--
-- Name: idx_hygiene_clusters_run; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hygiene_clusters_run ON public.knowledge_hygiene_clusters USING btree (run_id, category);


--
-- Name: idx_hygiene_members_kid; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hygiene_members_kid ON public.knowledge_hygiene_cluster_members USING btree (knowledge_id);


--
-- Name: idx_hygiene_runs_origin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hygiene_runs_origin ON public.knowledge_hygiene_runs USING btree (origin, created_at DESC);


--
-- Name: idx_hygiene_runs_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_hygiene_runs_status ON public.knowledge_hygiene_runs USING btree (status, started_at DESC);


--
-- Name: idx_intelligence_entity; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_intelligence_entity ON public.intelligence USING btree (primary_entity_type, primary_entity_id);


--
-- Name: idx_intelligence_entity_status_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_intelligence_entity_status_created ON public.intelligence USING btree (primary_entity_type, primary_entity_id, status, created_at DESC);


--
-- Name: idx_intelligence_fts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_intelligence_fts ON public.intelligence USING gin (to_tsvector('simple'::regconfig, ((((COALESCE(name, ''::text) || ' '::text) || COALESCE(summary, ''::text)) || ' '::text) || COALESCE(content, ''::text))));


--
-- Name: idx_intelligence_signals; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_intelligence_signals ON public.intelligence USING gin (signals);


--
-- Name: idx_intelligence_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_intelligence_status ON public.intelligence USING btree (status);


--
-- Name: idx_interaction_ingestion_requests_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interaction_ingestion_requests_created ON public.interaction_ingestion_requests USING btree (created_at);


--
-- Name: idx_interactions_agent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_agent ON public.interactions USING btree (agent_id);


--
-- Name: idx_interactions_entity; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_entity ON public.interactions USING btree (primary_entity_type, primary_entity_id);


--
-- Name: idx_interactions_entity_status_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_entity_status_time ON public.interactions USING btree (primary_entity_type, primary_entity_id, status, "timestamp" DESC);


--
-- Name: idx_interactions_fts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_fts ON public.interactions USING gin (to_tsvector('simple'::regconfig, COALESCE(content, ''::text)));


--
-- Name: idx_interactions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_status ON public.interactions USING btree (status);


--
-- Name: idx_interactions_timestamp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_interactions_timestamp ON public.interactions USING btree ("timestamp");


--
-- Name: idx_knowledge_attachments_knowledge; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_attachments_knowledge ON public.knowledge_attachments USING btree (knowledge_id);


--
-- Name: idx_knowledge_attachments_sha; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_attachments_sha ON public.knowledge_attachments USING btree (sha256);


--
-- Name: idx_knowledge_attachments_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_attachments_status ON public.knowledge_attachments USING btree (status, created_at);


--
-- Name: idx_knowledge_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_category ON public.knowledge USING btree (category);


--
-- Name: idx_knowledge_consolidation_event; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_consolidation_event ON public.knowledge USING btree (consolidation_event_id);


--
-- Name: idx_knowledge_fts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_fts ON public.knowledge USING gin (to_tsvector('simple'::regconfig, ((((COALESCE(name, ''::text) || ' '::text) || COALESCE(summary, ''::text)) || ' '::text) || COALESCE(content, ''::text))));


--
-- Name: idx_knowledge_merged_from; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_merged_from ON public.knowledge USING gin (merged_from);


--
-- Name: idx_knowledge_merged_into; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_merged_into ON public.knowledge USING btree (merged_into);


--
-- Name: idx_knowledge_metadata_gin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_metadata_gin ON public.knowledge USING gin (metadata jsonb_path_ops);


--
-- Name: idx_knowledge_signals; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_signals ON public.knowledge USING gin (signals);


--
-- Name: idx_knowledge_source_links_bundle; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_source_links_bundle ON public.knowledge_source_links USING btree (bundle_id);


--
-- Name: idx_knowledge_source_links_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_source_links_source ON public.knowledge_source_links USING btree (source_type, source_id);


--
-- Name: idx_knowledge_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_knowledge_status ON public.knowledge USING btree (status);


--
-- Name: idx_memories_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_date ON public.memories USING btree (date);


--
-- Name: idx_memories_entity; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_entity ON public.memories USING btree (primary_entity_type, primary_entity_id);


--
-- Name: idx_memories_fts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_fts ON public.memories USING gin (to_tsvector('simple'::regconfig, COALESCE(content_summary, ''::text)));


--
-- Name: idx_memories_uncompacted; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_uncompacted ON public.memories USING btree (primary_entity_id) WHERE (compacted = false);


--
-- Name: idx_operation_metrics_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operation_metrics_status ON public.memory_operation_metrics USING btree (status, updated_at);


--
-- Name: idx_operation_previews_state; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_operation_previews_state ON public.memory_operation_previews USING btree (state, expires_at);


--
-- Name: idx_outbound_webhooks_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_outbound_webhooks_active ON public.memory_outbound_webhooks USING btree (is_active);


--
-- Name: idx_pipeline_runs_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pipeline_runs_created ON public.memory_pipeline_runs USING btree (created_at DESC);


--
-- Name: idx_pipeline_runs_job; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_pipeline_runs_job ON public.memory_pipeline_runs USING btree (job, created_at DESC);


--
-- Name: idx_provider_batch_requests_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_provider_batch_requests_status ON public.memory_provider_batch_requests USING btree (batch_run_id, status);


--
-- Name: idx_provider_batch_runs_parent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_provider_batch_runs_parent ON public.memory_provider_batch_runs USING btree (parent_run_id, created_at);


--
-- Name: idx_provider_batch_runs_preview; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_provider_batch_runs_preview ON public.memory_provider_batch_runs USING btree (preview_id);


--
-- Name: idx_provider_batch_runs_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_provider_batch_runs_status ON public.memory_provider_batch_runs USING btree (local_status, next_poll_at);


--
-- Name: idx_provider_batch_sources_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_provider_batch_sources_source ON public.memory_provider_batch_request_sources USING btree (source_type, source_id);


--
-- Name: idx_vision_webhooks_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_vision_webhooks_active ON public.vision_completion_webhooks USING btree (is_active);


--
-- Name: idx_webhook_sources_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_webhook_sources_active ON public.memory_webhook_sources USING btree (is_active);


--
-- Name: uq_interactions_crm_dedup_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uq_interactions_crm_dedup_key ON public.interactions USING btree (COALESCE((metadata ->> 'crm_dedup_key'::text), ''::text)) WHERE (COALESCE((metadata ->> 'crm_dedup_key'::text), ''::text) <> ''::text);


--
-- Name: knowledge_attachments knowledge_attachments_knowledge_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_attachments
    ADD CONSTRAINT knowledge_attachments_knowledge_id_fkey FOREIGN KEY (knowledge_id) REFERENCES public.knowledge(id) ON DELETE SET NULL;


--
-- Name: knowledge_consolidation_event_sources knowledge_consolidation_event_sources_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_event_sources
    ADD CONSTRAINT knowledge_consolidation_event_sources_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.knowledge_consolidation_events(id) ON DELETE CASCADE;


--
-- Name: knowledge_consolidation_preview_sources knowledge_consolidation_preview_sources_preview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_consolidation_preview_sources
    ADD CONSTRAINT knowledge_consolidation_preview_sources_preview_id_fkey FOREIGN KEY (preview_id) REFERENCES public.knowledge_consolidation_previews(id) ON DELETE CASCADE;


--
-- Name: knowledge_evidence_bundle_members knowledge_evidence_bundle_members_bundle_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_evidence_bundle_members
    ADD CONSTRAINT knowledge_evidence_bundle_members_bundle_id_fkey FOREIGN KEY (bundle_id) REFERENCES public.knowledge_evidence_bundles(id) ON DELETE CASCADE;


--
-- Name: knowledge_hygiene_cluster_members knowledge_hygiene_cluster_members_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_hygiene_cluster_members
    ADD CONSTRAINT knowledge_hygiene_cluster_members_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.knowledge_hygiene_clusters(id) ON DELETE CASCADE;


--
-- Name: knowledge_hygiene_clusters knowledge_hygiene_clusters_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.knowledge_hygiene_clusters
    ADD CONSTRAINT knowledge_hygiene_clusters_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.knowledge_hygiene_runs(id) ON DELETE CASCADE;


--
-- Name: memory_agent_entities memory_agent_entities_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_agent_entities
    ADD CONSTRAINT memory_agent_entities_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.memory_agents(id) ON DELETE CASCADE;


--
-- Name: memory_entity_subtypes memory_entity_subtypes_entity_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_entity_subtypes
    ADD CONSTRAINT memory_entity_subtypes_entity_type_id_fkey FOREIGN KEY (entity_type_id) REFERENCES public.memory_entity_types(id) ON DELETE CASCADE;


--
-- Name: memory_llm_configs memory_llm_configs_provider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_llm_configs
    ADD CONSTRAINT memory_llm_configs_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.memory_llm_providers(id) ON DELETE SET NULL;


--
-- Name: memory_provider_batch_request_sources memory_provider_batch_request_sources_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_request_sources
    ADD CONSTRAINT memory_provider_batch_request_sources_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.memory_provider_batch_requests(id) ON DELETE CASCADE;


--
-- Name: memory_provider_batch_requests memory_provider_batch_requests_batch_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_requests
    ADD CONSTRAINT memory_provider_batch_requests_batch_run_id_fkey FOREIGN KEY (batch_run_id) REFERENCES public.memory_provider_batch_runs(id) ON DELETE CASCADE;


--
-- Name: memory_provider_batch_runs memory_provider_batch_runs_preview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memory_provider_batch_runs
    ADD CONSTRAINT memory_provider_batch_runs_preview_id_fkey FOREIGN KEY (preview_id) REFERENCES public.memory_operation_previews(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--


