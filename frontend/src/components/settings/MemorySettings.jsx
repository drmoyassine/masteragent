import React, { useState, useCallback } from "react";
import {
    Clock, Play, ShieldAlert, Shield, Zap, GraduationCap, Brain,
    Layers, Scissors, FileText, Eye, AlertCircle, CheckCircle2,
    Edit2, Cpu, Sparkles, BarChart3, Image as ImageIcon, ChevronDown, Settings,
    Plus, X, GitMerge, Search, CircleHelp
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import api, { triggerMemoryGeneration, triggerIntelligenceCheck, triggerKnowledgeCheck, triggerPlaybookExtraction, exportKnowledgePack, triggerBackfillFacets, triggerReflectTelemetry, triggerInteractionRetention, fetchProviderModels, analyzeHygieneNow, backfillEmbeddings, getEmbeddingCoverage, getPipelineRuns, getMaintenanceControls, getMaintenanceEligibleCounts, setMaintenanceControl } from "@/lib/api";
import { useEffect } from "react";

const apiErrorMessage = (error, fallback) => {
    const detail = error?.response?.data?.detail;
    if (Array.isArray(detail)) return detail.map(item => item?.msg || item?.detail || JSON.stringify(item)).join(", ");
    if (detail && typeof detail === "object") return detail.message || JSON.stringify(detail);
    return detail || fallback;
};

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
import { DraggablePipeline, KnowledgePathways } from "./DraggablePipeline";
import { OutboundWebhooksSettings } from "./OutboundWebhooksSettings";
import { VisionWebhooksSettings } from "./VisionWebhooksSettings";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

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
    const [retentionRunning, setRetentionRunning] = useState(false);
    const pipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "interactions" && c.task_type !== "embedding").sort((a,b) => a.execution_order - b.execution_order);

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
                                <SettingLabel help="rate_limit_enabled">Enable Rate Limiting</SettingLabel>
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
                            <SettingLabel help="rate_limit_rpm" className="text-xs font-mono">Requests per Minute (RPM)</SettingLabel>
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

            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Raw Interaction Retention</CardTitle>
                    <CardDescription className="text-xs">
                        Remove old source interactions after their processing outcome is recorded. Default retention is 30 days.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-1">
                            <SettingLabel help="interaction_retention_days" className="text-xs font-mono">Retention period (days)</SettingLabel>
                            <Input type="number" min={1} max={3650}
                                value={settings.interaction_retention_days ?? 30}
                                onChange={(e) => onUpdateSettings("interaction_retention_days", Math.max(1, parseInt(e.target.value, 10) || 30))} />
                        </div>
                        <div className="flex items-center justify-between gap-3">
                            <div>
                                <SettingLabel help="interaction_retain_until_processed">Retain until processing completes</SettingLabel>
                                <p className="text-[10px] text-muted-foreground">Protect pending, failed, and unreflected source records.</p>
                            </div>
                            <Switch checked={settings.interaction_retain_until_processed ?? true}
                                onCheckedChange={(v) => onUpdateSettings("interaction_retain_until_processed", v)} />
                        </div>
                    </div>
                    <Button variant="outline" disabled={retentionRunning} onClick={async () => {
                        setRetentionRunning(true);
                        try { await triggerInteractionRetention({ batch_size: 500, max_records: 5000 }); toast.success("Interaction retention cleanup queued"); }
                        catch (e) { toast.error(apiErrorMessage(e, "Failed to queue retention cleanup")); }
                        finally { setRetentionRunning(false); }
                    }}>Run bounded cleanup</Button>
                    <p className="text-[10px] text-muted-foreground">Each run deletes at most 5,000 eligible records. Failed or unfinished telemetry remains protected when the toggle is on.</p>
                </CardContent>
            </Card>

            {/* Outbound Webhooks */}
            <OutboundWebhooksSettings />

            {/* Vision Completion Webhooks */}
            <VisionWebhooksSettings />
        </div>
    );
}

