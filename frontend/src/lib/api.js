import axios from 'axios';

// Use empty string for relative URLs (production) or env variable (development)
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
    baseURL: API_BASE,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle 401 responses
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            console.warn('Unauthorized request (401), redirecting to login...', error.config.url);
            localStorage.removeItem('auth_token');
            // Use window.location.replace to prevent back-button loops
            window.location.replace('/');
        }
        return Promise.reject(error);
    }
);

// Auth
export const getAuthStatus = () => api.get('/auth/status');
export const signup = (data) => api.post('/auth/signup', data);
export const login = (data) => api.post('/auth/login', data);
export const getGitHubLoginUrl = () => api.get('/auth/github/login');
export const logout = () => {
    localStorage.removeItem('auth_token');
    return api.post('/auth/logout');
};

// Settings
export const getSettings = () => api.get('/settings');
export const saveSettings = (data) => api.post('/settings', data);
export const deleteSettings = () => api.delete('/settings');
export const setStorageMode = (storageMode) => api.post('/settings/storage-mode', { storage_mode: storageMode });

// Templates
export const getTemplates = () => api.get('/templates');
export const getTemplate = (id) => api.get(`/templates/${id}`);

// Prompts
export const getPrompts = () => api.get('/prompts');
export const getPrompt = (id) => api.get(`/prompts/${id}`);
export const createPrompt = (data) => api.post('/prompts', data);
export const exportPromptMarkdown = (id) => api.get(`/prompts/${id}/export.md`, { responseType: 'blob' });
export const importPromptMarkdown = (data) => api.post('/prompts/import-md', data);
export const updatePrompt = (id, data) => api.put(`/prompts/${id}`, data);
export const deletePrompt = (id) => api.delete(`/prompts/${id}`);

// Sections
export const getPromptSections = (promptId, version = 'v1') =>
    api.get(`/prompts/${promptId}/sections`, { params: { version } });
export const getSectionContent = (promptId, filename, version = 'v1') =>
    api.get(`/prompts/${promptId}/sections/${filename}`, { params: { version } });
export const createSection = (promptId, data, version = 'v1') =>
    api.post(`/prompts/${promptId}/sections`, data, { params: { version } });
export const updateSection = (promptId, filename, data, version = 'v1') =>
    api.put(`/prompts/${promptId}/sections/${filename}`, data, { params: { version } });
export const deleteSection = (promptId, filename, version = 'v1') =>
    api.delete(`/prompts/${promptId}/sections/${filename}`, { params: { version } });
export const reorderSections = (promptId, sections, version = 'main') =>
    api.post(`/prompts/${promptId}/sections/reorder`, { sections }, { params: { version } });

// Versions
export const getPromptVersions = (promptId) => api.get(`/prompts/${promptId}/versions`);
export const createVersion = (promptId, data) => api.post(`/prompts/${promptId}/versions`, data);

// Render
export const renderPrompt = (promptId, version, variables = {}, apiKey = null) => {
    const headers = apiKey ? { 'X-API-Key': apiKey } : {};
    return api.post(`/prompts/${promptId}/${version}/render`, { variables }, { headers });
};

// API Keys
export const getApiKeys = () => api.get('/keys');
export const createApiKey = (name) => api.post('/keys', { name });
export const deleteApiKey = (id) => api.delete(`/keys/${id}`);

// Health
export const healthCheck = () => api.get('/health');

// ============================================
// Memory System APIs
// ============================================

// Memory Health
export const memoryHealthCheck = () => api.get('/memory/health');
export const initMemorySystem = () => api.post('/memory/init');

// Entity Types
export const getEntityTypes = () => api.get('/memory/config/entity-types');
export const createEntityType = (data) => api.post('/memory/config/entity-types', data);
export const updateEntityType = (id, data) => api.patch(`/memory/config/entity-types/${id}`, data);
export const deleteEntityType = (id) => api.delete(`/memory/config/entity-types/${id}`);

// Entity Subtypes
export const getEntitySubtypes = (typeId) => api.get(`/memory/config/entity-types/${typeId}/subtypes`);
export const createEntitySubtype = (data) => api.post('/memory/config/entity-subtypes', data);
export const deleteEntitySubtype = (id) => api.delete(`/memory/config/entity-subtypes/${id}`);


