import React, { useState, useCallback } from "react";
import {
    Clock, Play, ShieldAlert, Zap, GraduationCap, Brain,
    Layers, Scissors, FileText, Eye, AlertCircle, CheckCircle2,
    Edit2, Cpu, Sparkles, BarChart3, Image as ImageIcon, ChevronDown, Settings,
    Plus, X
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import api, { triggerMemoryGeneration, triggerIntelligenceCheck, fetchProviderModels } from "@/lib/api";
import { useEffect } from "react";

// â”€â”€â”€ Threshold Overrides Table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
// Shows only entity types that have an active override.
// Users pick from a dropdown to add new overrides and can remove them.
function ThresholdOverridesTable({ entityTypes, overrideKey, globalFallback }) {
    const [overrides, setOverrides] = useState({}); // { entityName: value }
    const [loadingMap, setLoadingMap] = useState({});
    const [initialLoading, setInitialLoading] = useState(true);

    // Load existing overrides for all entity types on mount
    useEffect(() => {
        if (!entityTypes?.length) { setInitialLoading(false); return; }
        let cancelled = false;
        (async () => {
            const result = {};
            await Promise.all(entityTypes.map(async (et) => {
                try {
                    const res = await api.get(`/memory/entity-type-config/${et.name}`);
                    const val = res.data[overrideKey];
                    if (val != null) result[et.name] = val;
                } catch { /* entity config may not exist yet */ }
            }));
            if (!cancelled) { setOverrides(result); setInitialLoading(false); }
        })();
        return () => { cancelled = true; };
    }, [entityTypes, overrideKey]);

    const activeNames = Object.keys(overrides);
    const availableToAdd = (entityTypes || []).filter(et => !activeNames.includes(et.name));

    const handleAdd = async (entityName) => {
        // Set the override to the global fallback initially
        setLoadingMap(p => ({ ...p, [entityName]: true }));
        try {
            await api.patch(`/memory/entity-type-config/${entityName}`, {
                [overrideKey]: globalFallback
            });
            setOverrides(p => ({ ...p, [entityName]: globalFallback }));
            toast.success(`Override added for ${entityName}`);
        } catch {
            toast.error("Failed to add override");
        } finally {
            setLoadingMap(p => ({ ...p, [entityName]: false }));
        }
    };

    const handleChange = (entityName, val) => {
        setOverrides(p => ({ ...p, [entityName]: val }));
    };

    const handleSave = async (entityName) => {
        const val = overrides[entityName];
        setLoadingMap(p => ({ ...p, [entityName]: true }));
        try {
            await api.patch(`/memory/entity-type-config/${entityName}`, {
                [overrideKey]: val === "" ? null : parseInt(val, 10)
            });
            toast.success(`${entityName} threshold updated`);
        } catch {
            toast.error("Failed to update threshold");
        } finally {
            setLoadingMap(p => ({ ...p, [entityName]: false }));
        }
    };

    const handleRemove = async (entityName) => {
        setLoadingMap(p => ({ ...p, [entityName]: true }));
        try {
            await api.patch(`/memory/entity-type-config/${entityName}`, {
                [overrideKey]: null
            });
            setOverrides(p => {
                const next = { ...p };
                delete next[entityName];
                return next;
            });
            toast.success(`Override removed for ${entityName}`);
        } catch {
            toast.error("Failed to remove override");
        } finally {
            setLoadingMap(p => ({ ...p, [entityName]: false }));
        }
    };

    const getEntityType = (name) => entityTypes?.find(et => et.name === name);

    if (initialLoading) {
        return <p className="text-xs text-muted-foreground py-2">Loading overridesâ€¦</p>;
    }

    return (
        <div className="space-y-3">
            {activeNames.length > 0 && (
                <div className="border border-border rounded-md overflow-hidden bg-background">
                    <table className="w-full text-left">
                        <thead className="bg-muted text-xs text-muted-foreground uppercase">
                            <tr>
                                <th className="py-2 pl-4 font-medium">Entity Type</th>
                                <th className="py-2 pr-4 font-medium text-right">Threshold</th>
                                <th className="py-2 pr-3 font-medium text-right w-10"></th>
                            </tr>
                        </thead>
                        <tbody>
                            {activeNames.map(name => {
                                const et = getEntityType(name);
                                return (
                                    <tr key={name} className="border-t border-border text-sm">
                                        <td className="py-2.5 pl-4">
                                            <div className="flex items-center gap-2 font-medium">
                                                <span className="text-lg leading-none">{et?.icon || "ðŸ“¦"}</span>
                                                <span className="capitalize">{name}</span>
                                            </div>
                                        </td>
                                        <td className="py-2.5 pr-4 text-right">
                                            <Input
                                                type="number"
                                                min={1}
                                                className="w-20 h-7 text-right text-xs ml-auto"
                                                value={overrides[name] ?? ""}
                                                onChange={e => handleChange(name, e.target.value)}
                                                onBlur={() => handleSave(name)}
                                                disabled={loadingMap[name]}
                                            />
                                        </td>
                                        <td className="py-2.5 pr-3 text-right">
                                            <button
                                                onClick={() => handleRemove(name)}
                                                disabled={loadingMap[name]}
                                                className="text-muted-foreground hover:text-red-400 transition-colors p-1 rounded"
                                                title="Remove override"
                                            >
                                                <X className="w-3.5 h-3.5" />
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
            {activeNames.length === 0 && (
                <p className="text-xs text-muted-foreground italic py-1">
                    No overrides set â€” all entity types use the global default ({globalFallback}).
                </p>
            )}
            {availableToAdd.length > 0 && (
                <div className="flex items-center gap-2">
                    <select
                        id={`add-override-${overrideKey}`}
                        className="h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground"
                        defaultValue=""
                        onChange={(e) => {
                            if (e.target.value) { handleAdd(e.target.value); e.target.value = ""; }
                        }}
                    >
                        <option value="" disabled>Select entity typeâ€¦</option>
                        {availableToAdd.map(et => (
                            <option key={et.id} value={et.name}>{et.name}</option>
                        ))}
                    </select>
                    <span className="text-[10px] text-muted-foreground">Add entity-specific override</span>
                </div>
            )}
        </div>
    );
}

// ─── Auto-Approve Toggle Table ──────────────────────────────────────────────
// Shows all entity types with a boolean switch for intelligence_auto_approve
// or knowledge_auto_promote per entity.
// readKey: DB column name (lowercase), writeKey: Pydantic field name (may differ in casing)
function AutoApproveTable({ entityTypes, readKey, writeKey, label }) {
    const [states, setStates] = useState({}); // { entityName: bool }
    const [loadingMap, setLoadingMap] = useState({});
    const [initialLoading, setInitialLoading] = useState(true);

    useEffect(() => {
        if (!entityTypes?.length) { setInitialLoading(false); return; }
        let cancelled = false;
        (async () => {
            const result = {};
            await Promise.all(entityTypes.map(async (et) => {
                try {
                    const res = await api.get(`/memory/entity-type-config/${et.name}`);
                    result[et.name] = res.data[readKey] ?? false;
                } catch { result[et.name] = false; }
            }));
            if (!cancelled) { setStates(result); setInitialLoading(false); }
        })();
        return () => { cancelled = true; };
    }, [entityTypes, readKey]);

    const handleToggle = async (entityName, value) => {
        setLoadingMap(p => ({ ...p, [entityName]: true }));
        setStates(p => ({ ...p, [entityName]: value }));
        try {
            await api.patch(`/memory/entity-type-config/${entityName}`, { [writeKey]: value });
            toast.success(`${entityName}: ${label} ${value ? "enabled" : "disabled"}`);
        } catch {
            setStates(p => ({ ...p, [entityName]: !value }));
            toast.error("Failed to update setting");
        } finally {
            setLoadingMap(p => ({ ...p, [entityName]: false }));
        }
    };

    if (initialLoading) return <p className="text-xs text-muted-foreground py-2">Loading…</p>;
    if (!entityTypes?.length) return <p className="text-xs text-muted-foreground py-2 italic">No entity types configured.</p>;

    return (
        <div className="border border-border rounded-md overflow-hidden bg-background">
            <table className="w-full text-left">
                <thead className="bg-muted text-xs text-muted-foreground uppercase">
                    <tr>
                        <th className="py-2 pl-4 font-medium">Entity Type</th>
                        <th className="py-2 pr-4 font-medium text-right">{label}</th>
                    </tr>
                </thead>
                <tbody>
                    {(entityTypes || []).map(et => (
                        <tr key={et.name} className="border-t border-border text-sm">
                            <td className="py-2.5 pl-4">
                                <div className="flex items-center gap-2 font-medium">
                                    <span className="text-lg leading-none">{et.icon || "📦"}</span>
                                    <span className="capitalize">{et.name}</span>
                                </div>
                            </td>
                            <td className="py-2.5 pr-4 text-right">
                                <Switch
                                    checked={!!states[et.name]}
                                    onCheckedChange={(v) => handleToggle(et.name, v)}
                                    disabled={loadingMap[et.name]}
                                />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

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
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
} from "@/components/ui/tabs";

import {
    TASK_TYPE_LABELS,
} from "@/components/settings/LLMProviderSettings";
import { InlineTaskConfigAccordion } from "./InlineTaskConfigAccordion";
import { DraggablePipeline } from "./DraggablePipeline";
import { OutboundWebhooksSettings } from "./OutboundWebhooksSettings";

// â”€â”€â”€ Prompt Structure Preview â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function PromptStructurePreview({ sections }) {
    const [open, setOpen] = useState(false);
    return (
        <Card className="bg-zinc-950/60 border-zinc-800">
            <button
                type="button"
                className="w-full flex items-center justify-between px-4 py-3 text-left"
                onClick={() => setOpen(!open)}
            >
                <div className="flex items-center gap-2">
                    <Eye className="w-4 h-4 text-blue-400" />
                    <span className="text-xs font-semibold text-zinc-300">LLM Prompt Structure Preview</span>
                </div>
                <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
            {open && (
                <CardContent className="pt-0 pb-4 px-4">
                    <div className="rounded-md bg-zinc-900 border border-zinc-800 p-3 font-mono text-[11px] leading-relaxed space-y-2">
                        {sections.map((s, i) => (
                            <div key={i} className={`${s.conditional ? 'opacity-70' : ''}`}>
                                <span className="text-zinc-500">--- </span>
                                <span className={`font-semibold ${s.color || 'text-zinc-300'}`}>{s.label}</span>
                                <span className="text-zinc-500"> ---</span>
                                {s.count !== undefined && (
                                    <span className="ml-2 text-zinc-600">({s.count} items)</span>
                                )}
                                {s.conditional && (
                                    <span className="ml-2 text-zinc-700 italic">if count &gt; 0</span>
                                )}
                                <div className="text-zinc-600 text-[10px] ml-4 mt-0.5">{s.description}</div>
                            </div>
                        ))}
                    </div>
                    <p className="text-[10px] text-zinc-600 mt-2">
                        Sections are injected top-to-bottom. The LLM weights later sections more heavily (recency bias).
                    </p>
                </CardContent>
            )}
        </Card>
    );
}

// â”€â”€â”€ Interactions Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function RawInteractionsTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const pipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "interactions").sort((a,b) => a.execution_order - b.execution_order);

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Zap className="w-5 h-5 text-amber-500" />
                    Interactions
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Controls how Interactions are received, parsed, and embedded before they become structured memories.
                </p>
            </div>

            {/* Interactions Pipeline Assignment */}
            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3 border-b">
                    <CardTitle className="text-sm">Interactions Pipeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                    <DraggablePipeline 
                        title=""
                        pipelineStage="interactions"
                        pipelineConfigs={pipelineNodes}
                        onReorder={(arr) => onReorderPipeline("interactions", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                    />
                </CardContent>
            </Card>



            {/* Ingestion Throughput */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Zap className="w-5 h-5 text-amber-500" />
                        <CardTitle className="text-lg">Ingestion Throughput</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Configure inbound rate limits and parallel processing queues.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Zap className="w-4 h-4 text-amber-500" />
                            API Rate Limiting
                        </h4>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label>Enable Rate Limiting</Label>
                                <p className="text-[10px] text-muted-foreground">
                                    Limit inbound API requests per agent.
                                </p>
                            </div>
                            <Switch
                                checked={settings.rate_limit_enabled}
                                onCheckedChange={(v) => onUpdateSettings("rate_limit_enabled", v)}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Requests per Minute (RPM)</Label>
                            <Input
                                type="number"
                                value={settings.rate_limit_per_minute || 60}
                                onChange={(e) =>
                                    onUpdateSettings(
                                        "rate_limit_per_minute",
                                        parseInt(e.target.value)
                                    )
                                }
                                disabled={!settings.rate_limit_enabled}
                            />
                        </div>
                    </div>

                </CardContent>
            </Card>

            {/* Outbound Webhooks */}
            <OutboundWebhooksSettings />
        </div>
    );
}

// â”€â”€â”€ Memories Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function MemoryGenerationTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const [isTriggering, setIsTriggering] = useState(false);
    const pipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "memories").sort((a,b) => a.execution_order - b.execution_order);

    const handleRunNow = async () => {
        setIsTriggering(true);
        try {
            await triggerMemoryGeneration(true);
            toast.success("Generation task scheduled in background. Check docker logs.");
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Failed to trigger task");
        } finally {
            setIsTriggering(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Brain className="w-5 h-5 text-purple-500" />
                    Memories
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Transforms Interactions into structured daily memories via NER and LLM summarization.
                </p>
            </div>

            {/* Unified Memories Configuration */}
            <Card>
                <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <Settings className="w-5 h-5 text-blue-500" />
                            <CardTitle className="text-lg">Memories Configuration</CardTitle>
                        </div>
                        <CardDescription className="text-xs mt-1.5">
                            Schedule, prior context, and processing throughput for memory generation.
                        </CardDescription>
                    </div>
                    <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={handleRunNow}
                        disabled={isTriggering}
                    >
                        <Play className="w-3.5 h-3.5" />
                        Run Now
                    </Button>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Â§ Schedule */}
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Clock className="w-4 h-4 text-blue-500" />
                            Schedule
                        </h4>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Daily Run Time (UTC)</Label>
                            <Input
                                type="time"
                                value={settings.memory_generation_time || "02:00"}
                                onChange={(e) =>
                                    onUpdateSettings("memory_generation_time", e.target.value)
                                }
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Time of day to process pending interactions into daily memory records.
                            </p>
                        </div>
                    </div>

                    {/* Â§ Prior Context */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Layers className="w-4 h-4 text-purple-500" />
                            Prior Context
                        </h4>
                        <p className="text-[10px] text-muted-foreground -mt-2">
                            Controls how many previous memories are injected as context when generating new memories.
                            Higher counts provide more continuity but increase token usage.
                        </p>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Chronological Memories</Label>
                                <Input
                                    type="number"
                                    min={0}
                                    max={10}
                                    value={settings.prior_context_chrono_count !== undefined ? settings.prior_context_chrono_count : 2}
                                    onChange={(e) =>
                                        onUpdateSettings("prior_context_chrono_count", parseInt(e.target.value) || 0)
                                    }
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    Most recent memories by date (ordered DESC).
                                </p>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Semantic Memories</Label>
                                <Input
                                    type="number"
                                    min={0}
                                    max={10}
                                    value={settings.prior_context_semantic_count !== undefined ? settings.prior_context_semantic_count : 2}
                                    onChange={(e) =>
                                        onUpdateSettings("prior_context_semantic_count", parseInt(e.target.value) || 0)
                                    }
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    Most similar memories via vector search (pgvector cosine).
                                </p>
                            </div>
                        </div>
                        <p className="text-[10px] text-muted-foreground border-t pt-2">
                            Combined unique memories are injected under "Prior Context" in the LLM prompt.
                            Set both to 0 to disable prior context entirely. Duplicates are automatically deduplicated.
                        </p>
                    </div>

                    {/* Â§ Processing */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Cpu className="w-4 h-4 text-indigo-500" />
                            Processing
                        </h4>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Max Retries</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    max="10"
                                    value={settings.memory_queue_retries !== undefined ? settings.memory_queue_retries : 3}
                                    onChange={(e) =>
                                        onUpdateSettings("memory_queue_retries", parseInt(e.target.value))
                                    }
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Retry Delay (ms)</Label>
                                <Input
                                    type="number"
                                    min="0"
                                    step="500"
                                    value={settings.memory_queue_retry_delay !== undefined ? settings.memory_queue_retry_delay : 2000}
                                    onChange={(e) =>
                                        onUpdateSettings("memory_queue_retry_delay", parseInt(e.target.value))
                                    }
                                />
                            </div>
                        </div>
                        <p className="text-[10px] text-muted-foreground">
                            BullMQ will exponentially back off using the base delay specified above on failure.
                        </p>
                    </div>
                </CardContent>
            </Card>

            <PromptStructurePreview sections={[
                { label: "Entity Metadata", color: "text-zinc-400", description: "Entity type, ID, date, interaction count" },
                { label: "Prior Context (established facts, do NOT repeat)", color: "text-purple-400", count: (settings.prior_context_chrono_count || 2) + (settings.prior_context_semantic_count || 2), conditional: true, description: "Chronological + semantic prior memories for this entity" },
                { label: "Raw Interactions", color: "text-amber-400", description: "Today's raw interaction content to process" },
                { label: "Extracted Signals", color: "text-emerald-400", description: "NER entities, intents, relationships from extraction step" },
            ]} />

            {/* Memories Pipeline */}
            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3 border-b">
                    <CardTitle className="text-sm">Memories Pipeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                    <DraggablePipeline 
                        title=""
                        pipelineStage="memories"
                        pipelineConfigs={pipelineNodes}
                        onReorder={(arr) => onReorderPipeline("memories", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                        renderNodeExtras={(config) => {
                            if (config.task_type === "embedding") {
                                return (
                                    <div className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="space-y-2">
                                                <Label className="text-xs font-mono">Chunk Size (tokens)</Label>
                                                <Input
                                                    type="number"
                                                    min={100}
                                                    max={2000}
                                                    value={settings.chunk_size || 400}
                                                    onChange={(e) =>
                                                        onUpdateSettings("chunk_size", parseInt(e.target.value))
                                                    }
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-xs font-mono">Chunk Overlap (tokens)</Label>
                                                <Input
                                                    type="number"
                                                    min={0}
                                                    max={500}
                                                    value={settings.chunk_overlap || 80}
                                                    onChange={(e) =>
                                                        onUpdateSettings("chunk_overlap", parseInt(e.target.value))
                                                    }
                                                />
                                            </div>
                                        </div>
                                        <p className="text-[10px] text-muted-foreground">
                                            Controls how interaction text is split before embedding. larger chunks = more context, smaller = finer search.
                                        </p>
                                    </div>
                                );
                            }
                            return null;
                        }}
                    />
                </CardContent>
            </Card>
        </div>
    );
}


// â”€â”€â”€ Intelligence Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function IntelligenceTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline, entityTypes }) {
    const privatePipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "intelligence").sort((a,b) => a.execution_order - b.execution_order);
    const [isTriggering, setIsTriggering] = useState(false);

    const handleRunNow = async () => {
        setIsTriggering(true);
        try {
            await triggerIntelligenceCheck();
            toast.success("Intelligence extraction check triggered. Entities at threshold will be queued.");
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Failed to trigger intelligence check");
        } finally {
            setIsTriggering(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Brain className="w-5 h-5 text-purple-500" />
                    Intelligence Pipeline
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Extracts high-level intelligence and semantic insights from memory records.
                </p>
            </div>

            {/* Unified Intelligence Configuration */}
            <Card>
                <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <Settings className="w-5 h-5 text-purple-500" />
                            <CardTitle className="text-lg">Intelligence Configuration</CardTitle>
                        </div>
                        <CardDescription className="text-xs mt-1.5">
                            Prior context injection and mining trigger thresholds.
                        </CardDescription>
                    </div>
                    <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={handleRunNow}
                        disabled={isTriggering}
                    >
                        <Play className="w-3.5 h-3.5" />
                        Run Now
                    </Button>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Â§ Prior Context */}
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Layers className="w-4 h-4 text-purple-500" />
                            Prior Context
                        </h4>
                        <p className="text-[10px] text-muted-foreground -mt-2">
                            Existing intelligence items injected during generation so the LLM avoids creating duplicates.
                        </p>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Chronological</Label>
                                <Input
                                    type="number"
                                    min={0}
                                    max={10}
                                    value={settings.prior_intelligence_chrono_count !== undefined ? settings.prior_intelligence_chrono_count : 3}
                                    onChange={(e) =>
                                        onUpdateSettings("prior_intelligence_chrono_count", parseInt(e.target.value) || 0)
                                    }
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    Most recent intelligence by date for this entity.
                                </p>
                            </div>
                            <div className="space-y-2">
                                <Label className="text-xs font-mono">Semantic</Label>
                                <Input
                                    type="number"
                                    min={0}
                                    max={10}
                                    value={settings.prior_intelligence_semantic_count !== undefined ? settings.prior_intelligence_semantic_count : 2}
                                    onChange={(e) =>
                                        onUpdateSettings("prior_intelligence_semantic_count", parseInt(e.target.value) || 0)
                                    }
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    Most similar intelligence via vector search for this entity.
                                </p>
                            </div>
                        </div>
                        <div className="space-y-2 border-t pt-3">
                            <Label className="text-xs font-mono">Knowledge Cross-Reference (Semantic)</Label>
                            <Input
                                type="number"
                                min={0}
                                max={10}
                                value={settings.prior_knowledge_in_intelligence_count !== undefined ? settings.prior_knowledge_in_intelligence_count : 2}
                                onChange={(e) =>
                                    onUpdateSettings("prior_knowledge_in_intelligence_count", parseInt(e.target.value) || 0)
                                }
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Global knowledge items (PII-scrubbed) injected as organizational context.
                                Helps the LLM generate novel intelligence that builds on â€” rather than restates â€” established patterns.
                            </p>
                        </div>
                        <p className="text-[10px] text-muted-foreground border-t pt-2">
                            All prior context is injected as labeled sections in the LLM prompt to prevent redundant generation.
                        </p>
                    </div>

                    {/* Â§ Mining Triggers */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Brain className="w-4 h-4 text-purple-400" />
                            Mining Triggers
                        </h4>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Global Default Threshold (N memories)</Label>
                            <Input
                                type="number"
                                min={2}
                                value={settings.intelligence_extraction_threshold || 10}
                                onChange={(e) =>
                                    onUpdateSettings("intelligence_extraction_threshold", parseInt(e.target.value))
                                }
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Generate an intelligence item after this many uncompacted memories accumulate.
                            </p>
                        </div>
                        <div className="space-y-3 pt-2">
                            <Label className="text-xs font-mono">Entity-Specific Overrides</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Different entities accumulate interactions at different rates (e.g., an API token might need 1,000 interactions before compaction, while a Contact might need only 5).
                            </p>
                            <ThresholdOverridesTable
                                entityTypes={entityTypes}
                                overrideKey="intelligence_extraction_threshold"
                                globalFallback={settings.intelligence_extraction_threshold || 10}
                            />
                        </div>
                    </div>

                    {/* § Auto-Approve */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                            Auto-Approve
                        </h4>
                        <p className="text-[10px] text-muted-foreground -mt-2">
                            When enabled, newly generated intelligence items are automatically set to <span className="font-mono">confirmed</span> instead of <span className="font-mono">draft</span>. Only enable for entity types where you trust the pipeline output.
                        </p>
                        <AutoApproveTable
                            entityTypes={entityTypes}
                            readKey="intelligence_auto_approve"
                            writeKey="Intelligence_auto_approve"
                            label="Auto-Approve"
                        />
                    </div>
                </CardContent>
            </Card>

            <PromptStructurePreview sections={[
                { label: "Entity Metadata", color: "text-zinc-400", description: "Entity type and ID" },
                { label: "Established Knowledge (organizational patterns already known)", color: "text-indigo-400", count: settings.prior_knowledge_in_intelligence_count !== undefined ? settings.prior_knowledge_in_intelligence_count : 2, conditional: true, description: "Global PII-scrubbed knowledge items via semantic search" },
                { label: "Existing Intelligence for this entity (do NOT duplicate)", color: "text-purple-400", count: (settings.prior_intelligence_chrono_count || 3) + (settings.prior_intelligence_semantic_count || 2), conditional: true, description: "Chronological + semantic prior intelligence for this entity" },
                { label: "Memory Summaries to Analyze", color: "text-amber-400", description: "Uncompacted memory records feeding this intelligence generation" },
            ]} />

            {/* Intelligence Pipeline */}
            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3 border-b">
                    <CardTitle className="text-sm">Intelligence Pipeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                    <DraggablePipeline 
                        title=""
                        pipelineStage="intelligence"
                        pipelineConfigs={privatePipelineNodes}
                        onReorder={(arr) => onReorderPipeline("intelligence", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                    />
                </CardContent>
            </Card>
        </div>
    );
}

// â”€â”€â”€ Knowledge Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function KnowledgeTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline, entityTypes }) {
    const publicPipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "knowledge").sort((a,b) => a.execution_order - b.execution_order);

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <GraduationCap className="w-5 h-5 text-indigo-500" />
                    Knowledge Generation
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Generates agnostic, PII-scrubbed, reusable Knowledge items.
                </p>
            </div>

            {/* Knowledge Configuration — flat, no sub-section headers */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Settings className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Knowledge Configuration</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Mining triggers and prior context for deduplication.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Knowledge Threshold */}
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Knowledge Threshold (N intelligence items)</Label>
                        <Input
                            type="number"
                            min={0}
                            value={settings.knowledge_threshold || 5}
                            onChange={(e) =>
                                onUpdateSettings("knowledge_threshold", parseInt(e.target.value) || 0)
                            }
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Generate a knowledge item after this many confirmed intelligence items accumulate. Set to 0 to disable auto-extraction.
                        </p>
                    </div>

                    {/* Entity-Specific Overrides */}
                    <div className="space-y-3 border-t pt-4">
                        <Label className="text-xs font-mono">Entity-Specific Overrides</Label>
                        <p className="text-[10px] text-muted-foreground">
                            Override the global threshold per entity type.
                        </p>
                        <ThresholdOverridesTable
                            entityTypes={entityTypes}
                            overrideKey="knowledge_extraction_threshold"
                            globalFallback={settings.knowledge_threshold || 5}
                        />
                    </div>

                    {/* Prior Context */}
                    <div className="space-y-2 border-t pt-4">
                        <Label className="text-xs font-mono">Prior Context — Semantic Matches</Label>
                        <Input
                            type="number"
                            min={0}
                            max={10}
                            value={settings.prior_knowledge_semantic_count !== undefined ? settings.prior_knowledge_semantic_count : 3}
                            onChange={(e) =>
                                onUpdateSettings("prior_knowledge_semantic_count", parseInt(e.target.value) || 0)
                            }
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Existing knowledge items injected via pgvector cosine search to prevent duplicates. Set to 0 to disable.
                        </p>
                    </div>
                </CardContent>
            </Card>

            <PromptStructurePreview sections={[
                { label: "Existing Knowledge (do NOT duplicate or repeat these)", color: "text-indigo-400", count: settings.prior_knowledge_semantic_count !== undefined ? settings.prior_knowledge_semantic_count : 3, conditional: true, description: "Semantically similar existing knowledge items for deduplication" },
                { label: "Intelligence Items to Synthesize", color: "text-purple-400", description: "PII-scrubbed intelligence items being synthesized into reusable knowledge" },
            ]} />

            {/* Knowledge Pipeline */}
            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3 border-b">
                    <CardTitle className="text-sm">Knowledge Pipeline</CardTitle>
                </CardHeader>
                <CardContent className="pt-4">
                    <DraggablePipeline
                        title=""
                        pipelineStage="knowledge"
                        pipelineConfigs={publicPipelineNodes}
                        onReorder={(arr) => onReorderPipeline("knowledge", arr)}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
                        onAddConfig={onAddConfig}
                        modelLists={modelLists}
                        fetchingModels={fetchingModels}
                        fetchErrors={fetchErrors}
                        onFetchModels={onFetchModels}
                    />
                </CardContent>
            </Card>

            {/* Queue Performance — consolidated across all pipeline stages */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Queue Performance</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        BullMQ worker concurrency per pipeline. Reduce if hitting LLM rate limits.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Interactions</Label>
                            <Input
                                type="number"
                                min="1"
                                max="50"
                                value={settings.interactions_queue_concurrency || 5}
                                onChange={(e) =>
                                    onUpdateSettings("interactions_queue_concurrency", parseInt(e.target.value) || 5)
                                }
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Memories</Label>
                            <Input
                                type="number"
                                min="1"
                                max="50"
                                value={settings.memory_queue_concurrency || 1}
                                onChange={(e) =>
                                    onUpdateSettings("memory_queue_concurrency", parseInt(e.target.value) || 1)
                                }
                            />
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Knowledge</Label>
                            <Input
                                type="number"
                                min="1"
                                max="50"
                                value={settings.knowledge_queue_concurrency || 1}
                                onChange={(e) =>
                                    onUpdateSettings("knowledge_queue_concurrency", parseInt(e.target.value) || 1)
                                }
                            />
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

// â”€â”€â”€ Analytics Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function AnalyticsTab() {
    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <BarChart3 className="w-5 h-5 text-emerald-500" />
                    Analytics Pipeline
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    System analytics and metrics (Upcoming feature).
                </p>
            </div>
            <Card>
                <CardContent className="py-12 flex flex-col items-center justify-center text-center text-muted-foreground">
                    <BarChart3 className="w-12 h-12 mb-4 opacity-20" />
                    <p>Dashboard visualization components are under construction.</p>
                </CardContent>
            </Card>
        </div>
    );
}

// â”€â”€â”€ Main Component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export function MemorySettings({
    settings,
    llmConfigs,
    llmProviders,
    onUpdateSettings,
    onSaveConfig, onDeleteConfig, onAddConfig,
    onUpdateMemorySettings,
    activeTab = "raw_interactions",
    onTabChange,
    onReorderPipeline,
    entityTypes
}) {
    const [modelLists, setModelLists] = useState({});
    const [fetchingModels, setFetchingModels] = useState({});
    const [fetchErrors, setFetchErrors] = useState({});

    const handleFetchModels = useCallback(
        async (configId, providerId) => {
            if (!providerId) return;
            setFetchingModels((prev) => ({ ...prev, [configId]: true }));
            setFetchErrors((prev) => ({ ...prev, [configId]: null }));

            try {
                const selectedProvider = llmProviders.find((p) => p.id === providerId);
                if (!selectedProvider) throw new Error("Provider not found");

                const response = await fetchProviderModels({
                    provider: selectedProvider.provider,
                    provider_id: providerId,
                });
                setModelLists((prev) => ({
                    ...prev,
                    [configId]: response.data.models,
                }));
            } catch (err) {
                const detail = err.response?.data?.detail || "Failed to fetch models.";
                setFetchErrors((prev) => ({ ...prev, [configId]: detail }));
            } finally {
                setFetchingModels((prev) => ({ ...prev, [configId]: false }));
            }
        },
        [llmProviders]
    );

    // Shared props for all sub-tabs
    const tabProps = {
        settings,
        onUpdateSettings: onUpdateMemorySettings,
        llmConfigs,
        llmProviders,
        onSaveConfig, onDeleteConfig, onAddConfig,
        modelLists,
        fetchingModels,
        fetchErrors,
        onFetchModels: handleFetchModels,
        onReorderPipeline,
        entityTypes
    };

    return (
        <div className="max-w-4xl">
            <Tabs value={activeTab} onValueChange={onTabChange} className="w-full">
                <TabsList className="grid w-full grid-cols-5 mb-8">
                    <TabsTrigger value="raw_interactions" className="gap-2">
                        <Zap className="w-4 h-4" />
                        Interactions
                    </TabsTrigger>
                    <TabsTrigger value="memory_generation" className="gap-2">
                        <Brain className="w-4 h-4" />
                        Memories
                    </TabsTrigger>
                    <TabsTrigger value="intelligence" className="gap-2">
                        <Brain className="w-4 h-4 text-purple-500" />
                        Intelligence
                    </TabsTrigger>
                    <TabsTrigger value="knowledge" className="gap-2">
                        <GraduationCap className="w-4 h-4" />
                        Knowledge
                    </TabsTrigger>
                    <TabsTrigger value="analytics" className="gap-2">
                        <BarChart3 className="w-4 h-4" />
                        Analytics
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="raw_interactions">
                    <RawInteractionsTab {...tabProps} />
                </TabsContent>

                <TabsContent value="memory_generation">
                    <MemoryGenerationTab {...tabProps} />
                </TabsContent>

                <TabsContent value="intelligence">
                    <IntelligenceTab {...tabProps} />
                </TabsContent>

                <TabsContent value="knowledge">
                    <KnowledgeTab {...tabProps} />
                </TabsContent>

                <TabsContent value="analytics">
                    <AnalyticsTab />
                </TabsContent>
            </Tabs>

        </div>
    );
}