// â”€â”€â”€ Memories Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function MemoryGenerationTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const [isTriggering, setIsTriggering] = useState(false);
    const pipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "memories" && c.task_type !== "embedding").sort((a,b) => a.execution_order - b.execution_order);

    const handleRunNow = async () => {
        setIsTriggering(true);
        try {
            await triggerMemoryGeneration(true);
            toast.success("Generation task scheduled in background. Check docker logs.");
        } catch (error) {
            toast.error(apiErrorMessage(error, "Failed to trigger task"));
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
                            <SettingLabel help="memory_run_time" className="text-xs font-mono">Daily Run Time (UTC)</SettingLabel>
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
                                <SettingLabel help="memory_prior_chrono" className="text-xs font-mono">Chronological Memories</SettingLabel>
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
                                <SettingLabel help="memory_prior_semantic" className="text-xs font-mono">Semantic Memories</SettingLabel>
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

                    <div className="space-y-2">
                        <SettingLabel help="memory_max_tokens" className="text-xs font-mono">Max Output Tokens</SettingLabel>
                        <Input
                            type="number"
                            min={256}
                            max={8000}
                            step={100}
                            value={settings.memory_generation_max_tokens !== undefined ? settings.memory_generation_max_tokens : 1200}
                            onChange={(e) =>
                                onUpdateSettings("memory_generation_max_tokens", parseInt(e.target.value) || 1200)
                            }
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Caps the length of each generated memory summary. Higher = more detail retained, higher token cost.
                        </p>
                    </div>

                    {/* Â§ Threshold Trigger */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Layers className="w-4 h-4 text-amber-500" />
                            Threshold Trigger
                        </h4>
                        <p className="text-[10px] text-muted-foreground -mt-2">
                            Fire a memory job whenever the entity accumulates this many pending interactions —
                            in addition to the daily schedule, whichever comes first. Set to 0 to keep daily-only.
                            Only fires after a "safe boundary" interaction so a conversation isn't split mid-flight.
                        </p>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <SettingLabel help="memory_threshold" className="text-xs font-mono">Interaction Threshold</SettingLabel>
                                <Input
                                    type="number"
                                    min={0}
                                    max={500}
                                    value={settings.memory_threshold !== undefined ? settings.memory_threshold : 0}
                                    onChange={(e) =>
                                        onUpdateSettings("memory_threshold", parseInt(e.target.value) || 0)
                                    }
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    0 = disabled (daily schedule only). Typical: 10–30.
                                </p>
                            </div>
                            <div className="space-y-2">
                                <SettingLabel help="memory_safe_boundary" className="text-xs font-mono">Safe Boundary Types</SettingLabel>
                                <Input
                                    placeholder="e.g. outgoing_whatsapp_message,outgoing_email"
                                    className="font-mono text-xs"
                                    value={Array.isArray(settings.memory_safe_boundary_types)
                                        ? settings.memory_safe_boundary_types.join(",")
                                        : (settings.memory_safe_boundary_types || "outgoing_whatsapp_message")}
                                    onChange={(e) => {
                                        const arr = (e.target.value || "")
                                            .split(",")
                                            .map(s => s.trim())
                                            .filter(Boolean);
                                        onUpdateSettings("memory_safe_boundary_types", arr);
                                    }}
                                />
                                <p className="text-[10px] text-muted-foreground">
                                    Comma-separated interaction_types that may close a memory window.
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* Â§ Processing */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Cpu className="w-4 h-4 text-indigo-500" />
                            Processing
                        </h4>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <SettingLabel help="memory_retries" className="text-xs font-mono">Max Retries</SettingLabel>
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
                                <SettingLabel help="memory_retry_delay" className="text-xs font-mono">Retry Delay (ms)</SettingLabel>
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
                    />
                </CardContent>
            </Card>
        </div>
    );
}


// â”€â”€â”€ Intelligence Tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function IntelligenceTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline, entityTypes }) {
    const privatePipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "intelligence" && c.task_type !== "embedding").sort((a,b) => a.execution_order - b.execution_order);
    const [isTriggering, setIsTriggering] = useState(false);

    const handleRunNow = async () => {
        setIsTriggering(true);
        try {
            await triggerIntelligenceCheck();
            toast.success("Intelligence extraction check triggered. Entities at threshold will be queued.");
        } catch (error) {
            toast.error(apiErrorMessage(error, "Failed to trigger intelligence check"));
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
                                <SettingLabel help="intelligence_prior_chrono" className="text-xs font-mono">Chronological</SettingLabel>
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
                                <SettingLabel help="intelligence_prior_semantic" className="text-xs font-mono">Semantic</SettingLabel>
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
                            <SettingLabel help="intelligence_prior_knowledge" className="text-xs font-mono">Knowledge Cross-Reference (Semantic)</SettingLabel>
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
                        <div className="space-y-2 border-t pt-3">
                            <SettingLabel help="intelligence_max_tokens" className="text-xs font-mono">Max Output Tokens</SettingLabel>
                            <Input
                                type="number"
                                min={256}
                                max={8000}
                                step={100}
                                value={settings.intelligence_max_tokens !== undefined ? settings.intelligence_max_tokens : 1200}
                                onChange={(e) =>
                                    onUpdateSettings("intelligence_max_tokens", parseInt(e.target.value) || 1200)
                                }
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Caps the combined length of generated intelligence (the prompt emits up to 3 insights).
                                Raise if detailed multi-signal output is being truncated; lower to reduce token cost.
                            </p>
                        </div>
                    </div>

                    {/* § Schedule (nightly sweep valve) */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Clock className="w-4 h-4 text-teal-400" />
                            Schedule
                        </h4>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5 pr-4">
                                <SettingLabel help="intelligence_schedule_enabled" className="text-xs font-mono">Nightly Sweep</SettingLabel>
                                <p className="text-[10px] text-muted-foreground">
                                    Reflect every night on whatever accumulated — even entities below the threshold.
                                    Fires alongside the threshold valve (whichever comes first).
                                </p>
                            </div>
                            <Switch
                                checked={settings.intelligence_schedule_enabled !== undefined ? settings.intelligence_schedule_enabled : true}
                                onCheckedChange={(v) => onUpdateSettings("intelligence_schedule_enabled", v)}
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <SettingLabel help="intelligence_run_time" className="text-xs font-mono">Daily Run Time (UTC)</SettingLabel>
                                <Input type="time" value={settings.intelligence_generation_time || "02:30"}
                                    onChange={(e) => onUpdateSettings("intelligence_generation_time", e.target.value)} />
                            </div>
                            <div className="space-y-1">
                                <SettingLabel help="intelligence_schedule_floor" className="text-xs font-mono">Schedule Floor (min memories)</SettingLabel>
                                <Input type="number" min={1}
                                    value={settings.intelligence_schedule_floor !== undefined ? settings.intelligence_schedule_floor : 2}
                                    onChange={(e) => onUpdateSettings("intelligence_schedule_floor", parseInt(e.target.value) || 1)} />
                                <p className="text-[10px] text-muted-foreground">Minimum uncompacted memories for the nightly sweep to synthesize.</p>
                            </div>
                        </div>
                    </div>

                    {/* Â§ Mining Triggers (threshold valve) */}
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Brain className="w-4 h-4 text-purple-400" />
                            Threshold Trigger
                        </h4>
                        <div className="space-y-2">
                            <SettingLabel help="intelligence_threshold" className="text-xs font-mono">Global Default Threshold (N memories)</SettingLabel>
                            <Input
                                type="number"
                                min={2}
                                value={settings.intelligence_extraction_threshold || 10}
                                onChange={(e) =>
                                    onUpdateSettings("intelligence_extraction_threshold", parseInt(e.target.value))
                                }
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Fire an intelligence job intra-day the moment this many uncompacted memories accumulate for an entity (in addition to the nightly sweep).
                            </p>
                        </div>
                        <div className="space-y-3 pt-2">
                            <SettingLabel help="intelligence_overrides" className="text-xs font-mono">Entity-Specific Overrides</SettingLabel>
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
                        <div className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <CheckCircle2 className="w-4 h-4 text-green-500" />
                            <SettingLabel help="intelligence_auto_approve" className="text-sm font-semibold">Auto-Approve</SettingLabel>
                        </div>
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
function LegacyKnowledgeTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline, entityTypes }) {
    const publicPipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "knowledge").sort((a,b) => a.execution_order - b.execution_order);
    const [triggering, setTriggering] = useState(null); // 'check' | 'drain' | 'playbooks' | 'consolidation' | 'facets' | 'export'
    const [facetsSchemaText, setFacetsSchemaText] = useState("[]");
    const [profileMapText, setProfileMapText] = useState("{}");

    // Sync JSON editors from settings whenever settings load/change externally
    useEffect(() => {
        try { setFacetsSchemaText(JSON.stringify(settings.knowledge_facets_schema || [], null, 2)); } catch { /* keep */ }
        try { setProfileMapText(JSON.stringify(settings.profile_facet_map || {}, null, 2)); } catch { /* keep */ }
    }, [settings.knowledge_facets_schema, settings.profile_facet_map]);

    const commitJsonField = (field, text) => {
        try {
            const parsed = JSON.parse(text);
            onUpdateSettings(field, parsed);
            return true;
        } catch {
            toast.error(`Invalid JSON in ${field}`);
            return false;
        }
    };

    const runTrigger = async (kind, fn, successMsg) => {
        setTriggering(kind);
        try {
            await fn();
            toast.success(successMsg);
        } catch (error) {
            toast.error(apiErrorMessage(error, "Failed to queue trigger"));
        } finally {
            setTriggering(null);
        }
    };

    return (
        <div className="space-y-6">
            <div className="mb-2 flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h3 className="text-lg font-semibold flex items-center gap-2">
                        <GraduationCap className="w-5 h-5 text-indigo-500" />
                        Knowledge Generation
                    </h3>
                    <p className="text-sm text-muted-foreground mt-1">
                        Generate reusable knowledge and maintain the source data used by the pipeline.
                    </p>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Process the next eligible intelligence batch"
                        onClick={() => runTrigger('check', () => triggerKnowledgeCheck(false), "Knowledge generation queued")}
                        disabled={!!triggering}>
                        <Play className="w-3.5 h-3.5" />
                        Generate Next Batch
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Process all eligible confirmed intelligence and historical telemetry"
                        onClick={() => runTrigger('drain', () => triggerKnowledgeCheck(true), "Backlog drain queued — batches run until exhausted")}
                        disabled={!!triggering}>
                        <Zap className="w-3.5 h-3.5" />
                        Process Backlog
                    </Button>
                </div>
            </div>

            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3">
                    <CardTitle className="text-sm">Maintenance tools</CardTitle>
                    <CardDescription className="text-xs mt-1">
                        Use these only for a specific maintenance need. The planned Knowledge-table consolidation workflow is proposal-and-review based, so automatic consolidation is intentionally not exposed here.
                    </CardDescription>
                </CardHeader>
                <CardContent className="flex items-center gap-2 flex-wrap">
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Cluster confirmed intelligence across entities and extract playbooks + skills (normally weekly)"
                        onClick={() => runTrigger('playbooks', triggerPlaybookExtraction, "Playbook extraction queued")}
                        disabled={!!triggering}>
                        <Brain className="w-3.5 h-3.5" />
                        Extract Skills & Playbooks
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Download the whole knowledge base as a memory-file pack (INDEX.md + one markdown file per record)"
                        onClick={() => runTrigger('export', async () => {
                            const res = await exportKnowledgePack({ status: 'active' });
                            const url = window.URL.createObjectURL(new Blob([res.data]));
                            const a = document.createElement('a');
                            a.href = url; a.download = 'knowledge-pack.zip';
                            document.body.appendChild(a); a.click(); a.remove();
                            window.URL.revokeObjectURL(url);
                        }, "Knowledge pack downloaded")}
                        disabled={!!triggering}>
                        <FileText className="w-3.5 h-3.5" />
                        Export Pack
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Extract governed metadata.facets on existing knowledge records that lack them"
                        onClick={() => runTrigger('facets', triggerBackfillFacets, "Facet backfill queued")}
                        disabled={!!triggering}>
                        <Sparkles className="w-3.5 h-3.5" />
                        Backfill Facets
                    </Button>
                    <Button size="sm" variant="outline" className="gap-1.5"
                        title="Reflect on yesterday's AI telemetry to extract skills/playbooks/knowledge"
                        onClick={() => runTrigger('telemetry', () => triggerReflectTelemetry(), "Telemetry reflection queued")}
                        disabled={!!triggering}>
                        <Cpu className="w-3.5 h-3.5" />
                        Reflect Telemetry
                    </Button>
                </CardContent>
            </Card>

            {/* Knowledge Configuration — flat, no sub-section headers */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Settings className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Knowledge Configuration</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Mining triggers and prior context for knowledge generation.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* § Schedule (nightly sweep valve) */}
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Clock className="w-4 h-4 text-teal-400" />
                            Schedule
                        </h4>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5 pr-4">
                                <Label className="text-xs font-mono">Nightly Sweep</Label>
                                <p className="text-[10px] text-muted-foreground">
                                    Synthesize knowledge every night from whatever confirmed intelligence accumulated —
                                    even entity types below the threshold. Fires alongside the threshold valve.
                                </p>
                            </div>
                            <Switch
                                checked={settings.knowledge_schedule_enabled !== undefined ? settings.knowledge_schedule_enabled : true}
                                onCheckedChange={(v) => onUpdateSettings("knowledge_schedule_enabled", v)}
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Daily Run Time (UTC)</Label>
                                <Input type="time" value={settings.knowledge_generation_time || "03:00"}
                                    onChange={(e) => onUpdateSettings("knowledge_generation_time", e.target.value)} />
                            </div>
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Schedule Floor (min intelligence)</Label>
                                <Input type="number" min={1}
                                    value={settings.knowledge_schedule_floor !== undefined ? settings.knowledge_schedule_floor : 2}
                                    onChange={(e) => onUpdateSettings("knowledge_schedule_floor", parseInt(e.target.value) || 1)} />
                                <p className="text-[10px] text-muted-foreground">Minimum unused confirmed intelligence for the nightly sweep.</p>
                            </div>
                        </div>
                    </div>

                    {/* Knowledge Threshold (threshold valve) */}
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
                    <div className="space-y-2 border-t pt-4">
                        <Label className="text-xs font-mono">Max Output Tokens</Label>
                        <Input
                            type="number"
                            min={256}
                            max={8000}
                            step={100}
                            value={settings.knowledge_max_tokens !== undefined ? settings.knowledge_max_tokens : 1200}
                            onChange={(e) =>
                                onUpdateSettings("knowledge_max_tokens", parseInt(e.target.value) || 1200)
                            }
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Caps the generated knowledge JSON. A response truncated mid-JSON fails to parse and the run
                            is skipped — raise this if storytelling content gets cut off; lower it to reduce token cost.
                        </p>
                    </div>
                    {/* Context injection (retrieval, not generation) */}
                    <div className="grid grid-cols-2 gap-4 border-t pt-4">
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Context Injection Cap</Label>
                            <Input
                                type="number" min={1} max={100}
                                value={settings.context_knowledge_count !== undefined ? settings.context_knowledge_count : 30}
                                onChange={(e) => onUpdateSettings("context_knowledge_count", parseInt(e.target.value) || 30)}
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Max knowledge items injected into an entity's get-context payload. Items are ranked by
                                relevance to the live conversation (blended with quality), not just quality.
                            </p>
                        </div>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Relevance Floor</Label>
                            <Input
                                type="number" step="0.05" min={0} max={1}
                                value={settings.context_knowledge_min_similarity !== undefined ? settings.context_knowledge_min_similarity : 0}
                                onChange={(e) => onUpdateSettings("context_knowledge_min_similarity", parseFloat(e.target.value) || 0)}
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Drop knowledge below this cosine similarity to the conversation. 0 = never drop
                                (reorder only). Raise once the corpus is large enough to filter aggressively.
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center justify-between border-t pt-4">
                        <div className="space-y-0.5 pr-4">
                            <Label className="text-xs font-mono">Refine on Merge</Label>
                            <p className="text-[10px] text-muted-foreground">
                                When a new precursor matches an existing knowledge/skill/playbook, LLM-merge the new
                                evidence into it (update-in-place, version bump) instead of only counting the match.
                                Falls back to a plain count increment on any failure.
                            </p>
                        </div>
                        <Switch
                            checked={settings.knowledge_refine_on_merge !== undefined ? settings.knowledge_refine_on_merge : true}
                            onCheckedChange={(v) => onUpdateSettings("knowledge_refine_on_merge", v)}
                        />
                    </div>

                    {/* Auto-activate new knowledge (global dial) */}
                    <div className="flex items-center justify-between border-t pt-4">
                        <div className="space-y-0.5 pr-4">
                            <Label className="text-xs font-mono">Auto-activate New Knowledge</Label>
                            <p className="text-[10px] text-muted-foreground">
                                When on, new knowledge — including telemetry-reflected skill/playbook candidates — is
                                created <code>active</code> so the agent sees it immediately. Turn off to keep new
                                knowledge as drafts for review. Existing drafts were activated once on deploy.
                            </p>
                        </div>
                        <Switch
                            checked={settings.knowledge_auto_activate !== undefined ? settings.knowledge_auto_activate : true}
                            onCheckedChange={(v) => onUpdateSettings("knowledge_auto_activate", v)}
                        />
                    </div>

                    {/* Sprint 2.5 — governed facets + lean index injection */}
                    <div className="grid grid-cols-2 gap-4 border-t pt-4">
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Context Injection Mode</Label>
                            <select
                                className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm"
                                value={settings.context_knowledge_mode || "full"}
                                onChange={(e) => onUpdateSettings("context_knowledge_mode", e.target.value)}
                            >
                                <option value="full">full — inject complete records (prior behavior)</option>
                                <option value="index">index — lean index, pull full on demand</option>
                            </select>
                            <p className="text-[10px] text-muted-foreground">
                                In <code>index</code> mode each item shows id/name/category/signals/summary/facets only —
                                the agent retrieves full content via GET /knowledge/&#123;id&#125; when it decides an entry is relevant.
                                The always-on Knowledge Management skill is injected in full regardless of mode.
                            </p>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5 pr-4">
                                <Label className="text-xs font-mono">Facet Extraction</Label>
                                <p className="text-[10px] text-muted-foreground">
                                    Extract governed metadata.facets on knowledge creation (one extra LLM call, additive only —
                                    never alters generated content). Disable to skip the call entirely.
                                </p>
                            </div>
                            <Switch
                                checked={settings.facet_extraction_enabled !== undefined ? settings.facet_extraction_enabled : true}
                                onCheckedChange={(v) => onUpdateSettings("facet_extraction_enabled", v)}
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-2 gap-4 border-t pt-4">
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <Label className="text-xs font-mono">Knowledge Facets Schema</Label>
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]"
                                    onClick={() => commitJsonField("knowledge_facets_schema", facetsSchemaText)}>
                                    Save
                                </Button>
                            </div>
                            <textarea
                                className="w-full h-40 rounded-md border border-input bg-background p-2 text-[11px] font-mono"
                                value={facetsSchemaText}
                                onChange={(e) => setFacetsSchemaText(e.target.value)}
                                onBlur={() => commitJsonField("knowledge_facets_schema", facetsSchemaText)}
                                spellCheck={false}
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Governed facet keys agents may filter on. JSON array of &#123;key, label, description, examples?&#125;.
                                Values are normalized at extraction; vocabulary is discoverable via GET /knowledge/facets.
                            </p>
                        </div>
                        <div className="space-y-2">
                            <div className="flex items-center justify-between">
                                <Label className="text-xs font-mono">Profile → Facet Map</Label>
                                <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px]"
                                    onClick={() => commitJsonField("profile_facet_map", profileMapText)}>
                                    Save
                                </Button>
                            </div>
                            <textarea
                                className="w-full h-40 rounded-md border border-input bg-background p-2 text-[11px] font-mono"
                                value={profileMapText}
                                onChange={(e) => setProfileMapText(e.target.value)}
                                onBlur={() => commitJsonField("profile_facet_map", profileMapText)}
                                spellCheck={false}
                            />
                            <p className="text-[10px] text-muted-foreground">
                                Maps facet_key → entity_profiles property name, so get-context auto-derives facets from the
                                contact's CRM profile when no explicit facets are passed. Leave empty to disable derivation.
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Quality Gauges */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Shield className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Quality Gauges</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Controls for deduplication, quality scoring, consolidation, and playbook extraction.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    {/* Dedup & Quality */}
                    <div>
                        <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Dedup & Quality</Label>
                        <div className="grid grid-cols-2 gap-4 mt-2">
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Duplicate Similarity Threshold</Label>
                                <Input
                                    type="number" step="0.05" min="0.5" max="1.0"
                                    value={settings.dedup_similarity_threshold ?? 0.85}
                                    onChange={(e) => onUpdateSettings("dedup_similarity_threshold", parseFloat(e.target.value) || 0.85)}
                                />
                                <p className="text-[10px] text-muted-foreground">Cosine similarity that defines a "duplicate" — used by BOTH creation-time dedup (every pathway) and weekly consolidation (0.5-1.0; lower = merge more aggressively).</p>
                            </div>
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Extraction Confidence Threshold</Label>
                                <Input
                                    type="number" step="0.05" min="0.3" max="1.0"
                                    value={settings.extraction_confidence_threshold ?? 0.6}
                                    onChange={(e) => onUpdateSettings("extraction_confidence_threshold", parseFloat(e.target.value) || 0.6)}
                                />
                                <p className="text-[10px] text-muted-foreground">Minimum confidence to accept an extraction (0.3-1.0)</p>
                            </div>
                        </div>
                    </div>

                    {/* Consolidation */}
                    <div className="border-t pt-4">
                        <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Consolidation</Label>
                        <div className="grid grid-cols-1 gap-4 mt-2">
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Consolidation Interval (days)</Label>
                                <Input
                                    type="number" min="1" max="30"
                                    value={settings.consolidation_run_interval_days ?? 7}
                                    onChange={(e) => onUpdateSettings("consolidation_run_interval_days", parseInt(e.target.value) || 7)}
                                />
                                <p className="text-[10px] text-muted-foreground">How often to run the weekly consolidation sweep. The merge similarity threshold is the "Duplicate Similarity Threshold" above — shared with creation-time dedup.</p>
                            </div>
                        </div>
                    </div>

                    {/* Creation-time Dedup */}
                    <div className="border-t pt-4">
                        <div className="flex items-center justify-between">
                            <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Creation-time Dedup</Label>
                            <Switch
                                checked={settings.knowledge_creation_dedup_enabled !== undefined ? settings.knowledge_creation_dedup_enabled : true}
                                onCheckedChange={(v) => onUpdateSettings("knowledge_creation_dedup_enabled", v)}
                            />
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-2">When on, every knowledge creation pathway (intelligence, telemetry, playbook, skill) merges into an existing near-identical record instead of creating a duplicate. Uses the "Duplicate Similarity Threshold" above (shared with weekly consolidation).</p>
                    </div>

                    {/* Playbook Extraction */}
                    <div className="border-t pt-4">
                        <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Playbook Extraction</Label>
                        <div className="grid grid-cols-2 gap-4 mt-2">
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Playbook Interval (days)</Label>
                                <Input
                                    type="number" min="1" max="30"
                                    value={settings.playbook_extraction_interval_days ?? 7}
                                    onChange={(e) => onUpdateSettings("playbook_extraction_interval_days", parseInt(e.target.value) || 7)}
                                />
                                <p className="text-[10px] text-muted-foreground">How often to attempt playbook extraction</p>
                            </div>
                            <div className="space-y-1">
                                <Label className="text-xs font-mono">Evidence Threshold</Label>
                                <Input
                                    type="number" min="5" max="100"
                                    value={settings.playbook_extraction_evidence_threshold ?? 20}
                                    onChange={(e) => onUpdateSettings("playbook_extraction_evidence_threshold", parseInt(e.target.value) || 20)}
                                />
                                <p className="text-[10px] text-muted-foreground">Unlinked intelligence needed to trigger early extraction</p>
                            </div>
                        </div>
                    </div>

                    {/* Processing */}
                    <div className="border-t pt-4">
                        <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Processing</Label>
                        <div className="space-y-1 mt-2">
                            <Label className="text-xs font-mono">Memory Generation Interaction Types</Label>
                            <div className="flex gap-2">
                                <Input
                                    value={Array.isArray(settings.memory_generation_interaction_types) ? settings.memory_generation_interaction_types.join(", ") : (settings.memory_generation_interaction_types || "")}
                                    onChange={(e) => {
                                        const val = e.target.value.trim();
                                        onUpdateSettings("memory_generation_interaction_types", val ? val.split(",").map(s => s.trim()).filter(Boolean) : null);
                                    }}
                                    placeholder="e.g. internal_ai_thought, internal_ai_tool_call"
                                    className="flex-1"
                                />
                                <Select
                                    value={settings.memory_generation_interaction_types_mode || "exclude"}
                                    onValueChange={(v) => onUpdateSettings("memory_generation_interaction_types_mode", v)}
                                >
                                    <SelectTrigger className="w-[130px] h-9 text-xs">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="exclude">Exclude</SelectItem>
                                        <SelectItem value="include">Include only</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <p className="text-[10px] text-muted-foreground">Comma-separated interaction types. Mode determines whether these are excluded or the only ones included in memory generation.</p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <KnowledgeHygieneCard settings={settings} onUpdateSettings={onUpdateSettings} />

            <PromptStructurePreview sections={[
                { label: "Existing Knowledge (do NOT duplicate or repeat these)", color: "text-indigo-400", count: settings.prior_knowledge_semantic_count !== undefined ? settings.prior_knowledge_semantic_count : 3, conditional: true, description: "Semantically similar existing knowledge items for deduplication" },
                { label: "Intelligence Items to Synthesize", color: "text-purple-400", description: "PII-scrubbed intelligence items being synthesized into reusable knowledge" },
            ]} />

            {/* Telemetry Reflection */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-cyan-500" />
                        <CardTitle className="text-lg">Telemetry Reflection</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Nightly reflection on the agent's own telemetry (internal_ai_thought / internal_ai_tool_call).
                        Learns by doing: extracts reusable skills, playbooks, and trade-knowledge from what the agent
                        actually did or discovered — per entity, per day. Recurring learnings strengthen via dedup/merge.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5 pr-4">
                            <Label className="text-xs font-mono">Enable Nightly Reflection</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Emits typed candidates (skill / playbook / best_practices / lessons_learned / trade_knowledge)
                                as drafts. A single-session discovery starts at evidence_breadth=1 and promotes as it recurs.
                            </p>
                        </div>
                        <Switch
                            checked={settings.telemetry_reflection_enabled !== undefined ? settings.telemetry_reflection_enabled : true}
                            onCheckedChange={(v) => onUpdateSettings("telemetry_reflection_enabled", v)}
                        />
                    </div>
                    <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-1">
                            <Label className="text-xs font-mono">Daily Run Time (UTC)</Label>
                            <Input type="time" value={settings.telemetry_reflection_time || "04:00"}
                                onChange={(e) => onUpdateSettings("telemetry_reflection_time", e.target.value)} />
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs font-mono">Min Confidence</Label>
                            <Input type="number" step="0.05" min={0} max={1}
                                value={settings.telemetry_reflection_confidence_min !== undefined ? settings.telemetry_reflection_confidence_min : 0.6}
                                onChange={(e) => onUpdateSettings("telemetry_reflection_confidence_min", parseFloat(e.target.value) || 0)} />
                            <p className="text-[10px] text-muted-foreground">Discard candidates below this.</p>
                        </div>
                        <div className="space-y-1">
                            <Label className="text-xs font-mono">Max Output Tokens</Label>
                            <Input type="number" min={256} max={8000} step={100}
                                value={settings.telemetry_reflection_max_tokens !== undefined ? settings.telemetry_reflection_max_tokens : 1200}
                                onChange={(e) => onUpdateSettings("telemetry_reflection_max_tokens", parseInt(e.target.value) || 1200)} />
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Knowledge Generation Pathways (NOT a sequential pipeline — each
                pathway is an independent producer that picks its node by task_type) */}
            <Card className="border-dashed bg-muted/20">
                <CardHeader className="pb-3 border-b">
                    <CardTitle className="text-sm">Knowledge Generation Pathways</CardTitle>
                    <CardDescription className="text-[11px] mt-1">
                        Each pathway produces a different kind of knowledge from different input. Edit a prompt to tune that pathway.
                    </CardDescription>
                </CardHeader>
                <CardContent className="pt-4">
                    <KnowledgePathways
                        pipelineConfigs={publicPipelineNodes}
                        llmProviders={llmProviders}
                        onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig}
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
function SharedEmbeddingCard({ llmConfigs, onSaveConfig, onDeleteConfig, llmProviders, modelLists, fetchingModels, fetchErrors, onFetchModels }) {
    const [coverage, setCoverage] = useState(null);
    const embeddingConfig = (llmConfigs || []).find((config) => config.task_type === "embedding");
    const refreshCoverage = useCallback(() => {
        getEmbeddingCoverage().then(({ data }) => setCoverage(data)).catch(() => setCoverage(null));
    }, []);
    useEffect(() => { refreshCoverage(); }, [refreshCoverage]);
    return (
        <Card className="mb-6 border-green-500/30">
            <CardHeader className="pb-3 border-b">
                <div className="flex items-center gap-2"><Layers className="w-5 h-5 text-green-500" /><CardTitle className="text-lg">Shared Embedding &amp; Semantic Index</CardTitle></div>
                <CardDescription className="text-xs mt-1.5">One embedding provider and model are shared by interactions, memories, intelligence, and knowledge. Changing them requires a coordinated backfill.</CardDescription>
            </CardHeader>
            <CardContent className="pt-4 space-y-4">
                {embeddingConfig ? <InlineTaskConfigAccordion
                    config={embeddingConfig} llmProviders={llmProviders} onSaveConfig={onSaveConfig}
                    models={modelLists[embeddingConfig.id] || []} loadingModels={fetchingModels[embeddingConfig.id]}
                    error={fetchErrors[embeddingConfig.id]} onFetchModels={onFetchModels} isToggleable={true}
                    toggleChecked={embeddingConfig.is_active}
                    onToggleChange={(value) => onSaveConfig(embeddingConfig.id, { is_active: value })}
                    onDeleteConfig={onDeleteConfig}
                /> : <p className="text-xs text-amber-600">No shared embedding configuration is active. Semantic retrieval and consolidation will be limited.</p>}
                <div className="rounded-md border p-3 text-xs space-y-2">
                    <div className="flex items-center justify-between"><span className="text-muted-foreground">Overall coverage (v{coverage?.current_version ?? 2})</span><span className="font-medium">{coverage ? `${coverage.compatible}/${coverage.total} compatible (${(coverage.coverage * 100).toFixed(0)}%)` : "Loading…"}</span></div>
                    {coverage && <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-[10px]">{["interactions", "memories", "intelligence", "knowledge"].map((tier) => { const item = coverage.tiers?.[tier] || {}; return <div key={tier} className="rounded border px-2 py-1"><div className="font-medium capitalize">{tier}</div><div className="text-muted-foreground">{item.compatible || 0}/{item.total || 0} compatible</div></div>; })}</div>}
                    {coverage?.stale > 0 && <div className="text-amber-700">{coverage.stale} record(s) need backfill.</div>}
                    <p className="text-[10px] text-muted-foreground">Embedding backfill is now started and monitored from Knowledge → Operations.</p>
                </div>
                <p className="text-[10px] text-muted-foreground">Record-level embeddings currently use one serialized vector per record. Chunk size and overlap are not embedding controls.</p>
            </CardContent>
        </Card>
    );
}

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
                const detail = err.response?.data?.detail;
                const message = Array.isArray(detail)
                    ? detail.map(item => item?.msg || item?.detail || JSON.stringify(item)).join(", ")
                    : (typeof detail === "object" ? JSON.stringify(detail) : (detail || "Failed to fetch models."));
                setFetchErrors((prev) => ({ ...prev, [configId]: message }));
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
            <SharedEmbeddingCard
                llmConfigs={llmConfigs}
                onSaveConfig={onSaveConfig}
                onDeleteConfig={onDeleteConfig}
                llmProviders={llmProviders}
                modelLists={modelLists}
                fetchingModels={fetchingModels}
                fetchErrors={fetchErrors}
                onFetchModels={handleFetchModels}
            />
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

const KNOWLEDGE_SETTING_HELP = {
    interaction_retention_days: "Number of days raw interactions are retained after their processing outcome is complete. This does not delete memories, intelligence, or Knowledge.",
    interaction_retain_until_processed: "When enabled, pending, failed, and unreflected interactions cannot be removed by age-based cleanup. A telemetry day with no reusable learning counts as completed.",
    rate_limit_enabled: "Applies a per-agent limit to incoming API requests. Enable it when clients or integrations must be protected from bursts.",
    rate_limit_rpm: "Maximum incoming API requests an agent may make in one minute while rate limiting is enabled.",
    memory_run_time: "UTC time for the daily sweep that turns pending interactions into memory records.",
    memory_prior_chrono: "Number of the entity's newest memory records provided to the memory model for continuity.",
    memory_prior_semantic: "Number of earlier memories most related to the current interactions, found through semantic search.",
    memory_max_tokens: "Maximum length of the generated memory output. Higher values retain more detail but use more model tokens.",
    memory_threshold: "Creates a memory before the daily sweep once this many pending interactions accumulate for an entity. Zero disables this early trigger.",
    memory_safe_boundary: "Interaction types that may close a memory window. This prevents an active conversation from being split into separate memories.",
    memory_retries: "Maximum attempts to retry a failed memory-generation job before it is marked failed.",
    memory_retry_delay: "Initial wait before retrying a failed memory job. Later retries use exponential backoff from this value.",
    embedding_chunk_size: "Maximum size of an interaction-text chunk sent for embedding. Larger chunks carry more context; smaller chunks make retrieval more precise.",
    embedding_chunk_overlap: "Text repeated between adjacent embedding chunks so information at a boundary is not lost.",
    intelligence_prior_chrono: "Number of the entity's most recent intelligence records included to avoid repeating known findings.",
    intelligence_prior_semantic: "Number of the entity's most semantically related intelligence records included during generation.",
    intelligence_prior_knowledge: "Number of approved organizational Knowledge records supplied as cross-entity context when generating intelligence.",
    intelligence_max_tokens: "Maximum total length of the intelligence response. Raise only when valid multi-insight output is being truncated.",
    intelligence_schedule_enabled: "Enables the daily intelligence sweep, in addition to the threshold-based trigger.",
    intelligence_run_time: "UTC time for the daily intelligence sweep.",
    intelligence_schedule_floor: "Minimum uncompacted memories required for the scheduled sweep to generate intelligence for an entity.",
    intelligence_threshold: "Default number of uncompacted memories that triggers intelligence generation before the scheduled sweep.",
    intelligence_overrides: "Optional per-entity threshold overrides. Use only where an entity type accumulates evidence at a meaningfully different rate.",
    generation_enabled: "Turns all scheduled and threshold-driven Knowledge generation on or off. Existing Knowledge is not changed.",
    generation_time: "UTC time for the single daily run of all enabled Knowledge pathways.",
    evidence_threshold: "Minimum source evidence required before a pathway may generate Knowledge. Higher values wait for more evidence; lower values generate sooner.",
    minimum_confidence: "Minimum confidence reported by the generation model before a candidate is accepted. This is not a similarity score or a quality score.",
    maximum_tokens: "Maximum response length available to a generation model. Increase only when valid structured responses are being truncated.",
    approval_policy: "Approved records can be retrieved by agents. Draft records remain stored but are excluded from normal agent retrieval until reviewed.",
    operation_type: "Select the manual Knowledge operation to configure and run. Permanent system behavior remains in the Generation, Maintenance, and Retrieval tabs.",
    records_per_batch: "Number of eligible input records processed before the operation reaches its next bounded processing unit. Each operation enforces its own safe maximum.",
    batches_per_run: "Choose a finite number of batches or process the snapshot of all records that are eligible when the run starts. New records arriving later are not added to that run.",
    batch_limit: "Maximum number of batches for this run when Batches per Run is limited. The operation stops earlier if no eligible records remain.",
    facet_schema: "Shared governed keys that the generation model may populate in its primary response. A facet is added only when the evidence explicitly supports it.",
    profile_map: "Retrieval-only mapping from entity-profile fields to governed facets. Profile matches boost ranking; they do not exclude Knowledge.",
    max_matches: "Maximum ordinary Knowledge index entries returned in context. Always-on records are injected separately in full.",
    relevance_floor: "Minimum semantic relevance for ordinary retrieval. Zero ranks candidates without excluding them; a positive value excludes records without compatible embeddings.",
    hygiene_enabled: "Enables candidate discovery and consolidation proposals. Similarity discovers related records; it never independently performs a merge.",
    hygiene_mode: "Controls whether hygiene only analyzes, creates proposals, requires manual approval, or may auto-apply under strict policy gates.",
    candidate_similarity: "Embedding similarity used to draw candidate relationships. It does not decide whether records should consolidate.",
    evidence_routing: "Uses source embeddings before an expensive generation call. Very high similarity can link evidence; moderate similarity can request an LLM revision assessment.",
    evidence_mode: "Analysis only records routing recommendations without changing Knowledge. Enforced applies the allowed evidence-link or revision route.",
    evidence_low: "Lower bound for a related-evidence match. At or above this value, enforced mode asks the LLM whether an existing canonical record needs revision.",
    evidence_high: "Very-high evidence match threshold. At or above this value, enforced mode may link evidence to one existing canonical record without generating another record.",
    evidence_coverage: "Share of source items that must meet the very-high threshold before evidence can be linked automatically.",
    cluster_min: "Smallest number of Knowledge records that can form a consolidation candidate cluster.",
    cluster_max: "Largest automatically handled cluster. Larger connected components are split or sent for review to avoid weak chains combining a broad topic.",
    cohesion: "Minimum average similarity within a cluster. It guards against transitively connected but incoherent groups.",
    weak_link: "Similarity below which a graph edge is treated as weak during cluster splitting.",
    preview_ttl: "How long a non-mutating consolidation preview remains valid before source changes require regeneration.",
    auto_confidence: "Minimum LLM consolidation confidence required before an automatic policy may apply a proposal. It is never the only safety gate.",
    contradiction_policy: "How unresolved contradictions affect consolidation. Manual review is the safest production default.",
    canonical_strategy: "Default for approved consolidations: update one selected source or create a new canonical record and retire every source.",
    embedding_version: "Embedding serialization version used for candidate comparison. Change only with a planned backfill and calibration.",
    creation_time: "After creating eligible Knowledge, enqueue the shared non-mutating hygiene preview. It does not directly merge records.",
    consolidation_categories: "Choose which Knowledge categories participate in automated candidate discovery. Categories are never automatically consolidated across one another.",
    category_automation: "Per-category safety gate. A category remains manual until explicitly allowed, even if the global hygiene mode is automatic.",
};

function SettingLabel({ children, help, className = "text-xs" }) {
    const text = KNOWLEDGE_SETTING_HELP[help] || help;
    return <div className="flex items-center gap-1">
        <Label className={className}>{children}</Label>
        {text && <TooltipProvider delayDuration={120}><Tooltip><TooltipTrigger asChild><button type="button" aria-label={`Help: ${children}`} className="text-muted-foreground hover:text-foreground"><CircleHelp className="h-3.5 w-3.5" /></button></TooltipTrigger><TooltipContent className="max-w-xs text-xs leading-relaxed">{text}</TooltipContent></Tooltip></TooltipProvider>}
    </div>;
}

// Simplified Knowledge settings: generation, maintenance, and retrieval only.
function KnowledgeTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, entityTypes }) {
    const publicPipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "knowledge").sort((a,b) => a.execution_order - b.execution_order);
    const [runs, setRuns] = useState([]);
    const [controls, setControls] = useState([]);
    const [eligibleCounts, setEligibleCounts] = useState({});
    const [facetsSchemaText, setFacetsSchemaText] = useState("[]");
    const [profileMapText, setProfileMapText] = useState("{}");

    useEffect(() => {
        try { setFacetsSchemaText(JSON.stringify(settings.knowledge_facets_schema || [], null, 2)); } catch { /* noop */ }
        try { setProfileMapText(JSON.stringify(settings.profile_facet_map || {}, null, 2)); } catch { /* noop */ }
    }, [settings.knowledge_facets_schema, settings.profile_facet_map]);
    const refreshStatus = useCallback(() => Promise.all([
        getPipelineRuns({ limit: 30 }), getMaintenanceControls(),
    ]).then(([runResponse, controlResponse]) => {
        setRuns(runResponse.data?.items || runResponse.data || []);
        setControls(controlResponse.data?.items || []);
    }).catch(() => {}), []);
    const refreshEligible = useCallback(() => getMaintenanceEligibleCounts().then(({ data }) => setEligibleCounts(data || {})).catch(() => {}), []);
    useEffect(() => {
        refreshStatus(); refreshEligible();
        const statusTimer = setInterval(refreshStatus, 5000);
        const eligibleTimer = setInterval(refreshEligible, 60000);
        return () => { clearInterval(statusTimer); clearInterval(eligibleTimer); };
    }, [refreshStatus, refreshEligible]);
    const saveJson = (field, text) => {
        try { onUpdateSettings(field, JSON.parse(text)); }
        catch { toast.error(`Invalid JSON in ${field}`); }
    };

    return (
        <div className="space-y-5">
            <div>
                <h3 className="text-lg font-semibold flex items-center gap-2"><GraduationCap className="w-5 h-5 text-indigo-500" />Knowledge</h3>
                <p className="text-sm text-muted-foreground mt-1">Configure how knowledge is generated, maintained, and retrieved.</p>
            </div>
            <Tabs defaultValue="generation" className="w-full">
                <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="generation">Knowledge Generation</TabsTrigger>
                    <TabsTrigger value="maintenance">Knowledge Maintenance</TabsTrigger>
                    <TabsTrigger value="retrieval">Knowledge Retrieval</TabsTrigger>
                    <TabsTrigger value="operations">Knowledge Operations</TabsTrigger>
                </TabsList>

                <TabsContent value="generation" className="space-y-5 mt-5">
                    <Card className="border-dashed bg-muted/20"><CardHeader><CardTitle className="text-base">Knowledge Generation Pathways</CardTitle><CardDescription>Each independent pathway contains its own overrides, prompt, provider, and model.</CardDescription></CardHeader><CardContent><KnowledgePathways pipelineConfigs={publicPipelineNodes} llmProviders={llmProviders} onSaveConfig={onSaveConfig} onDeleteConfig={onDeleteConfig} modelLists={modelLists} fetchingModels={fetchingModels} fetchErrors={fetchErrors} onFetchModels={onFetchModels} settings={settings} onUpdateSettings={onUpdateSettings} entityTypes={entityTypes} /></CardContent></Card>
                    <Card>
                        <CardHeader><CardTitle className="text-base">Global generation controls</CardTitle><CardDescription>Defaults shared by every generation pathway. A pathway override applies only where shown below.</CardDescription></CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex items-center justify-between"><div><SettingLabel help="generation_enabled">Generation enabled</SettingLabel><p className="text-[11px] text-muted-foreground">Master switch for scheduled and threshold-driven generation.</p></div><Switch checked={settings.knowledge_generation_enabled ?? true} onCheckedChange={(v) => onUpdateSettings("knowledge_generation_enabled", v)} /></div>
                            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                <div className="space-y-1"><SettingLabel help="generation_time">Daily run time (UTC)</SettingLabel><Input type="time" value={settings.knowledge_generation_time || "03:00"} onChange={(e) => onUpdateSettings("knowledge_generation_time", e.target.value)} /></div>
                                <div className="space-y-1"><SettingLabel help="evidence_threshold">Evidence threshold</SettingLabel><Input type="number" min="1" value={settings.knowledge_generation_evidence_threshold ?? 5} onChange={(e) => onUpdateSettings("knowledge_generation_evidence_threshold", Number(e.target.value) || 1)} /></div>
                                <div className="space-y-1"><SettingLabel help="minimum_confidence">Minimum confidence</SettingLabel><Input type="number" min="0" max="1" step="0.05" value={settings.knowledge_generation_min_confidence ?? 0.6} onChange={(e) => onUpdateSettings("knowledge_generation_min_confidence", Number(e.target.value))} /></div>
                                <div className="space-y-1"><SettingLabel help="maximum_tokens">Maximum output tokens</SettingLabel><Input type="number" min="256" max="8000" value={settings.knowledge_generation_max_tokens ?? 1200} onChange={(e) => onUpdateSettings("knowledge_generation_max_tokens", Number(e.target.value) || 1200)} /></div>
                            </div>
                            <div className="max-w-sm space-y-1"><SettingLabel help="approval_policy">Activation policy</SettingLabel><Select value={settings.knowledge_generation_approval_policy || "approve_immediately"} onValueChange={(v) => onUpdateSettings("knowledge_generation_approval_policy", v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="approve_immediately">Create as Approved</SelectItem><SelectItem value="create_as_draft">Create as Draft</SelectItem></SelectContent></Select><p className="text-[10px] text-muted-foreground">Approved records may be retrieved by agents. Draft records require review.</p></div>
                        </CardContent>
                    </Card>

                    <Card><CardHeader><CardTitle className="text-base">Pre-generation evidence routing</CardTitle><CardDescription>Uses persisted source embeddings before an expensive generation call. Similarity discovers the route; the LLM decides whether moderate matches revise an existing record.</CardDescription></CardHeader><CardContent className="space-y-4">
                        <div className="flex items-center justify-between"><div><SettingLabel help="evidence_routing">Evidence routing enabled</SettingLabel><p className="text-[10px] text-muted-foreground">Applies to declarative, telemetry, playbook, and skill pathways.</p></div><Switch checked={settings.knowledge_evidence_routing_enabled ?? true} onCheckedChange={(v) => onUpdateSettings("knowledge_evidence_routing_enabled", v)} /></div>
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4"><div className="space-y-1"><SettingLabel help="evidence_mode">Mode</SettingLabel><Select value={settings.knowledge_evidence_routing_mode || "analysis_only"} onValueChange={(v) => onUpdateSettings("knowledge_evidence_routing_mode", v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="analysis_only">Analysis only</SelectItem><SelectItem value="enforced">Enforced</SelectItem></SelectContent></Select></div><div className="space-y-1"><SettingLabel help="evidence_low">Moderate from</SettingLabel><Input type="number" min="0" max="1" step="0.01" value={settings.knowledge_evidence_low_threshold ?? 0.78} onChange={(e) => onUpdateSettings("knowledge_evidence_low_threshold", Number(e.target.value))} /></div><div className="space-y-1"><SettingLabel help="evidence_high">Very high from</SettingLabel><Input type="number" min="0" max="1" step="0.01" value={settings.knowledge_evidence_high_threshold ?? 0.95} onChange={(e) => onUpdateSettings("knowledge_evidence_high_threshold", Number(e.target.value))} /></div><div className="space-y-1"><SettingLabel help="evidence_coverage">High-match coverage</SettingLabel><Input type="number" min="0" max="1" step="0.05" value={settings.knowledge_evidence_high_coverage ?? 0.9} onChange={(e) => onUpdateSettings("knowledge_evidence_high_coverage", Number(e.target.value))} /></div></div>
                    </CardContent></Card>

                    <Card><CardHeader><CardTitle className="text-base">Governed facets</CardTitle><CardDescription>Defines the shared facet keys the generation model may populate in its primary response. It is not a retrieval-only setting.</CardDescription></CardHeader><CardContent><div className="space-y-2"><div className="flex justify-between"><SettingLabel help="facet_schema">Facet schema</SettingLabel><Button size="sm" variant="ghost" onClick={() => saveJson("knowledge_facets_schema", facetsSchemaText)}>Save</Button></div><textarea className="w-full h-48 rounded-md border bg-background p-2 text-xs font-mono" value={facetsSchemaText} onChange={(e) => setFacetsSchemaText(e.target.value)} /><p className="text-[10px] text-muted-foreground">Only explicitly supported values are stored. Example: <code>"intake": "September 2026"</code>.</p></div></CardContent></Card>
                </TabsContent>

                <TabsContent value="maintenance" className="space-y-5 mt-5">
                    <KnowledgeHygieneCard settings={settings} onUpdateSettings={onUpdateSettings} />
                </TabsContent>

                <TabsContent value="retrieval" className="space-y-5 mt-5">
                    <Card><CardHeader><CardTitle className="text-base">Context retrieval</CardTitle><CardDescription>Always-on records are injected in full. All other matches are compact index entries that agents retrieve in full only when needed.</CardDescription></CardHeader><CardContent className="grid grid-cols-2 gap-4"><div className="space-y-1"><SettingLabel help="max_matches">Maximum matched records</SettingLabel><Input type="number" min="1" max="100" value={settings.context_knowledge_count ?? 30} onChange={(e) => onUpdateSettings("context_knowledge_count", Number(e.target.value) || 30)} /></div><div className="space-y-1"><SettingLabel help="relevance_floor">Relevance floor</SettingLabel><Input type="number" min="0" max="1" step="0.05" value={settings.context_knowledge_min_similarity ?? 0} onChange={(e) => onUpdateSettings("context_knowledge_min_similarity", Number(e.target.value))} /><p className="text-[10px] text-muted-foreground">0 ranks without excluding. Above 0, records without compatible embeddings are excluded.</p></div></CardContent></Card>
                    <Card><CardHeader><CardTitle className="text-base">Profile-derived facet ranking</CardTitle><CardDescription>Maps entity profile fields to generated facets. Matching values boost ranking and never remove otherwise relevant Knowledge.</CardDescription></CardHeader><CardContent><div className="space-y-2"><div className="flex justify-between"><SettingLabel help="profile_map">Profile-to-facet map</SettingLabel><Button size="sm" variant="ghost" onClick={() => saveJson("profile_facet_map", profileMapText)}>Save</Button></div><textarea className="w-full h-48 rounded-md border bg-background p-2 text-xs font-mono" value={profileMapText} onChange={(e) => setProfileMapText(e.target.value)} /></div></CardContent></Card>
                </TabsContent>

                <TabsContent value="operations" className="space-y-5 mt-5">
                    <KnowledgeOperations runs={runs} controls={controls} eligibleCounts={eligibleCounts} onRefresh={refreshStatus} settings={settings} />
                </TabsContent>
            </Tabs>
        </div>
    );
}

const OPERATION_DEFINITIONS = {
    embedding_backfill: { label: "Embedding backfill", job: "knowledge_embedding_backfill", eligibleKey: "embedding_backfill", defaultRecords: 25, maxRecords: 25, maxTotal: 10000000, defaultBatches: 10, calibrationCap: 250, button: "Start embedding backfill", description: "Generate missing or stale embeddings across interactions, memories, intelligence, and Knowledge." },
    knowledge_generation: { label: "Knowledge generation", job: "run_all_knowledge_generation", eligibleKey: "knowledge_generation", defaultRecords: 100, maxRecords: 1000, maxTotal: 1000000, defaultBatches: 1, calibrationCap: 250, button: "Generate Knowledge from source evidence", description: "Process eligible source evidence through every enabled Knowledge generation pathway." },
    hygiene_analysis: { label: "Knowledge hygiene analysis", job: "knowledge_hygiene_run", eligibleKey: "hygiene_analysis", defaultRecords: 250, maxRecords: 5000, maxTotal: 1000000, defaultBatches: 1, calibrationCap: 250, button: "Analyze Knowledge for consolidation", description: "Discover candidate relationships and cluster metrics. This analysis does not generate or apply a merge." },
    facet_backfill: { label: "Facet backfill", job: "backfill_facets", eligibleKey: "facet_backfill", defaultRecords: 25, maxRecords: 100, maxTotal: 1000000, defaultBatches: 10, calibrationCap: 250, button: "Backfill missing Knowledge facets", description: "Extract governed facets for active Knowledge records that currently have none." },
};

const JOB_LABELS = {
    ...Object.fromEntries(Object.values(OPERATION_DEFINITIONS).map(def => [def.job, def.label])),
    interaction_retention: "Interaction retention",
};

function KnowledgeOperations({ runs, controls, eligibleCounts, onRefresh, settings }) {
    const [operation, setOperation] = useState("embedding_backfill");
    const [recordsPerBatch, setRecordsPerBatch] = useState(OPERATION_DEFINITIONS.embedding_backfill.defaultRecords);
    const [runExtent, setRunExtent] = useState("limited");
    const [batchesPerRun, setBatchesPerRun] = useState(OPERATION_DEFINITIONS.embedding_backfill.defaultBatches);
    const [executionMode, setExecutionMode] = useState("synchronous_calibration");
    const [maxClusters, setMaxClusters] = useState(100);
    const [busy, setBusy] = useState(false);
    const definition = OPERATION_DEFINITIONS[operation];
    const eligible = Number(eligibleCounts?.[definition.eligibleKey] || 0);
    const latestRunFor = (job) => runs
        .filter(run => run.job === job)
        .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0];
    const latestOperation = latestRunFor(definition.job);
    const operationActive = ["running", "paused", "blocked"].includes(latestOperation?.status);
    const resolvedBatches = runExtent === "all" ? Math.ceil(eligible / Math.max(1, recordsPerBatch)) : Math.max(1, batchesPerRun);
    const totalRecords = runExtent === "all" ? eligible : recordsPerBatch * resolvedBatches;
    const calibrationCap = definition.calibrationCap || 250;
    const supportsInlineCalibration = operation === "embedding_backfill";

    const changeOperation = (value) => {
        const next = OPERATION_DEFINITIONS[value];
        setOperation(value); setRecordsPerBatch(next.defaultRecords); setBatchesPerRun(next.defaultBatches); setRunExtent("limited");
    };
    const start = async () => {
        if (recordsPerBatch < 1 || recordsPerBatch > definition.maxRecords) return toast.error(`Records per Batch must be between 1 and ${definition.maxRecords}`);
        if (totalRecords < 1) return toast.error("No eligible records are available for this operation");
        if (executionMode === "synchronous_calibration" && totalRecords > calibrationCap) return toast.error(`Calibration runs are limited to ${calibrationCap} records`);
        if (totalRecords > definition.maxTotal) return toast.error(`This run exceeds the ${definition.maxTotal.toLocaleString()} record safety limit`);
        setBusy(true);
        try {
            await setMaintenanceControl(definition.job, "run");
            const runMetadata = { records_per_batch: recordsPerBatch, batches_per_run: runExtent === "all" ? undefined : resolvedBatches, run_all: runExtent === "all", execution_mode: executionMode };
            let response;
            if (operation === "embedding_backfill") response = await backfillEmbeddings({ batch_size: recordsPerBatch, max_records: totalRecords, ...runMetadata });
            if (operation === "knowledge_generation") response = await triggerKnowledgeCheck(resolvedBatches > 1, { max_records: totalRecords, max_rounds: resolvedBatches, ...runMetadata });
            if (operation === "hygiene_analysis") response = await analyzeHygieneNow({ mode: "analysis_only", dry_run: true, max_records: totalRecords, max_clusters: maxClusters, ...runMetadata });
            if (operation === "facet_backfill") response = await triggerBackfillFacets({ batch_size: recordsPerBatch, max_records: totalRecords, ...runMetadata });
            toast.success(response?.data?.status === "completed" ? `${definition.label} calibration completed` : `${definition.label} queued`);
            await onRefresh();
        } catch (error) { toast.error(apiErrorMessage(error, `Could not start ${definition.label}`)); }
        finally { setBusy(false); }
    };
    const exportApproved = async () => {
        setBusy(true);
        try {
            const res = await exportKnowledgePack({ status: "active" }); const url = URL.createObjectURL(new Blob([res.data])); const a = document.createElement("a"); a.href=url; a.download="knowledge-pack.zip"; a.click(); URL.revokeObjectURL(url); toast.success("Approved Knowledge exported");
        } catch { toast.error("Could not export approved Knowledge"); }
        finally { setBusy(false); }
    };
    return <div className="space-y-5">
        <Card>
            <CardHeader><CardTitle className="text-base">Start a Knowledge operation</CardTitle><CardDescription>Choose one operation, define its bounded workload, review the estimate, and start it explicitly.</CardDescription></CardHeader>
            <CardContent className="space-y-4">
                <div className="max-w-md space-y-1"><SettingLabel help="operation_type">Operation</SettingLabel><Select value={operation} onValueChange={changeOperation}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.entries(OPERATION_DEFINITIONS).map(([key, item]) => <SelectItem key={key} value={key}>{item.label}</SelectItem>)}</SelectContent></Select><p className="text-[11px] text-muted-foreground">{definition.description}</p></div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="space-y-1"><SettingLabel help="execution_mode">Execution mode</SettingLabel><Select value={executionMode} onValueChange={setExecutionMode}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="synchronous_calibration">{supportsInlineCalibration ? "Synchronous calibration" : "Bounded calibration (queued)"}</SelectItem><SelectItem value="provider_batch" disabled>Provider batch (enable after calibration)</SelectItem></SelectContent></Select><p className="text-[10px] text-muted-foreground">{supportsInlineCalibration ? "Runs immediately and keeps this page waiting for the measured result." : "Queues a small bounded run and reports its result in operation history."}</p></div>
                    <div className="space-y-1"><SettingLabel help="records_per_batch">Records per Batch</SettingLabel><Input type="number" min="1" max={definition.maxRecords} value={recordsPerBatch} onChange={(e) => setRecordsPerBatch(Math.max(1, Math.min(definition.maxRecords, Number(e.target.value) || 1)))} /><p className="text-[10px] text-muted-foreground">Allowed for this operation: 1–{definition.maxRecords}.</p></div>
                    <div className="space-y-1"><SettingLabel help="batches_per_run">Batches per Run</SettingLabel><Select value={runExtent} onValueChange={setRunExtent}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="limited">Limit batches</SelectItem><SelectItem value="all">All eligible records</SelectItem></SelectContent></Select></div>
                    <div className="space-y-1"><SettingLabel help="batch_limit">Batch limit</SettingLabel><Input type="number" min="1" max="10000" disabled={runExtent === "all"} value={runExtent === "all" ? resolvedBatches || 0 : batchesPerRun} onChange={(e) => setBatchesPerRun(Math.max(1, Math.min(10000, Number(e.target.value) || 1)))} /><p className="text-[10px] text-muted-foreground">All uses a finite snapshot of currently eligible records.</p></div>
                </div>
                {operation === "hygiene_analysis" && <div className="max-w-xs space-y-1"><SettingLabel help="analysis_max_clusters">Maximum clusters inspected</SettingLabel><Input type="number" min="1" max="10000" value={maxClusters} onChange={(e) => setMaxClusters(Math.max(1, Math.min(10000, Number(e.target.value) || 1)))} /></div>}
                <div className="rounded-md border bg-muted/20 p-3 text-xs grid grid-cols-2 md:grid-cols-4 gap-3"><div><span className="text-muted-foreground">Eligible now</span><div className="font-medium">{eligible.toLocaleString()}</div></div><div><span className="text-muted-foreground">Records per Batch</span><div className="font-medium">{recordsPerBatch.toLocaleString()}</div></div><div><span className="text-muted-foreground">Batches per Run</span><div className="font-medium">{runExtent === "all" ? `All (${resolvedBatches})` : resolvedBatches}</div></div><div><span className="text-muted-foreground">Maximum records</span><div className="font-medium">{totalRecords.toLocaleString()}{executionMode === "synchronous_calibration" ? ` / ${calibrationCap} calibration cap` : ""}</div></div></div>
                <div className="flex gap-2 flex-wrap"><Button onClick={start} disabled={busy || operationActive || totalRecords < 1 || totalRecords > definition.maxTotal || (executionMode === "synchronous_calibration" && totalRecords > calibrationCap)}><Play className="w-4 h-4 mr-2" />{busy ? (supportsInlineCalibration ? "Running calibration…" : "Starting calibration…") : operationActive ? `${definition.label} already active` : supportsInlineCalibration ? `Run synchronous calibration` : `Run bounded calibration`}</Button><Button variant="outline" onClick={exportApproved} disabled={busy}><FileText className="w-4 h-4 mr-2" />Export approved Knowledge</Button></div>
                {executionMode === "synchronous_calibration" && totalRecords > calibrationCap && <p className="text-xs text-destructive">Reduce Records per Batch or Batches per Run: calibration is limited to {calibrationCap.toLocaleString()} records.</p>}
                {operation === "knowledge_generation" && <p className="text-[10px] text-muted-foreground">One input record is one eligible source-evidence record. Several inputs may produce one Knowledge record, or none when policy rejects the candidate. Output is therefore not one-to-one.</p>}
                {operation === "hygiene_analysis" && <p className="text-[10px] text-muted-foreground">Records are combined into the selected analysis window before candidate graph formation. Similarity discovers candidates only; it never applies a merge.</p>}
            </CardContent>
        </Card>
        <MaintenanceRunStatus runs={runs} controls={controls} onRefresh={onRefresh} />
        <KnowledgeRunHistory runs={runs} />
    </div>;
}