// Agents
export const getAgents = () => api.get('/memory/config/agents');
export const createAgent = (data) => api.post('/memory/config/agents', data);
export const updateAgent = (id, data) => api.patch(`/memory/config/agents/${id}`, data);
export const deleteAgent = (id) => api.delete(`/memory/config/agents/${id}`);

// System Prompts
export const getSystemPrompts = () => api.get('/memory/config/system-prompts');
export const createSystemPrompt = (data) => api.post('/memory/config/system-prompts', data);
export const updateSystemPrompt = (id, data) => api.put(`/memory/config/system-prompts/${id}`, data);
export const deleteSystemPrompt = (id) => api.delete(`/memory/config/system-prompts/${id}`);

// LLM Providers
export const getLLMProviders = () => api.get('/memory/config/llm-providers');
export const createLLMProvider = (data) => api.post('/memory/config/llm-providers', data);
export const updateLLMProvider = (id, data) => api.put(`/memory/config/llm-providers/${id}`, data);
export const deleteLLMProvider = (id) => api.delete(`/memory/config/llm-providers/${id}`);
export const testLLMProvider = (data) => api.post('/memory/config/llm-providers/test', data);

// LLM Configurations
export const getLLMConfigs = () => api.get('/memory/config/llm-configs');
export const getLLMConfigByTask = (taskType) => api.get(`/memory/config/llm-configs/${taskType}`);
export const createLLMConfig = (data) => api.post('/memory/config/llm-configs', data);
export const reorderPipelineNodes = (data) => api.patch(`/memory/config/llm-configs/reorder`, data);
export const updateLLMConfig = (id, data) => api.put(`/memory/config/llm-configs/${id}`, data);
export const deleteLLMConfig = (id) => api.delete(`/memory/config/llm-configs/${id}`);
export const fetchProviderModels = (data) => api.post('/memory/config/llm-configs/fetch-models', data);

// Memory Settings
export const getMemorySettings = () => api.get('/memory/config/settings');
export const updateMemorySettings = (data) => api.put('/memory/config/settings', data);

// Entity Type Config (per-type NER schema, compaction thresholds, etc.)
export const getEntityTypeConfig = (entityType) => api.get(`/memory/entity-type-config/${entityType}`);
export const updateEntityTypeConfig = (entityType, data) => api.patch(`/memory/entity-type-config/${entityType}`, data);


// Memory Explorer - Admin UI
export const searchMemories = (data) => api.post('/memory/admin/search', data);
export const getInteractionsAdmin = (params) => api.get('/memory/interactions', { params });
export const updateInteractionAdmin = (id, data) => api.put(`/memory/interactions/${id}`, data);
export const deleteInteractionAdmin = (id) => api.delete(`/memory/interactions/${id}`);
export const bulkDeleteInteractionsAdmin = (data) => api.post('/memory/interactions/bulk-delete', data);
export const bulkReprocessInteractionsAdmin = (data) => api.post('/memory/interactions/bulk-reprocess', data);
export const getMemoriesAdmin = (params) => api.get('/memory/admin/memories', { params });
export const getMemoryDetail = (id) => api.get(`/memory/admin/memories/${id}`);
export const updateMemoryAdmin = (id, data) => api.patch(`/memory/admin/memories/${id}`, data);
export const deleteMemoryAdmin = (id) => api.delete(`/memory/admin/memories/${id}`);
export const bulkDeleteMemoriesAdmin = (data) => api.post('/memory/admin/memories/bulk-delete', data);
export const bulkReprocessMemoriesAdmin = (data) => api.post('/memory/admin/memories/bulk-reprocess', data);
export const getInsightsAdmin = (params) => api.get('/memory/admin/intelligence', { params });
export const updateInsightAdmin = (id, data) => api.patch(`/memory/admin/intelligence/${id}`, data);
export const deleteInsightAdmin = (id) => api.delete(`/memory/admin/intelligence/${id}`);
export const bulkDeleteIntelligenceAdmin = (data) => api.post('/memory/admin/intelligence/bulk-delete', data);
export const bulkApproveIntelligenceAdmin = (data) => api.post('/memory/admin/intelligence/bulk-approve', data);
export const getInteractionFilterOptionsAdmin = (params) => api.get('/memory/interactions/filter-options', { params });
export const getDailyMemories = (date) => api.get(`/memory/admin/daily/${date}`);
export const getTimeline = (entityType, entityId) => api.get(`/memory/admin/timeline/${entityType}/${entityId}`);
export const triggerMemoryGeneration = (includeToday = false) => api.post('/memory/trigger/generate-memories', null, { params: { include_today: includeToday } });
export const triggerIntelligenceCheck = () => api.post('/memory/trigger/run-intelligence-check');
export const triggerKnowledgeCheck = (drain = false, options = {}) => api.post('/memory/trigger/run-knowledge-check', null, { params: { drain, ...options } });
export const triggerPlaybookExtraction = () => api.post('/memory/trigger/extract-playbooks');
export const reprocessIntelligence = (intelligenceIds) => api.post('/memory/trigger/reprocess-intelligence', { intelligence_ids: intelligenceIds });
export const triggerBackfillProfiles = () => api.post('/memory/trigger/backfill-profiles');

