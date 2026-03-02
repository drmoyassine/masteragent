import React, { useState, useCallback } from "react";
import { Brain, Layers, Eye, EyeOff, AlertCircle, CheckCircle2, FileText, ExternalLink, RefreshCw, Search, ChevronDown, Cpu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import { fetchProviderModels } from "@/lib/api";

// ─── Task type display metadata ───────────────────────────────────────────────
const TASK_TYPE_LABELS = {
    summarization: { label: "Summarization", icon: Brain, color: "bg-blue-500" },
    embedding: { label: "Embeddings", icon: Layers, color: "bg-green-500" },
    vision: { label: "Vision/Doc Parsing", icon: Eye, color: "bg-purple-500" },
    entity_extraction: { label: "Entity Extraction (NER)", icon: Cpu, color: "bg-amber-500" },
    pii_scrubbing: { label: "PII Scrubbing", icon: EyeOff, color: "bg-red-500" },
};

// ─── Providers valid per task type ────────────────────────────────────────────
const PROVIDERS_BY_TASK = {
    embedding: [
        { value: "openai", label: "OpenAI", hasModelFetch: true },
        { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
        { value: "ollama", label: "Ollama", hasModelFetch: true, needsBaseUrl: true },
        { value: "gemini", label: "Google Gemini", hasModelFetch: true },
        { value: "custom", label: "Custom API", hasModelFetch: false },
    ],
    summarization: [
        { value: "openai", label: "OpenAI", hasModelFetch: true },
        { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
        { value: "ollama", label: "Ollama", hasModelFetch: true, needsBaseUrl: true },
        { value: "anthropic", label: "Anthropic", hasModelFetch: true },
        { value: "gemini", label: "Google Gemini", hasModelFetch: true },
        { value: "custom", label: "Custom API", hasModelFetch: false },
    ],
    vision: [
        { value: "openai", label: "OpenAI", hasModelFetch: true },
        { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
        { value: "anthropic", label: "Anthropic", hasModelFetch: true },
        { value: "gemini", label: "Google Gemini", hasModelFetch: true },
        { value: "custom", label: "Custom API", hasModelFetch: false },
    ],
    entity_extraction: [
        { value: "gliner", label: "GLiNER (Local)", hasModelFetch: false },
        { value: "openai", label: "OpenAI", hasModelFetch: true },
        { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
        { value: "anthropic", label: "Anthropic", hasModelFetch: true },
        { value: "gemini", label: "Google Gemini", hasModelFetch: true },
        { value: "ollama", label: "Ollama", hasModelFetch: true, needsBaseUrl: true },
        { value: "custom", label: "Custom API", hasModelFetch: false },
    ],
    pii_scrubbing: [
        { value: "zendata", label: "Zendata (PII)", hasModelFetch: false },
        { value: "openai", label: "OpenAI", hasModelFetch: true },
        { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
        { value: "anthropic", label: "Anthropic", hasModelFetch: true },
        { value: "gemini", label: "Google Gemini", hasModelFetch: true },
        { value: "custom", label: "Custom API", hasModelFetch: false },
    ],
};

// Default base URLs per provider
const DEFAULT_BASE_URLS = {
    openai: "https://api.openai.com/v1",
    anthropic: "https://api.anthropic.com/v1",
    gemini: "https://generativelanguage.googleapis.com/v1beta",
    openrouter: "https://openrouter.ai/api/v1",
    ollama: "http://localhost:11434",
    gliner: "http://gliner:8002",
    zendata: "",
    custom: "",
};

// ─── Searchable Model Combobox ────────────────────────────────────────────────
function ModelCombobox({ value, onChange, models, loading, error, onFetch, canFetch, provider }) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState("");

    const filtered = models.filter((m) =>
        m.toLowerCase().includes(search.toLowerCase())
    );

    if (!canFetch) {
        // Free-text input for providers that don't support model fetching
        return (
            <Input
                value={value || ""}
                onChange={(e) => onChange(e.target.value)}
                placeholder="e.g., gpt-4o-mini"
            />
        );
    }

    return (
        <div className="flex gap-2">
            <Popover open={open} onOpenChange={setOpen}>
                <PopoverTrigger asChild>
                    <Button
                        variant="outline"
                        role="combobox"
                        className="w-full justify-between font-normal"
                        disabled={loading}
                    >
                        <span className="truncate text-left">{value || "Select or type a model..."}</span>
                        <ChevronDown className="w-4 h-4 shrink-0 opacity-50 ml-2" />
                    </Button>
                </PopoverTrigger>
                <PopoverContent className="w-full p-0 min-w-[320px]" align="start">
                    <div className="flex items-center border-b px-3">
                        <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
                        <input
                            className="flex h-10 w-full bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground"
                            placeholder="Search or type model name..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                        />
                    </div>
                    <div className="max-h-56 overflow-y-auto py-1">
                        {/* Allow typing a custom value */}
                        {search && !filtered.includes(search) && (
                            <div
                                className="flex cursor-pointer items-center px-3 py-2 text-sm hover:bg-accent"
                                onClick={() => { onChange(search); setSearch(""); setOpen(false); }}
                            >
                                <span className="text-muted-foreground mr-1">Use:</span> {search}
                            </div>
                        )}
                        {filtered.length === 0 && !search && (
                            <div className="py-6 text-center text-sm text-muted-foreground">
                                {error ? (
                                    <span className="text-red-400">{error}</span>
                                ) : (
                                    "Click refresh to fetch models"
                                )}
                            </div>
                        )}
                        {filtered.map((model) => (
                            <div
                                key={model}
                                className={`flex cursor-pointer items-center px-3 py-2 text-sm hover:bg-accent ${value === model ? "bg-accent/50 font-medium" : ""}`}
                                onClick={() => { onChange(model); setSearch(""); setOpen(false); }}
                            >
                                {model}
                            </div>
                        ))}
                    </div>
                </PopoverContent>
            </Popover>
            <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={onFetch}
                disabled={loading}
                title="Fetch available models from provider"
            >
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
        </div>
    );
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function LLMProviderSettings({
    llmConfigs,
    editingConfig,
    setEditingConfig,
    showApiKey,
    setShowApiKey,
    onSaveConfig
}) {
    const [modelLists, setModelLists] = useState({}); // { [configId]: string[] }
    const [fetchingModels, setFetchingModels] = useState({}); // { [configId]: bool }
    const [fetchErrors, setFetchErrors] = useState({}); // { [configId]: string }

    const handleFetchModels = useCallback(async (configId) => {
        if (!editingConfig) return;
        const provider = editingConfig.provider;
        const apiKey = editingConfig.api_key || "";
        const apiBaseUrl = editingConfig.api_base_url || DEFAULT_BASE_URLS[provider] || "";

        setFetchingModels((prev) => ({ ...prev, [configId]: true }));
        setFetchErrors((prev) => ({ ...prev, [configId]: null }));

        try {
            const payload = {
                provider,
                api_base_url: apiBaseUrl,
                config_id: configId, // allows backend to use stored key as fallback
            };

            // Only include api_key in the payload if it's not empty
            if (apiKey && apiKey.trim() !== "") {
                payload.api_key = apiKey.trim();
            }

            const response = await fetchProviderModels(payload);
            setModelLists((prev) => ({ ...prev, [configId]: response.data.models }));
        } catch (err) {
            const detail = err.response?.data?.detail || "Failed to fetch models. Check API key.";
            setFetchErrors((prev) => ({ ...prev, [configId]: detail }));
        } finally {
            setFetchingModels((prev) => ({ ...prev, [configId]: false }));
        }
    }, [editingConfig]);

    return (
        <div className="space-y-4 max-w-4xl">
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>LLM API Configurations</CardTitle>
                            <CardDescription>
                                Configure API keys and endpoints for each task type. These are used by the Memory System for processing data.
                            </CardDescription>
                        </div>
                        <Button asChild variant="outline" size="sm">
                            <a href="/api/docs" target="_blank" rel="noopener noreferrer" className="flex items-center gap-2">
                                <FileText className="w-4 h-4" />
                                API Endpoints Docs
                            </a>
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    {llmConfigs.map((config) => {
                        const taskInfo = TASK_TYPE_LABELS[config.task_type] || { label: config.task_type, icon: Brain, color: "bg-gray-500" };
                        const TaskIcon = taskInfo.icon;
                        const isEditing = editingConfig?.id === config.id;
                        const taskProviders = PROVIDERS_BY_TASK[config.task_type] || [];

                        // Use the currently selected provider in the editor, or the stored one if not editing
                        const activeProviderValue = isEditing ? editingConfig.provider : config.provider;
                        const currentProviderMeta = taskProviders.find((p) => p.value === activeProviderValue);

                        const canFetchModels = isEditing && (currentProviderMeta?.hasModelFetch ?? false);
                        const needsBaseUrl = currentProviderMeta?.needsBaseUrl ?? false;

                        // Key inheritance check: Does ANY other configuration have a key for this ACTIVE provider?
                        const otherConfigWithKey = llmConfigs.find(c =>
                            c.id !== config.id &&
                            c.provider === activeProviderValue &&
                            c.api_key_preview
                        );

                        // It's considered 'configured' if the specific config for this task has a key for the ACTIVE provider
                        const isSpecificallyConfigured = config.provider === activeProviderValue && !!config.api_key_preview;

                        // It's considered 'inherited' if NOT specifically configured, but some OTHER config has a key.
                        const hasInheritedKey = !isSpecificallyConfigured && !!otherConfigWithKey;

                        const isGloballyConfigured = isSpecificallyConfigured || hasInheritedKey;

                        return (
                            <Card key={config.id} className={`border-l-4 ${taskInfo.color} bg-card/50`}>
                                <CardContent className="pt-4">
                                    <div className="flex items-start justify-between">
                                        <div className="flex items-center gap-3">
                                            <div className={`p-2 rounded-lg ${taskInfo.color}`}>
                                                <TaskIcon className="w-5 h-5 text-white" />
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-foreground">{taskInfo.label}</h3>
                                                <p className="text-sm text-muted-foreground">
                                                    {isEditing ? `Editing: ${activeProviderValue}` : `${config.name} (${config.provider})`}
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {isGloballyConfigured ? (
                                                <Badge variant="default" className="bg-green-500">
                                                    <CheckCircle2 className="w-3 h-3 mr-1" /> Configured
                                                </Badge>
                                            ) : (
                                                <Badge variant="outline" className="border-amber-500 text-amber-500">
                                                    <AlertCircle className="w-3 h-3 mr-1" /> Needs API Key
                                                </Badge>
                                            )}
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => setEditingConfig(isEditing ? null : { ...config, api_key: null })}
                                            >
                                                {isEditing ? "Cancel" : "Edit"}
                                            </Button>
                                        </div>
                                    </div>

                                    {isEditing && (
                                        <div className="mt-4 pt-4 border-t space-y-4">
                                            {/* Provider Selection */}
                                            <div className="space-y-2">
                                                <Label>Provider</Label>
                                                <Select
                                                    value={editingConfig.provider}
                                                    onValueChange={(v) => {
                                                        const defaultUrl = DEFAULT_BASE_URLS[v] || "";
                                                        setEditingConfig({
                                                            ...editingConfig,
                                                            provider: v,
                                                            api_base_url: defaultUrl,
                                                            model_name: "", // Reset model when provider changes
                                                        });
                                                        // Clear cached model list when provider changes
                                                        setModelLists((prev) => ({ ...prev, [config.id]: [] }));
                                                    }}
                                                >
                                                    <SelectTrigger>
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {taskProviders.map((opt) => (
                                                            <SelectItem key={opt.value} value={opt.value}>
                                                                {opt.label}
                                                            </SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                                {editingConfig.provider === "ollama" && (
                                                    <p className="text-xs text-muted-foreground">
                                                        Ollama supports both local (<code>http://localhost:11434</code>) and cloud-hosted instances.
                                                    </p>
                                                )}
                                                {editingConfig.provider === "openrouter" && (
                                                    <p className="text-xs text-muted-foreground">
                                                        Get your API key at{" "}
                                                        <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" className="text-primary underline">
                                                            openrouter.ai/keys
                                                        </a>
                                                    </p>
                                                )}
                                            </div>

                                            {/* API Base URL — always shown, pre-populated with defaults */}
                                            <div className="space-y-2">
                                                <Label>API Base URL {needsBaseUrl && <span className="text-primary ml-1 text-xs">(required)</span>}</Label>
                                                <Input
                                                    value={editingConfig.api_base_url || ""}
                                                    onChange={(e) => setEditingConfig({ ...editingConfig, api_base_url: e.target.value })}
                                                    placeholder={DEFAULT_BASE_URLS[editingConfig.provider] || "https://..."}
                                                />
                                            </div>

                                            {/* Model Selection */}
                                            <div className="space-y-2">
                                                <Label>Model</Label>
                                                <ModelCombobox
                                                    value={editingConfig.model_name || ""}
                                                    onChange={(v) => setEditingConfig({ ...editingConfig, model_name: v })}
                                                    models={modelLists[config.id] || []}
                                                    loading={fetchingModels[config.id] || false}
                                                    error={fetchErrors[config.id]}
                                                    onFetch={() => handleFetchModels(config.id)}
                                                    canFetch={canFetchModels}
                                                    provider={editingConfig.provider}
                                                />
                                                {canFetchModels && !isGloballyConfigured && !editingConfig.api_key && (
                                                    <p className="text-xs text-amber-400">Save an API key first to enable model fetching.</p>
                                                )}
                                                {canFetchModels && hasInheritedKey && !editingConfig.api_key && (
                                                    <p className="text-xs text-blue-400 flex items-center gap-1">
                                                        <CheckCircle2 className="w-3 h-3" /> Using shared provider API key.
                                                    </p>
                                                )}
                                                {fetchErrors[config.id] && (
                                                    <p className="text-xs text-red-400">{fetchErrors[config.id]}</p>
                                                )}
                                            </div>

                                            {/* API Key */}
                                            <div className="space-y-2">
                                                <Label>API Key</Label>
                                                <div className="flex gap-2">
                                                    <Input
                                                        type={showApiKey[config.id] ? "text" : "password"}
                                                        value={editingConfig.api_key || ""}
                                                        onChange={(e) => setEditingConfig({ ...editingConfig, api_key: e.target.value })}
                                                        placeholder={
                                                            hasInheritedKey
                                                                ? "Already configured (enter to override)"
                                                                : editingConfig.provider === "ollama"
                                                                    ? "No key required for local"
                                                                    : "Enter API key"
                                                        }
                                                    />
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        size="icon"
                                                        onClick={() => setShowApiKey({ ...showApiKey, [config.id]: !showApiKey[config.id] })}
                                                    >
                                                        {showApiKey[config.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                                                    </Button>
                                                </div>
                                                {config.api_key_preview && !editingConfig.api_key && (
                                                    <p className="text-xs text-muted-foreground mt-1">Current: {config.api_key_preview}</p>
                                                )}
                                            </div>

                                            <Button onClick={() => {
                                                const payload = { ...editingConfig };
                                                if (!payload.api_key || payload.api_key.trim() === "") {
                                                    delete payload.api_key;
                                                }
                                                onSaveConfig(config.id, payload);
                                            }}>
                                                Save Configuration
                                            </Button>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        );
                    })}
                </CardContent>
            </Card>

            {/* API Documentation */}
            <Card className="border-primary/20 bg-primary/5">
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-primary/10">
                            <FileText className="w-5 h-5 text-primary" />
                        </div>
                        <div>
                            <CardTitle>API Documentation</CardTitle>
                            <CardDescription>
                                View the interactive OpenAPI (Swagger) documentation to explore and test the available endpoints.
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <CardContent>
                    <div className="flex gap-4">
                        <Button asChild variant="default" className="font-mono">
                            <a href="/api/docs" target="_blank" rel="noopener noreferrer">
                                <ExternalLink className="w-4 h-4 mr-2" />
                                Swagger UI
                            </a>
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