function MaintenanceRunStatus({ runs, controls, onRefresh }) {
    const [busy, setBusy] = useState(null);
    const labels = JOB_LABELS;
    const controlFor = (job) => controls.find((item) => item.job === job)?.command || "run";
    const setControl = async (job, command) => {
        setBusy(`${job}:${command}`);
        try { await setMaintenanceControl(job, command); toast.success(command === "run" ? "Run state cleared. Start the next bounded run to resume." : `${labels[job] || job} will ${command} at its next safe checkpoint.`); onRefresh(); }
        catch (error) { toast.error(apiErrorMessage(error, "Could not update run control")); }
        finally { setBusy(null); }
    };
    const activeJobs = Object.keys(labels).map(job => ({
        job,
        latest: runs.filter(run => run.job === job).sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0],
    })).filter(item => ["running", "paused", "blocked"].includes(item.latest?.status));
    return <Card className="border-amber-500/40 bg-amber-500/5">
        <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><BarChart3 className="w-4 h-4" />Active Knowledge operations</CardTitle><CardDescription>Updates every 5 seconds. Pause and cancel take effect after the current safe processing unit.</CardDescription></CardHeader>
        <CardContent className="space-y-3">
            {activeJobs.map(({ job, latest }) => {
                const command = controlFor(job);
                const total = Number(latest?.progress_total || 0);
                const completed = Number(latest?.progress_completed || 0);
                const progress = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : null;
                return <div key={job} className="rounded-md border p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2"><span className="text-xs font-medium">{labels[job]}</span><Badge variant="outline">{latest?.status || "idle"}</Badge></div>
                    <div className="text-[11px] text-muted-foreground flex flex-wrap gap-x-4 gap-y-1"><span>Control: {command}</span>{progress !== null && <span>Progress: {completed}/{total} ({progress}%)</span>}{latest?.estimated_tokens && <span>Est. tokens: {Number(latest.estimated_tokens).toLocaleString()}</span>}{latest?.estimated_cost_usd != null && <span>Est. cost: ${Number(latest.estimated_cost_usd).toFixed(4)}</span>}{latest?.detail?.checkpoint?.last_record_id && <span>Checkpoint: {String(latest.detail.checkpoint.last_record_id).slice(0, 8)}…</span>}</div>
                    {latest?.reason_code && <div className="text-[11px] text-amber-700 dark:text-amber-300">{latest.reason_code}</div>}
                    <div className="flex gap-2">{latest?.status === "running" && command === "run" && <Button size="sm" variant="outline" disabled={busy === `${job}:pause`} onClick={() => setControl(job, "pause")}>Pause</Button>}{latest?.status === "running" && !["cancel"].includes(command) && <Button size="sm" variant="outline" disabled={busy === `${job}:cancel`} onClick={() => setControl(job, "cancel")}>Cancel</Button>}{latest?.status === "paused" && <Button size="sm" variant="outline" disabled={busy === `${job}:run`} onClick={() => setControl(job, "run")}>Resume</Button>}{command !== "run" && latest?.status === "running" && <span className="text-[11px] text-muted-foreground self-center">{command === "pause" ? "Pausing at checkpoint…" : "Stopping at checkpoint…"}</span>}</div>
                </div>;
            })}
            {!activeJobs.length && <p className="text-xs text-muted-foreground">No Knowledge operations are currently running or paused.</p>}
        </CardContent>
    </Card>;
}

