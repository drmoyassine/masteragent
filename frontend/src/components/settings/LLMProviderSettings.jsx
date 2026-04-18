import React, { useState, useCallback, useEffect } from "react";
import { Brain, Layers, Eye, EyeOff, AlertCircle, CheckCircle2, FileText, ExternalLink, RefreshCw, Search, ChevronDown, Cpu, Plus, Edit2, Trash2, Scissors, Clock, Sparkles } from "lucide-react";
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
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { fetchProviderModels, testLLMProvider, getPrompts } from "@/lib/api";
import { toast } from "sonner";

// ─── Task type display metadata ───────────────────────────────────────────────
export const TASK_TYPE_LABELS = {
    memory_generation: { label: "Memory Generation", icon: Clock, color: "bg-indigo-500" },
    embedding: { label: "Embeddings", icon: Layers, color: "bg-green-500" },
    vision: { label: "Vision/Doc Parsing", icon: Eye, color: "bg-purple-500" },
    entity_extraction: { label: "Entity Extraction (NER)", icon: Cpu, color: "bg-amber-500" },
    pii_scrubbing: { label: "PII Scrubbing", icon: EyeOff, color: "bg-red-500" },
    private_knowledge_generation: { label: "Private Knowledge Generation", icon: Sparkles, color: "bg-teal-500" },
    public_knowledge_generation: { label: "Public Knowledge Generation", icon: GraduationCap, color: "bg-green-500" }
};

