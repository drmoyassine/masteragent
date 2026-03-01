import React from "react";
import { Brain, Layers, Eye, Users, EyeOff, AlertCircle, CheckCircle2, Cpu } from "lucide-react";
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

const TASK_TYPE_LABELS = {
    summarization: { label: "Summarization", icon: Brain, color: "bg-blue-500" },
    embedding: { label: "Embeddings", icon: Layers, color: "bg-green-500" },
    vision: { label: "Vision/Doc Parsing", icon: Eye, color: "bg-purple-500" },
    entity_extraction: { label: "Entity Extraction (NER)", icon: Users, color: "bg-amber-500" },
    pii_scrubbing: { label: "PII Scrubbing", icon: EyeOff, color: "bg-red-500" },
};

const PROVIDER_OPTIONS = [
    { value: "openai", label: "OpenAI" },
    { value: "anthropic", label: "Anthropic" },
    { value: "gemini", label: "Google Gemini" },
    { value: "gliner", label: "GLiNER2 (NER)" },
    { value: "zendata", label: "Zendata (PII)" },
    { value: "custom", label: "Custom API" },
];

export function LLMProviderSettings({
    llmConfigs,
    editingConfig,
    setEditingConfig,
    showApiKey,
    setShowApiKey,
    onSaveConfig
}) {
    return (
        <div className="space-y-4 max-w-4xl">
            <Card>
                <CardHeader>
                    <CardTitle>LLM API Configurations</CardTitle>
                    <CardDescription>
                        Configure API keys and endpoints for each task type. These are used by the Memory System for processing data.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    {llmConfigs.map((config) => {
                        const taskInfo = TASK_TYPE_LABELS[config.task_type] || { label: config.task_type, icon: Brain, color: "bg-gray-500" };
                        const TaskIcon = taskInfo.icon;
                        const isEditing = editingConfig?.id === config.id;

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
                                                <p className="text-sm text-muted-foreground">{config.name} ({config.provider})</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            {config.api_key_preview ? (
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
                                                onClick={() => setEditingConfig(isEditing ? null : config)}
                                            >
                                                {isEditing ? "Cancel" : "Edit"}
                                            </Button>
                                        </div>
                                    </div>

                                    {isEditing && (
                                        <div className="mt-4 pt-4 border-t space-y-4">
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="space-y-2">
                                                    <Label>Provider</Label>
                                                    <Select
                                                        value={editingConfig.provider}
                                                        onValueChange={(v) => setEditingConfig({ ...editingConfig, provider: v })}
                                                    >
                                                        <SelectTrigger>
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {PROVIDER_OPTIONS.map((opt) => (
                                                                <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                                <div className="space-y-2">
                                                    <Label>Model Name</Label>
                                                    <Input
                                                        value={editingConfig.model_name || ""}
                                                        onChange={(e) => setEditingConfig({ ...editingConfig, model_name: e.target.value })}
                                                        placeholder="e.g., gpt-4o-mini"
                                                    />
                                                </div>
                                            </div>
                                            <div className="space-y-2">
                                                <Label>API Base URL</Label>
                                                <Input
                                                    value={editingConfig.api_base_url || ""}
                                                    onChange={(e) => setEditingConfig({ ...editingConfig, api_base_url: e.target.value })}
                                                    placeholder="https://api.openai.com/v1"
                                                />
                                            </div>
                                            <div className="space-y-2">
                                                <Label>API Key</Label>
                                                <div className="flex gap-2">
                                                    <Input
                                                        type={showApiKey[config.id] ? "text" : "password"}
                                                        value={editingConfig.api_key || ""}
                                                        onChange={(e) => setEditingConfig({ ...editingConfig, api_key: e.target.value })}
                                                        placeholder="Enter API key"
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
                                            <Button onClick={() => onSaveConfig(config.id, editingConfig)}>
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
        </div>
    );
}