function KnowledgeRunHistory({ runs }) {
    const relevant = runs.filter(run => JOB_LABELS[run.job]).slice(0, 20);
    return <Card><CardHeader><CardTitle className="text-base">Knowledge operation history</CardTitle><CardDescription>Inputs, outputs, checkpoints, costs, and stop reasons for recent operations.</CardDescription></CardHeader><CardContent className="space-y-2">
        {relevant.map(run => { const result = run.detail?.result || {}; const started = run.started_at ? new Date(run.started_at) : null; const finished = run.finished_at ? new Date(run.finished_at) : null; const duration = started && finished ? `${Math.max(0, Math.round((finished - started) / 1000))}s` : run.status === "running" ? "Running" : "—"; const batchInput = run.detail?.records_per_batch ? `${run.detail.records_per_batch} × ${run.detail.run_all ? "all" : (run.detail.batches_per_run || "—")}` : "—"; const outputs = run.job === "backfill_facets" ? result.enriched : run.job === "knowledge_embedding_backfill" ? (result.succeeded ?? run.records_created) : run.job === "knowledge_hygiene_run" ? result.proposals_created : run.records_created; return <details key={run.id} className="rounded-md border p-3 text-xs"><summary className="cursor-pointer flex items-center justify-between gap-3"><span><strong>{JOB_LABELS[run.job]}</strong><span className="text-muted-foreground ml-2">{run.created_at ? new Date(run.created_at).toLocaleString() : ""}</span></span><Badge variant="outline">{run.status || run.outcome}</Badge></summary><div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-3 text-muted-foreground"><div>Requested input<br/><span className="text-foreground">{batchInput}</span></div><div>Processed<br/><span className="text-foreground">{Number(run.progress_completed || result.processed || 0).toLocaleString()}</span></div><div>Outputs<br/><span className="text-foreground">{Number(outputs || 0).toLocaleString()}</span></div><div>Failed<br/><span className="text-foreground">{Number(run.progress_failed || result.failed || 0).toLocaleString()}</span></div><div>Duration / estimated cost<br/><span className="text-foreground">{duration}{run.estimated_cost_usd != null ? ` / $${Number(run.estimated_cost_usd).toFixed(4)}` : ""}</span></div><div>Stop reason<br/><span className="text-foreground">{run.reason_code || "—"}</span></div></div>{run.detail && <pre className="mt-3 max-h-48 overflow-auto rounded bg-muted/30 p-2 text-[10px] whitespace-pre-wrap">{JSON.stringify(run.detail, null, 2)}</pre>}</details>; })}
        {!relevant.length && <p className="text-xs text-muted-foreground">No Knowledge operation history is available yet.</p>}
    </CardContent></Card>;
}

// ── Knowledge Hygiene & Consolidation settings card ──────────────────────────
// Candidate similarity only DISCOVERS related records; the merge decision
// always comes from the category-aware LLM proposal + review. First rollout
// is manual_only; auto modes are exposed but disabled by default.
function KnowledgeHygieneCard({ settings, onUpdateSettings }) {
    const CATEGORIES = ["best_practices", "lessons_learned", "trade_knowledge", "skill", "playbook"];
    const enabledCats = settings.knowledge_hygiene_enabled_categories || CATEGORIES;
    const catPolicies = settings.knowledge_hygiene_category_policies || {};

    const toggleCategory = (cat) => {
        const next = enabledCats.includes(cat) ? enabledCats.filter((c) => c !== cat) : [...enabledCats, cat];
        onUpdateSettings("knowledge_hygiene_enabled_categories", next);
    };

    return (
        <Card>
            <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                    <GitMerge className="w-5 h-5 text-rose-500" />
                    <CardTitle className="text-lg">Knowledge Hygiene & Consolidation</CardTitle>
                </div>
                <CardDescription className="text-xs mt-1.5">
                    Consolidation groups related records and proposes a stronger canonical record via a category-aware LLM. Candidate similarity finds related records — it never decides a merge.
                </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
                <div className="flex items-center justify-between">
                    <div className="space-y-0.5 pr-4">
                        <SettingLabel help="hygiene_enabled" className="text-xs font-mono">Knowledge hygiene enabled</SettingLabel>
                        <p className="text-[10px] text-muted-foreground">Master switch for candidate discovery + proposals.</p>
                    </div>
                    <Switch
                        checked={settings.knowledge_hygiene_enabled !== undefined ? settings.knowledge_hygiene_enabled : true}
                        onCheckedChange={(v) => onUpdateSettings("knowledge_hygiene_enabled", v)}
                    />
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                        <SettingLabel help="hygiene_mode" className="text-xs font-mono">Mode</SettingLabel>
                        <Select value={settings.knowledge_hygiene_mode || "manual_only"} onValueChange={(v) => onUpdateSettings("knowledge_hygiene_mode", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="analysis_only">Analysis only (no proposals)</SelectItem>
                                <SelectItem value="proposal_only">Proposal only (no apply)</SelectItem>
                                <SelectItem value="manual_only">Manual (review + apply) — recommended</SelectItem>
                                <SelectItem value="auto_conservative">Auto (conservative)</SelectItem>
                                <SelectItem value="auto_synthesis">Auto (synthesis)</SelectItem>
                            </SelectContent>
                        </Select>
                        <p className="text-[10px] text-muted-foreground">Auto modes apply only when policy gates pass (high confidence, no contradictions). Start manual.</p>
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="candidate_similarity" className="text-xs font-mono">Candidate similarity</SettingLabel>
                        <Input type="number" step="0.01" min="0" max="1"
                            value={settings.knowledge_hygiene_similarity_threshold ?? 0.82}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_similarity_threshold", Number(e.target.value))} />
                        <p className="text-[10px] text-muted-foreground">0–1 edge threshold for grouping candidates. Finds related records; does NOT decide merges.</p>
                    </div>
                </div>

                <div className="grid grid-cols-4 gap-3">
                    <div className="space-y-1">
                        <SettingLabel help="cluster_min" className="text-xs font-mono">Min cluster</SettingLabel>
                        <Input type="number" min="2" value={settings.knowledge_hygiene_min_cluster_size ?? 2}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_min_cluster_size", parseInt(e.target.value) || 2)} />
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="cluster_max" className="text-xs font-mono">Max cluster</SettingLabel>
                        <Input type="number" min="2" max="20" value={settings.knowledge_hygiene_max_cluster_size ?? 5}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_max_cluster_size", parseInt(e.target.value) || 5)} />
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="cohesion" className="text-xs font-mono">Min cohesion</SettingLabel>
                        <Input type="number" step="0.01" min="0" max="1" value={settings.knowledge_hygiene_min_cluster_cohesion ?? 0.72}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_min_cluster_cohesion", Number(e.target.value))} />
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="weak_link" className="text-xs font-mono">Weak-link</SettingLabel>
                        <Input type="number" step="0.01" min="0" max="1" value={settings.knowledge_hygiene_weak_link_threshold ?? 0.65}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_weak_link_threshold", Number(e.target.value))} />
                    </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                    <div className="space-y-1">
                        <SettingLabel help="preview_ttl" className="text-xs font-mono">Preview TTL (min)</SettingLabel>
                        <Input type="number" min="5" max="1440" value={settings.knowledge_hygiene_preview_ttl_minutes ?? 60}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_preview_ttl_minutes", parseInt(e.target.value) || 60)} />
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="auto_confidence" className="text-xs font-mono">Min auto-confidence</SettingLabel>
                        <Input type="number" step="0.01" min="0" max="1" value={settings.knowledge_hygiene_min_auto_confidence ?? 0.9}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_min_auto_confidence", Number(e.target.value))} />
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="contradiction_policy" className="text-xs font-mono">Contradiction policy</SettingLabel>
                        <Select value={settings.knowledge_hygiene_contradiction_policy || "manual_review"} onValueChange={(v) => onUpdateSettings("knowledge_hygiene_contradiction_policy", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="manual_review">Manual review</SelectItem>
                                <SelectItem value="keep_separate">Keep separate</SelectItem>
                                <SelectItem value="warn_and_merge">Warn and merge</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>

                <div className="space-y-1">
                    <SettingLabel help="consolidation_categories" className="text-xs font-mono">Categories enabled for consolidation</SettingLabel>
                    <div className="flex flex-wrap gap-2 mt-1">
                        {CATEGORIES.map((cat) => (
                            <Badge key={cat} variant={enabledCats.includes(cat) ? "default" : "outline"} className="cursor-pointer" onClick={() => toggleCategory(cat)}>
                                {cat.replace(/_/g, " ")}
                            </Badge>
                        ))}
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                        <SettingLabel help="canonical_strategy" className="text-xs font-mono">Default canonical strategy</SettingLabel>
                        <Select
                            value={settings.knowledge_hygiene_default_canonical_strategy || "update_existing"}
                            onValueChange={(v) => onUpdateSettings("knowledge_hygiene_default_canonical_strategy", v)}
                        >
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="update_existing">Update selected canonical</SelectItem>
                                <SelectItem value="create_new">Create new canonical</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-1">
                        <SettingLabel help="embedding_version" className="text-xs font-mono">Embedding version</SettingLabel>
                        <Input type="number" min="1"
                            value={settings.knowledge_hygiene_embedding_version ?? 2}
                            onChange={(e) => onUpdateSettings("knowledge_hygiene_embedding_version", parseInt(e.target.value) || 1)} />
                    </div>
                </div>

                <div className="space-y-2">
                    <SettingLabel help="category_automation" className="text-xs font-mono">Category automation policies</SettingLabel>
                    <p className="text-[10px] text-muted-foreground">A category remains manual until explicitly enabled, even when the global mode is automatic.</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        {CATEGORIES.map((cat) => (
                            <div key={cat} className="flex items-center justify-between gap-2 rounded-md border p-2">
                                <span className="text-xs">{cat.replace(/_/g, " ")}</span>
                                <Select
                                    value={catPolicies[cat] || "manual_only"}
                                    onValueChange={(v) => onUpdateSettings("knowledge_hygiene_category_policies", { ...catPolicies, [cat]: v })}
                                >
                                    <SelectTrigger className="w-[165px] h-8"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="manual_only">Manual only</SelectItem>
                                        <SelectItem value="auto_conservative">Auto conservative</SelectItem>
                                        <SelectItem value="auto_synthesis">Auto synthesis</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        ))}
                    </div>
                </div>

                <div className="flex items-center justify-between border-t pt-4">
                    <div className="space-y-0.5 pr-4">
                        <SettingLabel help="creation_time" className="text-xs font-mono">Post-create hygiene preview</SettingLabel>
                        <p className="text-[10px] text-muted-foreground">After an eligible Knowledge record is created, queue a non-mutating consolidation preview. This is separate from the pre-generation evidence gate and never merges directly.</p>
                    </div>
                    <Switch
                        checked={settings.knowledge_hygiene_creation_time_enabled === true}
                        onCheckedChange={(v) => onUpdateSettings("knowledge_hygiene_creation_time_enabled", v)}
                    />
                </div>

            </CardContent>
        </Card>
);
}


