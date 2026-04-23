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

// Public Knowledge Types
export const getLessonTypes = () => api.get('/memory/config/knowledge_types');
export const createLessonType = (data) => api.post('/memory/config/knowledge_types', data);
export const deleteLessonType = (id) => api.delete(`/memory/config/knowledge_types/${id}`);


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
export const getInsightsAdmin = (params) => api.get('/memory/intelligence', { params });
export const updateInsightAdmin = (id, data) => api.patch(`/memory/intelligence/${id}`, data);
export const deleteInsightAdmin = (id) => api.delete(`/memory/intelligence/${id}`);
export const getInteractionFilterOptionsAdmin = (params) => api.get('/memory/interactions/filter-options', { params });
export const getDailyMemories = (date) => api.get(`/memory/admin/daily/${date}`);
export const getTimeline = (entityType, entityId) => api.get(`/memory/admin/timeline/${entityType}/${entityId}`);
export const triggerMemoryGeneration = (includeToday = false) => api.post('/memory/trigger/generate-memories', null, { params: { include_today: includeToday } });
export const triggerBackfillProfiles = () => api.post('/memory/trigger/backfill-profiles');

// Public Knowledge - Admin UI
export const getLessonsAdmin = (params) => api.get('/memory/knowledge', { params });
export const createLessonAdmin = (data) => api.post('/memory/knowledge', data);
export const updateLessonAdmin = (id, data) => api.put(`/memory/knowledge/\$\{id\}`, data);
export const deleteLessonAdmin = (id) => api.delete(`/memory/knowledge/\$\{id\}`);

// Outbound Webhooks - Admin UI
export const getOutboundWebhooks = () => api.get('/memory/outbound-webhooks');
export const createOutboundWebhook = (data) => api.post('/memory/outbound-webhooks', data);
export const updateOutboundWebhook = (id, data) => api.patch(`/memory/outbound-webhooks/${id}`, data);
export const deleteOutboundWebhook = (id) => api.delete(`/memory/outbound-webhooks/${id}`);

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