// Public Knowledge - Admin UI
export const getKnowledgeAdmin = (params) => api.get('/memory/admin/knowledge', { params });
export const createKnowledgeAdmin = (data) => api.post('/memory/admin/knowledge', data);
export const uploadKnowledgeAttachment = (file) => {
  const form = new FormData();
  form.append('file', file);
  return api.post('/memory/admin/knowledge/attachments/preview', form, { headers: { 'Content-Type': 'multipart/form-data' } });
};
export const getKnowledgeAttachment = (id) => api.get(`/memory/admin/knowledge/attachments/${id}`);
export const proposeKnowledgeFromAttachments = (data) => api.post('/memory/admin/knowledge/attachments/propose', data);
export const proposeKnowledgeDraft = (data) => api.post('/memory/admin/knowledge/draft/propose', data);
export const updateKnowledgeAdmin = (id, data) => api.patch(`/memory/admin/knowledge/${id}`, data);
export const deleteKnowledgeAdmin = (id) => api.delete(`/memory/admin/knowledge/${id}`);
export const bulkDeleteKnowledgeAdmin = (data) => api.post('/memory/admin/knowledge/bulk-delete', data);
export const getKnowledgeDetail = (id) => api.get(`/memory/admin/knowledge/${id}`);
export const submitKnowledgeFeedback = (id, data) => api.post(`/memory/admin/knowledge/${id}/feedback`, data);
export const exportKnowledgeMarkdown = (id) => api.get(`/memory/admin/knowledge/${id}/skill.md`, { responseType: 'blob' });
export const exportKnowledgePack = (params) => api.get('/memory/admin/knowledge-pack', { params, responseType: 'blob' });
export const importSkillMd = (data) => api.post('/memory/skills/import', data);
export const getPipelineRuns = (params) => api.get('/memory/pipeline-runs', { params });
export const getMaintenanceControls = () => api.get('/memory/maintenance-controls');
export const getMaintenanceEligibleCounts = () => api.get('/memory/maintenance/eligible-counts');
export const refreshMaintenanceEligibleCounts = () => api.post('/memory/maintenance/eligible-counts/refresh');
export const setMaintenanceControl = (job, command) => api.post(`/memory/maintenance-controls/${encodeURIComponent(job)}/${command}`);
export const getKnowledgeOperationCapabilities = () => api.get('/memory/admin/knowledge/operations/capabilities');
export const previewKnowledgeOperation = (payload) => api.post('/memory/admin/knowledge/operations/preview', payload);
export const submitKnowledgeOperation = (payload) => api.post('/memory/admin/knowledge/operations/runs', payload);
export const getKnowledgeOperationRuns = (params = {}) => api.get('/memory/admin/knowledge/operations/runs', { params });
export const syncKnowledgeOperation = (runId) => api.post(`/memory/admin/knowledge/operations/runs/${encodeURIComponent(runId)}/sync-status`);
export const controlKnowledgeOperation = (runId, command) => api.post(`/memory/admin/knowledge/operations/runs/${encodeURIComponent(runId)}/${command}`);
export const getKnowledgeOperationRequests = (runId, params = {}) => api.get(`/memory/admin/knowledge/operations/runs/${encodeURIComponent(runId)}/requests`, { params });
export const getSystemAlerts = () => api.get('/memory/system-alerts');
export const resolveSystemAlert = (code) => api.post(`/memory/system-alerts/${code}/resolve`);
export const getKnowledgeById = (id) => api.get(`/memory/admin/knowledge/${id}`);
export const getKnowledgeFacets = (params) => api.get('/memory/knowledge/facets', { params });
export const triggerBackfillFacets = (options = {}) => api.post('/memory/trigger/backfill-facets', null, { params: options });
export const triggerReflectTelemetry = (reflectionDate) => api.post('/memory/trigger/reflect-telemetry', null, { params: reflectionDate ? { reflection_date: reflectionDate } : {} });
export const triggerInteractionRetention = (options = {}) => api.post('/memory/trigger/interaction-retention', null, { params: options });
export const getMemoryStats = () => api.get('/memory/admin/stats');

