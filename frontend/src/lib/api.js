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
            localStorage.removeItem('auth_token');
            window.location.href = '/';
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
export const deleteEntityType = (id) => api.delete(`/memory/config/entity-types/${id}`);

// Entity Subtypes
export const getEntitySubtypes = (typeId) => api.get(`/memory/config/entity-types/${typeId}/subtypes`);
export const createEntitySubtype = (data) => api.post('/memory/config/entity-subtypes', data);
export const deleteEntitySubtype = (id) => api.delete(`/memory/config/entity-subtypes/${id}`);

// Lesson Types
export const getLessonTypes = () => api.get('/memory/config/lesson-types');
export const createLessonType = (data) => api.post('/memory/config/lesson-types', data);
export const deleteLessonType = (id) => api.delete(`/memory/config/lesson-types/${id}`);

// Channel Types
export const getChannelTypes = () => api.get('/memory/config/channel-types');
export const createChannelType = (data) => api.post('/memory/config/channel-types', data);
export const deleteChannelType = (id) => api.delete(`/memory/config/channel-types/${id}`);

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

// LLM Configurations
export const getLLMConfigs = () => api.get('/memory/config/llm-configs');
export const getLLMConfigByTask = (taskType) => api.get(`/memory/config/llm-configs/${taskType}`);
export const createLLMConfig = (data) => api.post('/memory/config/llm-configs', data);
export const updateLLMConfig = (id, data) => api.put(`/memory/config/llm-configs/${id}`, data);
export const deleteLLMConfig = (id) => api.delete(`/memory/config/llm-configs/${id}`);

// Memory Settings
export const getMemorySettings = () => api.get('/memory/config/settings');
export const updateMemorySettings = (data) => api.put('/memory/config/settings', data);

// Memory Explorer - Admin UI
export const searchMemories = (data) => api.post('/memory/search', data);
export const getDailyMemories = (date) => api.get(`/memory/daily/${date}`);
export const getMemoryDetail = (id) => api.get(`/memory/memories/${id}`);
export const getTimeline = (entityType, entityId) => api.get(`/memory/admin/timeline/${entityType}/${entityId}`);

// Lessons - Admin UI
export const getLessonsAdmin = (params) => api.get('/memory/admin/lessons', { params });
export const createLessonAdmin = (data) => api.post('/memory/admin/lessons', data);
export const updateLessonAdmin = (id, data) => api.put(`/memory/admin/lessons/${id}`, data);
export const deleteLessonAdmin = (id) => api.delete(`/memory/admin/lessons/${id}`);

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
