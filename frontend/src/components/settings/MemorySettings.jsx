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
import { OutboundWebhooksSettings } from "./OutboundWebhooksSettings";

// ─── Raw Interactions Tab ───────────────────────────────────────────────────
function RawInteractionsTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, modelLists, fetchingModels, fetchErrors, onFetchModels }) {
    const embeddingConfig = llmConfigs.find((c) => c.task_type === "embedding");
    const visionConfig = llmConfigs.find((c) => c.task_type === "vision");

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <Zap className="w-5 h-5 text-amber-500" />
                    Raw Interactions
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Controls how raw interactions are received, parsed, and embedded before they become structured memories.
                </p>
            </div>

            {/* Vision Processing */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <ImageIcon className="w-5 h-5 text-purple-500" />
                        <CardTitle className="text-lg">Vision Processing</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Configure how images and documents are processed by vision AI models.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Enable Vision Processing</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Allow processing image/document attachments from interactions
                            </p>
                        </div>
                        <Switch
                            checked={settings.vision_enabled !== false} // default true or whatever user has
                            onCheckedChange={(v) => onUpdateSettings("vision_enabled", v)}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Vision / Document Parsing Task Assignment */}
            {visionConfig && (
                <InlineTaskConfigAccordion
                    config={visionConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[visionConfig.id] || []}
                    loadingModels={fetchingModels[visionConfig.id]}
                    error={fetchErrors[visionConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}

            {/* Embedding / Vectorization */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Layers className="w-5 h-5 text-indigo-500" />
                        <CardTitle className="text-lg">Interaction Embeddings</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Configure vectorization settings for raw interaction text.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between border-b pb-4">
                        <div className="space-y-0.5">
                            <Label>Enable Interaction Embeddings</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Generate vector embeddings for raw interactions to allow for deep semantic search.
                            </p>
                        </div>
                        <Switch
                            checked={settings.interaction_embeddings_enabled !== false}
                            onCheckedChange={(v) => onUpdateSettings("interaction_embeddings_enabled", v)}
                        />
                    </div>
                    
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
                </CardContent>
            </Card>

            {/* Embedding Task Assignment */}
            {embeddingConfig && (
                <InlineTaskConfigAccordion
                    config={embeddingConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[embeddingConfig.id] || []}
                    loadingModels={fetchingModels[embeddingConfig.id]}
                    error={fetchErrors[embeddingConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}

            {/* Rate Limiting */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Zap className="w-5 h-5 text-amber-500" />
                        <CardTitle className="text-lg">Rate Limiting</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Control API usage by agents
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Enable Rate Limiting</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Limit requests per agent
                            </p>
                        </div>
                        <Switch
                            checked={settings.rate_limit_enabled}
                            onCheckedChange={(v) => onUpdateSettings("rate_limit_enabled", v)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Requests per Minute</Label>
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
                </CardContent>
            </Card>

            {/* Outbound Webhooks */}
            <OutboundWebhooksSettings />
        </div>
    );
}

// ─── Memory Generation Tab ──────────────────────────────────────────────────
function MemoryGenerationTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, modelLists, fetchingModels, fetchErrors, onFetchModels }) {
    const [isTriggering, setIsTriggering] = useState(false);
    const nerConfig = llmConfigs.find((c) => c.task_type === "entity_extraction");
    const summarizationConfig = llmConfigs.find((c) => c.task_type === "summarization");
    const memoryGenConfig = llmConfigs.find((c) => c.task_type === "memory_generation");

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
                    Memory Generation
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Transforms raw interactions into structured daily memories via NER and LLM summarization.
                </p>
            </div>

            {/* Memory Generation Schedule */}
            <Card>
                <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <Clock className="w-5 h-5 text-blue-500" />
                            <CardTitle className="text-lg">Memory Generation Settings</CardTitle>
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
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Memory Generation Mode</Label>
                        <Select
                            value={settings.memory_generation_mode || "ner_and_raw"}
                            onValueChange={(v) =>
                                onUpdateSettings("memory_generation_mode", v)
                            }
                        >
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="ner_and_raw">
                                    NER + Raw interactions → LLM
                                </SelectItem>
                                <SelectItem value="ner_only">
                                    NER output only → LLM
                                </SelectItem>
                            </SelectContent>
                        </Select>
                        <p className="text-[10px] text-muted-foreground">
                            <strong>NER + Raw</strong>: richer context, better summaries. &nbsp;
                            <strong>NER only</strong>: structured signals only, no raw text sent to LLM.
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Memory Generation Task Assignment */}
            {memoryGenConfig && (
                <InlineTaskConfigAccordion
                    config={memoryGenConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[memoryGenConfig.id] || []}
                    loadingModels={fetchingModels[memoryGenConfig.id]}
                    error={fetchErrors[memoryGenConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}

            {/* NER Task Assignment */}
            {nerConfig && (
                <InlineTaskConfigAccordion
                    config={nerConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[nerConfig.id] || []}
                    loadingModels={fetchingModels[nerConfig.id]}
                    error={fetchErrors[nerConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}

            {/* Summarization Task Assignment */}
            {summarizationConfig && (
                <InlineTaskConfigAccordion
                    config={summarizationConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[summarizationConfig.id] || []}
                    loadingModels={fetchingModels[summarizationConfig.id]}
                    error={fetchErrors[summarizationConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}
        </div>
    );
}

// ─── Knowledge Generation Tab ─────────────────────────────────────────────────
function KnowledgeGenerationTab({ settings, onUpdateSettings, llmConfigs, llmProviders, onSaveConfig, modelLists, fetchingModels, fetchErrors, onFetchModels }) {
    const insightConfig = llmConfigs.find((c) => c.task_type === "insight_generation");
    const piiConfig = llmConfigs.find((c) => c.task_type === "pii_scrubbing");

    return (
        <div className="space-y-6">
            <div className="mb-2">
                <h3 className="text-lg font-semibold flex items-center gap-2">
                    <GraduationCap className="w-5 h-5 text-indigo-500" />
                    Knowledge Generation
                </h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Extracts high-level knowledge (Lessons) from memory records and sanitizes data.
                </p>
            </div>

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

            {/* PII Scrubbing Task Assignment */}
            {piiConfig && (
                <InlineTaskConfigAccordion
                    config={piiConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[piiConfig.id] || []}
                    loadingModels={fetchingModels[piiConfig.id]}
                    error={fetchErrors[piiConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}

            {/* Lesson Mining */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <GraduationCap className="w-5 h-5 text-green-500" />
                        <CardTitle className="text-lg">Lesson Mining</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Automatic lesson generation from accumulated confirmed private lessons
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Auto-extract Lessons</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Automatically mine lessons from interactions
                            </p>
                        </div>
                        <Switch
                            checked={settings.auto_lesson_enabled}
                            onCheckedChange={(v) => onUpdateSettings("auto_lesson_enabled", v)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">
                            Lesson Threshold (N private lessons)
                        </Label>
                        <Input
                            type="number"
                            min={2}
                            value={settings.lesson_threshold || 5}
                            onChange={(e) =>
                                onUpdateSettings("lesson_threshold", parseInt(e.target.value))
                            }
                            disabled={!settings.auto_lesson_enabled}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Generate a public lesson after this many confirmed private lessons accumulate.
                        </p>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">
                            Lesson Trigger (days, optional)
                        </Label>
                        <Input
                            type="number"
                            min={1}
                            placeholder="Leave blank to use count only"
                            value={settings.lesson_trigger_days || ""}
                            onChange={(e) => {
                                const v = e.target.value;
                                onUpdateSettings("lesson_trigger_days", v ? parseInt(v) : null);
                            }}
                            disabled={!settings.auto_lesson_enabled}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Also trigger if oldest unused private lesson is this many days old (min 2).
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Insight / Private Lesson Generation Task Assignment */}
            {insightConfig && (
                <InlineTaskConfigAccordion
                    config={insightConfig}
                    llmProviders={llmProviders}
                    onSaveConfig={onSaveConfig}
                    models={modelLists[insightConfig.id] || []}
                    loadingModels={fetchingModels[insightConfig.id]}
                    error={fetchErrors[insightConfig.id]}
                    onFetchModels={onFetchModels}
                />
            )}
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
    onSaveConfig,
    onUpdateMemorySettings,
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
        onSaveConfig,
        modelLists,
        fetchingModels,
        fetchErrors,
        onFetchModels: handleFetchModels
    };

    return (
        <div className="max-w-4xl">
            <Tabs defaultValue="raw_interactions" className="w-full">
                <TabsList className="grid w-full grid-cols-4 mb-8">
                    <TabsTrigger value="raw_interactions" className="gap-2">
                        <Zap className="w-4 h-4" />
                        Raw Interactions
                    </TabsTrigger>
                    <TabsTrigger value="memory_generation" className="gap-2">
                        <Brain className="w-4 h-4" />
                        Memory Generation
                    </TabsTrigger>
                    <TabsTrigger value="knowledge_generation" className="gap-2">
                        <GraduationCap className="w-4 h-4" />
                        Knowledge Gen.
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

                <TabsContent value="knowledge_generation">
                    <KnowledgeGenerationTab {...tabProps} />
                </TabsContent>

                <TabsContent value="analytics">
                    <AnalyticsTab />
                </TabsContent>
            </Tabs>

        </div>
    );
}