const PROVIDER_META = [
    { value: "openai", label: "OpenAI", hasModelFetch: true },
    { value: "anthropic", label: "Anthropic", hasModelFetch: true },
    { value: "gemini", label: "Google Gemini", hasModelFetch: true },
    { value: "openrouter", label: "OpenRouter", hasModelFetch: true },
    { value: "ollama", label: "Ollama", hasModelFetch: true, needsBaseUrl: true },
    { value: "gliner", label: "GLiNER (Local)", hasModelFetch: false },
    { value: "zendata", label: "Zendata (PII)", hasModelFetch: false },
    { value: "custom", label: "Custom API", hasModelFetch: false },
];

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
function ModelCombobox({ value, onChange, models, loading, error, onFetch, canFetch }) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState("");

    const filtered = models.filter((m) =>
        m.toLowerCase().includes(search.toLowerCase())
    );

    if (!canFetch) {
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

// ─── Provider Dialog ──────────────────────────────────────────────────────────
function ProviderDialog({ open, onClose, onSave, existingProvider }) {
    const [formData, setFormData] = useState({
        name: "",
        provider: "openai",
        api_base_url: DEFAULT_BASE_URLS["openai"],
        api_key: "",
        rate_limit_rpm: 60,
        max_retries: 3,
        retry_delay_ms: 1000
    });
    const [showKey, setShowKey] = useState(false);
    const [testing, setTesting] = useState(false);
    const [testResult, setTestResult] = useState(null);

    useEffect(() => {
        if (open) {
            if (existingProvider) {
                setFormData({
                    id: existingProvider.id,
                    name: existingProvider.name || "",
                    provider: existingProvider.provider || "openai",
                    api_base_url: existingProvider.api_base_url || "",
                    api_key: "", // keep empty, relying on the preview placeholder if exists
                    rate_limit_rpm: existingProvider.rate_limit_rpm || 60,
                    max_retries: existingProvider.max_retries !== undefined ? existingProvider.max_retries : 3,
                    retry_delay_ms: existingProvider.retry_delay_ms || 1000
                });
            } else {
                setFormData({
                    name: "",
                    provider: "openai",
                    api_base_url: DEFAULT_BASE_URLS["openai"],
                    api_key: "",
                    rate_limit_rpm: 60,
                    max_retries: 3,
                    retry_delay_ms: 1000
                });
            }
            setTestResult(null);
        }
    }, [open, existingProvider]);

    const handleTest = async () => {
        setTesting(true);
        setTestResult(null);
        try {
            const payload = {
                provider: formData.provider,
                api_base_url: formData.api_base_url,
            };
            if (formData.api_key) payload.api_key = formData.api_key;
            if (formData.id) payload.provider_id = formData.id; // fallback to saved key

            const res = await testLLMProvider(payload);
            setTestResult({ success: true, count: res.data.models.length });
            toast.success(`Successfully fetched ${res.data.models.length} models`);
        } catch (error) {
            setTestResult({ success: false, error: error.response?.data?.detail || "Connection failed" });
            toast.error("Failed to fetch models");
        } finally {
            setTesting(false);
        }
    };

    const handleSave = async () => {
        if (!formData.name.trim()) {
            toast.error("Account name is required");
            return;
        }
        
        const payload = { ...formData };
        if (!payload.api_key) {
            delete payload.api_key; // Don't override with empty string
        }
        
        const success = await onSave(payload);
        if (success) {
            onClose();
        }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle>{existingProvider ? "Edit" : "Add"} Provider Account</DialogTitle>
                    <DialogDescription>
                        Set up a reusable LLM credential that can be assigned to different tasks.
                    </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Account Name</Label>
                        <Input 
                            value={formData.name} 
                            onChange={e => setFormData({ ...formData, name: e.target.value })} 
                            placeholder="e.g. My Prod OpenAI Key" 
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Provider Type</Label>
                        <Select
                            value={formData.provider}
                            onValueChange={v => setFormData({ ...formData, provider: v, api_base_url: DEFAULT_BASE_URLS[v] || "" })}
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {PROVIDER_META.map(p => (
                                    <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label>Base URL</Label>
                        <Input 
                            value={formData.api_base_url} 
                            onChange={e => setFormData({ ...formData, api_base_url: e.target.value })} 
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>API Key</Label>
                        <div className="flex gap-2">
                            <Input 
                                type={showKey ? "text" : "password"}
                                value={formData.api_key} 
                                onChange={e => setFormData({ ...formData, api_key: e.target.value })} 
                                placeholder={existingProvider?.api_key_preview ? `Configured: ${existingProvider.api_key_preview}` : "Enter API key"}
                            />
                            <Button type="button" variant="outline" size="icon" onClick={() => setShowKey(!showKey)}>
                                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </Button>
                        </div>
                    </div>

                    <div className="grid grid-cols-3 gap-4 pt-2 border-t">
                        <div className="space-y-2">
                            <Label className="text-xs">Max RPM Limit</Label>
                            <Input 
                                type="number" 
                                min="1"
                                value={formData.rate_limit_rpm} 
                                onChange={e => setFormData({ ...formData, rate_limit_rpm: parseInt(e.target.value) || 60 })} 
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">Auto Retries</Label>
                            <Input 
                                type="number"
                                min="0" 
                                value={formData.max_retries} 
                                onChange={e => setFormData({ ...formData, max_retries: parseInt(e.target.value) || 0 })} 
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs">Retry Delay (ms)</Label>
                            <Input 
                                type="number" 
                                min="0" step="100"
                                value={formData.retry_delay_ms} 
                                onChange={e => setFormData({ ...formData, retry_delay_ms: parseInt(e.target.value) || 1000 })} 
                            />
                        </div>
                    </div>

                    {testResult && (
                        <div className={`p-3 text-sm rounded-md border ${testResult.success ? "bg-green-500/10 border-green-500/20 text-green-600" : "bg-red-500/10 border-red-500/20 text-red-600"}`}>
                            {testResult.success ? (
                                <div className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4" /> Connection successful</div>
                            ) : (
                                <div className="flex items-center gap-2"><AlertCircle className="w-4 h-4" /> {testResult.error}</div>
                            )}
                        </div>
                    )}
                </div>
                <DialogFooter className="flex justify-between items-center sm:justify-between">
                    <Button type="button" variant="outline" onClick={handleTest} disabled={testing}>
                        {testing ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : "Test Connection"}
                    </Button>
                    <Button type="button" onClick={handleSave}>Save Account</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ─── Task Config Dialog ────────────────────────────────────────────────────────
export function TaskConfigDialog({
    open,
    onClose,
    config,
    llmProviders,
    onSaveConfig,
    memorySettings,
    onUpdateMemorySettings,
    models,
    loadingModels,
    error,
    onFetchModels
}) {
    const [formData, setFormData] = useState({ provider_id: "", model_name: "", prompt_id: "" });
    const [chunkSize, setChunkSize] = useState("");
    const [chunkOverlap, setChunkOverlap] = useState("");
    const [availablePrompts, setAvailablePrompts] = useState([]);

    useEffect(() => {
        if (open && config) {
            setFormData({
                provider_id: config.provider_id || "",
                model_name: config.model_name || "",
                prompt_id: config.prompt_id || ""
            });
            if (config.task_type === "embedding" && memorySettings) {
                setChunkSize(memorySettings.chunk_size || 400);
                setChunkOverlap(memorySettings.chunk_overlap || 80);
            }
            if (config.provider_id && canFetchModels) {
                onFetchModels(config.id, config.provider_id);
            }
            
            if (config.task_type !== "embedding" && config.task_type !== "vision") {
                 getPrompts()
                   .then(res => setAvailablePrompts(res.data))
                   .catch(err => console.error("Failed to fetch prompts:", err));
            }
        }
    }, [open, config]);

    const handleProviderChange = (v) => {
        setFormData({ provider_id: v, model_name: "" });
        onFetchModels(config.id, v);
    };

    const handleSave = async () => {
        const payload = {
            provider_id: formData.provider_id,
            model_name: formData.model_name,
            prompt_id: formData.prompt_id || null
        };
        onSaveConfig(config.id, payload);
        
        if (config.task_type === "embedding" && onUpdateMemorySettings) {
            const newSize = parseInt(chunkSize);
            const newOverlap = parseInt(chunkOverlap);
            let p1, p2;
            if (newSize && newSize !== memorySettings.chunk_size) {
                 p1 = onUpdateMemorySettings("chunk_size", newSize);
            }
            if (newOverlap && newOverlap !== memorySettings.chunk_overlap) {
                 p2 = onUpdateMemorySettings("chunk_overlap", newOverlap);
            }
            if (p1) await p1;
            if (p2) await p2;
        }
        onClose();
    };

    if (!config) return null;
    const taskInfo = TASK_TYPE_LABELS[config.task_type] || { label: config.task_type };

    const selectedProviderMeta = formData.provider_id 
        ? PROVIDER_META.find(m => m.value === llmProviders.find(p => p.id === formData.provider_id)?.provider)
        : null;
    const canFetchModels = selectedProviderMeta?.hasModelFetch;

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[450px]">
                <DialogHeader>
                    <DialogTitle>Assign {taskInfo.label}</DialogTitle>
                    <DialogDescription>Assign a provider account and model for this task.</DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                     <div className="space-y-2">
                          <Label>Provider Account</Label>
                          <Select value={formData.provider_id} onValueChange={handleProviderChange}>
                              <SelectTrigger><SelectValue placeholder="Select an account" /></SelectTrigger>
                              <SelectContent>
                                  {llmProviders.map((opt) => (
                                     <SelectItem key={opt.id} value={opt.id}>{opt.name} ({opt.provider})</SelectItem>
                                  ))}
                              </SelectContent>
                          </Select>
                     </div>

                     {formData.provider_id && canFetchModels && (
                         <div className="space-y-2">
                             <Label>Model</Label>
                             <ModelCombobox 
                                 value={formData.model_name}
                                 onChange={(v) => setFormData({ ...formData, model_name: v })}
                                 models={models}
                                 loading={loadingModels}
                                 error={error}
                                 onFetch={() => onFetchModels(config.id, formData.provider_id)}
                                 canFetch={canFetchModels}
                             />
                         </div>
                     )}
                     {formData.provider_id && !canFetchModels && (
                         <div className="space-y-2">
                             <Label>Model Name</Label>
                             <Input 
                                 value={formData.model_name}
                                 onChange={(e) => setFormData({ ...formData, model_name: e.target.value })}
                                 placeholder="e.g. gpt-4o"
                             />
                         </div>
                     )}
                     {config.task_type !== 'embedding' && config.task_type !== 'vision' && (
                         <div className="space-y-2 mt-4 pt-4 border-t">
                             <Label>Linked Prompt Template</Label>
                             <Select value={formData.prompt_id || "default"} onValueChange={(v) => setFormData(f => ({ ...f, prompt_id: v === "default" ? "" : v }))}>
                                 <SelectTrigger><SelectValue placeholder="Select a prompt" /></SelectTrigger>
                                 <SelectContent>
                                     <SelectItem value="default">-- Default Prompt --</SelectItem>
                                     {availablePrompts.map(p => (
                                         <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                     ))}
                                 </SelectContent>
                             </Select>
                             <p className="text-xs text-muted-foreground">Override the default system prompt for this task using a template from the Prompt Manager.</p>
                         </div>
                     )}

                     {config.task_type === 'embedding' && (
                         <div className="pt-4 mt-2 border-t space-y-4">
                             <div className="flex items-center gap-2 mb-2">
                                 <h4 className="text-sm font-semibold flex items-center gap-1.5"><Scissors className="w-4 h-4 text-purple-500"/> Chunking Strategy</h4>
                             </div>
                             <div className="grid grid-cols-2 gap-4">
                                  <div className="space-y-2">
                                      <Label className="text-xs">Chunk Size (tokens)</Label>
                                      <Input type="number" value={chunkSize} onChange={(e) => setChunkSize(e.target.value)} />
                                  </div>
                                  <div className="space-y-2">
                                      <Label className="text-xs">Chunk Overlap</Label>
                                      <Input type="number" value={chunkOverlap} onChange={(e) => setChunkOverlap(e.target.value)} />
                                  </div>
                             </div>
                         </div>
                     )}
                </div>

                <DialogFooter>
                     <Button variant="outline" onClick={onClose}>Cancel</Button>
                     <Button onClick={handleSave} disabled={!formData.provider_id || !formData.model_name}>Save Assignation</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ─── Main Component (Credentials Only) ───────────────────────────────────────
export function LLMProviderSettings({
    llmProviders,
    onSaveProvider,
    onDeleteProvider,
}) {
    // Provider Dialog State
    const [providerDialogOpen, setProviderDialogOpen] = useState(false);
    const [editingProvider, setEditingProvider] = useState(null);

    return (
        <div className="space-y-8 max-w-4xl">
            {/* ─── Provider Accounts ─── */}
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>LLM Provider Accounts</CardTitle>
                            <CardDescription>
                                Set up reusable credentials to assign to engine tasks.
                            </CardDescription>
                        </div>
                        <Button onClick={() => { setEditingProvider(null); setProviderDialogOpen(true); }}>
                            <Plus className="w-4 h-4 mr-2" />
                            Add Account
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-3">
                    {llmProviders.length === 0 ? (
                        <div className="text-center p-6 border border-dashed rounded-lg text-muted-foreground">
                            No provider accounts configured yet.
                        </div>
                    ) : (
                        llmProviders.map(provider => (
                            <div key={provider.id} className="flex items-center justify-between p-4 border rounded-lg bg-card/50">
                                <div>
                                    <div className="font-semibold flex items-center gap-2">
                                        {provider.name}
                                        <Badge variant="outline" className="text-xs uppercase">{provider.provider}</Badge>
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-1">
                                        Base URL: {provider.api_base_url || "Default"}
                                    </div>
                                    {provider.api_key_preview && (
                                        <div className="text-xs text-muted-foreground">
                                            Key: {provider.api_key_preview}
                                        </div>
                                    )}
                                </div>
                                <div className="flex items-center gap-2">
                                    <Button variant="ghost" size="icon" onClick={() => { setEditingProvider(provider); setProviderDialogOpen(true); }}>
                                        <Edit2 className="w-4 h-4 text-muted-foreground" />
                                    </Button>
                                    <Button variant="ghost" size="icon" onClick={() => onDeleteProvider(provider.id)}>
                                        <Trash2 className="w-4 h-4 text-red-400" />
                                    </Button>
                                </div>
                            </div>
                        ))
                    )}
                </CardContent>
            </Card>

            <ProviderDialog 
                open={providerDialogOpen} 
                onClose={() => setProviderDialogOpen(false)} 
                onSave={onSaveProvider}
                existingProvider={editingProvider}
            />
        </div>
    );
}