// Knowledge Hygiene & Consolidation - Admin UI
// Candidate similarity only DISCOVERS related records; merge decisions come
// from category-aware LLM proposals + admin review. Preview never mutates.
export const consolidationPreview = (data) => api.post('/memory/admin/knowledge/consolidations/preview', data);
export const getConsolidationMetrics = (data) => api.post('/memory/admin/knowledge/consolidations/metrics', data);
export const getConsolidationPreview = (previewId) => api.get(`/memory/admin/knowledge/consolidations/previews/${previewId}`);
export const regenerateConsolidationPreview = (previewId) => api.post(`/memory/admin/knowledge/consolidations/previews/${previewId}/regenerate`);
export const applyConsolidation = (data) => api.post('/memory/admin/knowledge/consolidations/apply', data);
export const getConsolidationEvent = (eventId) => api.get(`/memory/admin/knowledge/consolidations/events/${eventId}`);
export const reverseConsolidationEvent = (eventId) => api.post(`/memory/admin/knowledge/consolidations/events/${eventId}/reverse`);
export const getConsolidationLineage = (knowledgeId) => api.get(`/memory/admin/knowledge/consolidations/lineage/${knowledgeId}`);
export const analyzeHygieneNow = (data) => api.post('/memory/admin/knowledge/consolidations/analyze', data);
export const getHygieneRun = (runId) => api.get(`/memory/admin/knowledge/hygiene-runs/${runId}`);
export const getEmbeddingCoverage = () => api.get('/memory/admin/knowledge/consolidations/embedding-coverage');
export const backfillEmbeddings = (options = {}) => api.post('/memory/admin/knowledge/consolidations/backfill-embeddings', null, { params: options });

// Outbound Webhooks - Admin UI
export const getOutboundWebhooks = () => api.get('/memory/outbound-webhooks');
export const createOutboundWebhook = (data) => api.post('/memory/outbound-webhooks', data);
export const updateOutboundWebhook = (id, data) => api.patch(`/memory/outbound-webhooks/${id}`, data);
export const deleteOutboundWebhook = (id) => api.delete(`/memory/outbound-webhooks/${id}`);

// Vision Completion Webhooks - Admin UI
export const getVisionWebhooks = () => api.get('/memory/vision-webhooks');
export const createVisionWebhook = (data) => api.post('/memory/vision-webhooks', data);
export const updateVisionWebhook = (id, data) => api.patch(`/memory/vision-webhooks/${id}`, data);
export const deleteVisionWebhook = (id) => api.delete(`/memory/vision-webhooks/${id}`);

// ============================================
// Variables System APIs
// ============================================

// Account Variables
export const getAccountVariables = () => api.get('/account-variables');
export const createAccountVariable = (data) => api.post('/account-variables', data);
export const updateAccountVariable = (name, data) => api.put(`/account-variables/${name}`, data);
export const deleteAccountVariable = (name) => api.delete(`/account-variables/${name}`);

// Prompt Variables
export const getPromptVariables = (promptId, version = 'v1') =>
    api.get(`/prompts/${promptId}/variables`, { params: { version } });
export const createPromptVariable = (promptId, data, version = 'v1') =>
    api.post(`/prompts/${promptId}/variables`, { ...data, version });
export const updatePromptVariable = (promptId, name, data, version = 'v1') =>
    api.put(`/prompts/${promptId}/variables/${name}`, { ...data, version });
export const deletePromptVariable = (promptId, name, version = 'v1') =>
    api.delete(`/prompts/${promptId}/variables/${name}`, { params: { version } });

// Combined (for autocomplete)
export const getAvailableVariables = (promptId, version = 'v1') =>
    api.get(`/prompts/${promptId}/available-variables`, { params: { version } });

export default api;


