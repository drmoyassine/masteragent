import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API_BASE = `${BACKEND_URL}/api`;

const api = axios.create({
    baseURL: API_BASE,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Settings
export const getSettings = () => api.get('/settings');
export const saveSettings = (data) => api.post('/settings', data);
export const deleteSettings = () => api.delete('/settings');

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
export const getPromptSections = (promptId, version = 'main') => 
    api.get(`/prompts/${promptId}/sections`, { params: { version } });
export const getSectionContent = (promptId, filename, version = 'main') => 
    api.get(`/prompts/${promptId}/sections/${filename}`, { params: { version } });
export const createSection = (promptId, data, version = 'main') => 
    api.post(`/prompts/${promptId}/sections`, data, { params: { version } });
export const updateSection = (promptId, filename, data, version = 'main') => 
    api.put(`/prompts/${promptId}/sections/${filename}`, data, { params: { version } });
export const deleteSection = (promptId, filename, version = 'main') => 
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

export default api;
