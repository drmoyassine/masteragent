import React, { useState, useCallback } from "react";
import {
    Clock, Play, ShieldAlert, Zap, GraduationCap, Brain,
    Layers, Scissors, FileText, Eye, AlertCircle, CheckCircle2,
    Edit2, Cpu, Sparkles, BarChart3, Image as ImageIcon
} from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { triggerMemoryGeneration, fetchProviderModels } from "@/lib/api";
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

// ─── Interactions Tab ───────────────────────────────────────────────────
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

                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Cpu className="w-4 h-4 text-indigo-500" />
                            Queue Dynamics
                        </h4>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Max Background Concurrency</Label>
                            <p className="text-[10px] text-muted-foreground mb-2 whitespace-nowrap overflow-hidden text-ellipsis w-full">
                                Parallel BullMQ execution workers. Adjust if hitting LLM limits.
                            </p>
                            <Input
                                type="number"
                                min="1"
                                max="50"
                                value={settings.interactions_queue_concurrency || 5}
                                onChange={(e) =>
                                    onUpdateSettings(
                                        "interactions_queue_concurrency",
                                        parseInt(e.target.value) || 5
                                    )
                                }
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

// ─── Memories Tab ──────────────────────────────────────────────────
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

            {/* Memories Schedule */}
            <Card>
                <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <Clock className="w-5 h-5 text-blue-500" />
                            <CardTitle className="text-lg">Memories Settings</CardTitle>
                        </div>
                        <CardDescription className="text-xs mt-1.5">
                            When and how daily memories are generated from interactions
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
                <CardContent className="space-y-4">
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

                </CardContent>
            </Card>

            {/* Prior Context Injection */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5 text-purple-500" />
                        <CardTitle className="text-lg">Prior Context Injection</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Controls how many previous memories are injected as context when generating new memories.
                        Higher counts provide more continuity but increase token usage.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
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
                </CardContent>
            </Card>
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

            {/* Processing Throughput */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Processing Throughput</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Parallel BullMQ workers and retry mechanics for Memories.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Cpu className="w-4 h-4 text-indigo-500" />
                            Queue Dynamics
                        </h4>
                        <div className="space-y-2">
                            <Label className="text-xs font-mono">Max Concurrency</Label>
                            <Input
                                type="number"
                                min="1"
                                max="50"
                                value={settings.memory_queue_concurrency || 1}
                                onChange={(e) =>
                                    onUpdateSettings(
                                        "memory_queue_concurrency",
                                        parseInt(e.target.value) || 1
                                    )
                                }
                            />
                        </div>
                    </div>
                    <div className="space-y-4 pt-2">
                        <h4 className="text-sm font-semibold flex items-center gap-1.5 border-b pb-1">
                            <Play className="w-4 h-4 text-blue-500" />
                            Job Retry Policy
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
        </div>
    );
}


// ─── Intelligence Tab ───────────────────────────────────────────────────
function IntelligenceTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
    const privatePipelineNodes = llmConfigs.filter((c) => c.pipeline_stage === "intelligence").sort((a,b) => a.execution_order - b.execution_order);

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

            {/* Prior Context Injection */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5 text-purple-500" />
                        <CardTitle className="text-lg">Prior Intelligence Context</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Existing intelligence items injected during generation so the LLM avoids creating duplicates.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
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
                            Helps the LLM generate novel intelligence that builds on — rather than restates — established patterns.
                        </p>
                    </div>
                    <p className="text-[10px] text-muted-foreground border-t pt-2">
                        All prior context is injected as labeled sections in the LLM prompt to prevent redundant generation.
                    </p>
                </CardContent>
            </Card>

            {/* Intelligence Pipeline Assignment */}
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

// ─── Knowledge Tab ──────────────────────────────────────────────────────
function KnowledgeTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, onDeleteConfig, onAddConfig, modelLists, fetchingModels, fetchErrors, onFetchModels, onReorderPipeline }) {
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

            {/* Prior Knowledge Context */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Prior Knowledge Context</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Existing knowledge items injected via semantic search during generation to prevent duplication.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Semantic Matches</Label>
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
                            Most similar existing knowledge items found via pgvector cosine search.
                            Injected as "Existing Knowledge" so the LLM generates novel, non-redundant items.
                        </p>
                    </div>
                    <p className="text-[10px] text-muted-foreground border-t pt-2">
                        Knowledge is global (not entity-scoped). Set to 0 to disable deduplication context entirely.
                    </p>
                </CardContent>
            </Card>

            {/* PII Privacy */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-red-500" />
                        <CardTitle className="text-lg">PII Privacy</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Configure PII scrubbing layer for knowledge sharing.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Enable PII Scrubbing</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Automatically strip PII from shared data
                            </p>
                        </div>
                        <Switch
                            checked={settings.pii_scrubbing_enabled}
                            onCheckedChange={(v) => onUpdateSettings("pii_scrubbing_enabled", v)}
                        />
                    </div>
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Auto-share Scrubbed</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Automatically share PII-stripped memories
                            </p>
                        </div>
                        <Switch
                            checked={settings.auto_share_scrubbed}
                            onCheckedChange={(v) => onUpdateSettings("auto_share_scrubbed", v)}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Knowledge Mining */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <GraduationCap className="w-5 h-5 text-green-500" />
                        <CardTitle className="text-lg">Knowledge Mining</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Automatic knowledge generation from accumulated confirmed intelligence items
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Auto-extract Knowledge</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Automatically mine knowledge from intelligence
                            </p>
                        </div>
                        <Switch
                            checked={settings.auto_knowledge_enabled}
                            onCheckedChange={(v) => onUpdateSettings("auto_knowledge_enabled", v)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">
                            Knowledge Threshold (N intelligence items)
                        </Label>
                        <Input
                            type="number"
                            min={2}
                            value={settings.knowledge_threshold || 5}
                            onChange={(e) =>
                                onUpdateSettings("knowledge_threshold", parseInt(e.target.value))
                            }
                            disabled={!settings.auto_knowledge_enabled}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Generate a knowledge item after this many confirmed intelligence items accumulate.
                        </p>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">
                            Knowledge Trigger (days, optional)
                        </Label>
                        <Input
                            type="number"
                            min={1}
                            placeholder="Leave blank to use count only"
                            value={settings.knowledge_trigger_days || ""}
                            onChange={(e) => {
                                const v = e.target.value;
                                onUpdateSettings("knowledge_trigger_days", v ? parseInt(v) : null);
                            }}
                            disabled={!settings.auto_knowledge_enabled}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Also trigger if oldest unused intelligence is this many days old (min 2).
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Knowledge Pipeline Assignment */}
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

            {/* Queue Dynamics */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Cpu className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Queue Dynamics</CardTitle>
                    </div>
                    <CardDescription className="text-xs mt-1.5">
                        Parallel BullMQ execution workers for knowledge generation.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Max Concurrency</Label>
                        <Input
                            type="number"
                            min="1"
                            max="50"
                            value={settings.knowledge_queue_concurrency || 1}
                            onChange={(e) =>
                                onUpdateSettings(
                                    "knowledge_queue_concurrency",
                                    parseInt(e.target.value) || 1
                                )
                            }
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}

// ─── Analytics Tab ───────────────────────────────────────────────────────────
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

// ─── Main Component ──────────────────────────────────────────────────────────
export function MemorySettings({
    settings,
    llmConfigs,
    llmProviders,
    onUpdateSettings,
    onSaveConfig, onDeleteConfig, onAddConfig,
    onUpdateMemorySettings,
    activeTab = "raw_interactions",
    onTabChange,
    onReorderPipeline
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
        onReorderPipeline
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


