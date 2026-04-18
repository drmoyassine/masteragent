import React, { useState, useEffect } from "react";
import { Brain, Sparkles, Clock, Eye, Layers, Cpu, EyeOff, AlertCircle, FileText, CheckCircle2, ChevronDown, ChevronUp, Save, RefreshCw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { getPrompts } from "@/lib/api";
import { TASK_TYPE_LABELS } from "@/components/settings/LLMProviderSettings";

function ModelCombobox({ value, onChange, models = [], loading, error, onFetch, canFetch }) {
    if (!canFetch) return null;
    return (
        <div className="space-y-2">
            <div className="flex items-center gap-2">
                <Select value={value} onValueChange={onChange}>
                    <SelectTrigger className="flex-1">
                        <SelectValue placeholder={loading ? "Loading models..." : "Select a model"} />
                    </SelectTrigger>
                    <SelectContent>
                        {models.map(m => (
                            <SelectItem key={m} value={m}>{m}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <Button variant="outline" size="icon" onClick={onFetch} disabled={loading} title="Refresh Models">
                    <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </Button>
            </div>
            {error && <p className="text-xs text-red-500">{error}</p>}
        </div>
    );
}

export function InlineTaskConfigAccordion({ 
    config, 
    llmProviders, 
    onSaveConfig,
    models,
    loadingModels,
    error,
    onFetchModels,
    titleOverride,
    descriptionOverride,
    isToggleable,
    toggleChecked,
    onToggleChange,
    children
}) {
    const [expanded, setExpanded] = useState(false);
    const [formData, setFormData] = useState({
        provider_id: config.provider_id || "",
        model_name: config.model_name || "",
        prompt_id: config.prompt_id || "",
        inline_system_prompt: config.inline_system_prompt || "",
        inline_schema: config.inline_schema || ""
    });
    const [availablePrompts, setAvailablePrompts] = useState([]);
    
    // Switch state based on if we are linked or not
    const [isLinked, setIsLinked] = useState(!!config.prompt_id);

    useEffect(() => {
        if (expanded && config.task_type !== "embedding" && config.task_type !== "pii_scrubbing") {
            getPrompts()
                .then(res => setAvailablePrompts(res.data))
                .catch(err => console.error("Failed to fetch prompts:", err));
        }
    }, [expanded, config.task_type]);

    const taskInfo = TASK_TYPE_LABELS[config.task_type] || {
        label: config.task_type,
        icon: Brain,
        color: "bg-gray-500",
    };
    const TaskIcon = taskInfo.icon;
    const assignedProvider = llmProviders.find((p) => p.id === (formData.provider_id || config.provider_id));
    const isConfigured = !!assignedProvider && !!(formData.model_name || config.model_name);
    
    const isGliner = assignedProvider?.provider === "gliner";
    const isZendata = assignedProvider?.provider === "zendata";

    // PII endpoints that are LLMs use prompting, custom endpoint services do not
    const hasPrompting = config.task_type !== "embedding" && !isZendata;
    const hidePromptInput = isGliner;
    
    const canFetchModels = assignedProvider ? ["openai", "anthropic", "gemini", "openrouter", "ollama"].includes(assignedProvider.provider) : false;

    const handleSave = () => {
        const payload = {
            provider_id: formData.provider_id,
            model_name: formData.model_name,
            prompt_id: isLinked ? (formData.prompt_id || null) : null,
            inline_system_prompt: isLinked ? null : formData.inline_system_prompt,
            inline_schema: isLinked ? null : formData.inline_schema
        };
        onSaveConfig(config.id, payload);
        setExpanded(false);
    };

    return (
        <Card className={`border-l-4 ${taskInfo.color} bg-card/50 overflow-hidden transition-all duration-300`}>
            {/* Header (Always Visible) */}
            <div 
                className="p-4 cursor-pointer hover:bg-white/5 transition flex items-start justify-between"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${taskInfo.color}`}>
                        <TaskIcon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-foreground">{titleOverride || taskInfo.label}</h3>
                        {descriptionOverride ? (
                            <p className="text-sm text-muted-foreground">{descriptionOverride}</p>
                        ) : (
                            <p className="text-sm text-muted-foreground">
                                {isConfigured
                                    ? `${assignedProvider.name} (${config.model_name || formData.model_name})`
                                    : "Not assigned"}
                            </p>
                        )}
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    {isToggleable && (
                        <div onClick={(e) => e.stopPropagation()} className="flex items-center">
                            <Switch 
                                checked={toggleChecked} 
                                onCheckedChange={onToggleChange} 
                            />
                        </div>
                    )}
                    {isConfigured ? (
                        <Badge variant="default" className="bg-green-500">
                            <CheckCircle2 className="w-3 h-3 mr-1" /> Ready
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="border-amber-500 text-amber-500">
                            <AlertCircle className="w-3 h-3 mr-1" /> Config Required
                        </Badge>
                    )}
                    <Button variant="ghost" size="sm" className="p-0 h-auto">
                        {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
                    </Button>
                </div>
            </div>

            {/* Collapsible Body */}
            {expanded && (
                <CardContent className="pt-0 pb-6 border-t mt-4 space-y-8 animate-in fade-in slide-in-from-top-4 duration-300">
                    
                    {children && (
                        <div className="pt-4 pb-2 border-b">
                            {children}
                        </div>
                    )}
                    
                    {/* Prompting Details Section */}
                    {hasPrompting && (
                        <div className="space-y-6 pt-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <h4 className="text-sm font-semibold flex items-center gap-2">
                                        <FileText className="w-4 h-4 text-primary" /> Prompt Configuration
                                    </h4>
                                    <p className="text-xs text-muted-foreground mt-1">Configure exactly how the AI processes text for this pipeline stage.</p>
                                </div>
                                <div className="flex items-center gap-2 bg-black/20 p-2 rounded-md">
                                    <Label className="text-xs font-semibold cursor-pointer">Link from Prompt Manager</Label>
                                    <Switch 
                                        checked={isLinked} 
                                        onCheckedChange={setIsLinked}
                                    />
                                </div>
                            </div>
                            
                            {isLinked ? (
                                <div className="space-y-3 bg-black/10 p-4 rounded-lg border border-white/5">
                                    <Label>Linked Prompt Template</Label>
                                    <Select 
                                        value={formData.prompt_id || "default"} 
                                        onValueChange={(v) => setFormData(f => ({ ...f, prompt_id: v === "default" ? "" : v }))}
                                    >
                                        <SelectTrigger><SelectValue placeholder="Select a prompt template" /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="default">-- Default Prompt --</SelectItem>
                                            {availablePrompts.map(p => (
                                                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <p className="text-xs text-muted-foreground mt-2 border-l-2 border-primary pl-2 py-1">
                                        The runtime pipeline will fetch the latest version of this prompt automatically. Variable injection is supported via the Prompt Manager logic.
                                    </p>
                                </div>
                            ) : (
                                <div className="space-y-6 bg-black/10 p-4 rounded-lg border border-white/5">
                                        {!hidePromptInput && (
                                            <div className="space-y-2">
                                                <Label className="flex justify-between">
                                                    <span>Task System Prompt</span>
                                                    <span className="text-[10px] text-muted-foreground">Supports Mustache `&#123;&#123; variables &#125;&#125;`</span>
                                                </Label>
                                                <Textarea 
                                                    value={formData.inline_system_prompt}
                                                    onChange={(e) => setFormData(f => ({ ...f, inline_system_prompt: e.target.value }))}
                                                    placeholder="You are an AI assistant..."
                                                    className="min-h-[120px] font-mono text-sm leading-relaxed"
                                                />
                                            </div>
                                        )}
                                        <div className="space-y-2">
                                        <Label className="flex justify-between">
                                            <span>{isGliner ? "GLiNER Extraction Labels (JSON Schema)" : "JSON Output Schema (Optional)"}</span>
                                            <span className="text-[10px] text-muted-foreground">Structured JSON / Schema Dict</span>
                                        </Label>
                                        <Textarea 
                                            value={formData.inline_schema}
                                            onChange={(e) => setFormData(f => ({ ...f, inline_schema: e.target.value }))}
                                            placeholder='{\n  "entities": ["Organization", "Person"]\n}'
                                            className="min-h-[100px] font-mono text-sm leading-relaxed text-green-400"
                                        />
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                    
                    {/* Execution Model Section */}
                    <div className="space-y-6 pt-4 border-t">
                        <div>
                            <h4 className="text-sm font-semibold flex items-center gap-2">
                                <Cpu className="w-4 h-4 text-primary" /> Execution Engine
                            </h4>
                            <p className="text-xs text-muted-foreground mt-1">Assign the LLM provider and compute model for this task.</p>
                        </div>
                        
                        <div className="grid grid-cols-2 gap-6 items-start">
                            <div className="space-y-2">
                                <Label>Provider Account</Label>
                                <Select 
                                    value={formData.provider_id} 
                                    onValueChange={(v) => {
                                        setFormData(f => ({ ...f, provider_id: v, model_name: "" }));
                                        onFetchModels(config.id, v);
                                    }}
                                >
                                    <SelectTrigger><SelectValue placeholder="Select an account" /></SelectTrigger>
                                    <SelectContent>
                                        {llmProviders.map((opt) => (
                                           <SelectItem key={opt.id} value={opt.id}>{opt.name} ({opt.provider})</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            {formData.provider_id ? (
                                <div className="space-y-2">
                                    <Label>
                                        {isZendata || isGliner ? "Endpoint API Path (Optional)" : "Compute Model"}
                                    </Label>
                                    {canFetchModels ? (
                                        <ModelCombobox 
                                            value={formData.model_name}
                                            onChange={(v) => setFormData({ ...formData, model_name: v })}
                                            models={models}
                                            loading={loadingModels}
                                            error={error}
                                            onFetch={() => onFetchModels(config.id, formData.provider_id)}
                                            canFetch={canFetchModels}
                                        />
                                    ) : (
                                        <Input 
                                           value={formData.model_name}
                                           onChange={(e) => setFormData(f => ({ ...f, model_name: e.target.value }))}
                                           placeholder={isZendata || isGliner ? "e.g. /custom-path or leave blank" : "e.g. gpt-4o or local model"}
                                        />
                                    )}
                                </div>
                            ) : (
                                <div className="space-y-2 flex flex-col justify-center opacity-50">
                                    <Label>Compute Model / Path</Label>
                                    <div className="h-10 rounded-md border border-dashed border-muted grid place-items-center text-xs text-muted-foreground">Select a provider first</div>
                                </div>
                            )}
                        </div>
                    </div>
                    
                    <div className="pt-4 flex justify-end gap-3 mt-4 border-t">
                        <Button variant="ghost" onClick={() => setExpanded(false)}>Cancel</Button>
                        <Button onClick={handleSave} className="bg-primary text-primary-foreground hover:bg-primary/90 gap-2">
                            <Save className="w-4 h-4" /> Save Configuration
                        </Button>
                    </div>

                </CardContent>
            )}
        </Card>
    );
}
