import React, { useState } from "react";
import { Settings, Scissors, GraduationCap, ShieldAlert, Zap, Clock, Brain, Play } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { triggerMemoryGeneration } from "@/lib/api";
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

export function GeneralMemorySettings({ settings, onUpdateSettings }) {
    const [isTriggering, setIsTriggering] = useState(false);

    const handleRunNow = async () => {
        setIsTriggering(true);
        try {
            await triggerMemoryGeneration(true); // include_today = true
            toast.success("Generation task scheduled in background. Check docker logs.");
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Failed to trigger task");
        } finally {
            setIsTriggering(false);
        }
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl">

            {/* Memory Generation Schedule */}
            <Card>
                <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                        <div className="flex items-center gap-2">
                            <Clock className="w-5 h-5 text-blue-500" />
                            <CardTitle className="text-lg">Memory Generation</CardTitle>
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
                            onChange={(e) => onUpdateSettings("memory_generation_time", e.target.value)}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Time of day to process pending interactions into daily memory records.
                        </p>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Memory Generation Mode</Label>
                        <Select
                            value={settings.memory_generation_mode || "ner_and_raw"}
                            onValueChange={(v) => onUpdateSettings("memory_generation_mode", v)}
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

            {/* Lesson Mining */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <GraduationCap className="w-5 h-5 text-green-500" />
                        <CardTitle className="text-lg">Lesson Mining</CardTitle>
                    </div>
                    <CardDescription className="text-xs">
                        Automatic lesson generation from accumulated confirmed insights
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Auto-extract Lessons</Label>
                            <p className="text-[10px] text-muted-foreground">Automatically mine lessons from interactions</p>
                        </div>
                        <Switch
                            checked={settings.auto_lesson_enabled}
                            onCheckedChange={(v) => onUpdateSettings("auto_lesson_enabled", v)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Lesson Threshold (N insights)</Label>
                        <Input
                            type="number"
                            min={2}
                            value={settings.lesson_threshold || 5}
                            onChange={(e) => onUpdateSettings("lesson_threshold", parseInt(e.target.value))}
                            disabled={!settings.auto_lesson_enabled}
                        />
                        <p className="text-[10px] text-muted-foreground">
                            Generate a lesson after this many confirmed insights accumulate.
                        </p>
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Lesson Trigger (days, optional)</Label>
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
                            Also trigger if oldest unused insight is this many days old (min 2 insights).
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* PII Settings */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-red-500" />
                        <CardTitle className="text-lg">PII Privacy</CardTitle>
                    </div>
                    <CardDescription className="text-xs">Configure PII scrubbing and data sharing</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Enable PII Scrubbing</Label>
                            <p className="text-[10px] text-muted-foreground">Automatically strip PII from shared data</p>
                        </div>
                        <Switch
                            checked={settings.pii_scrubbing_enabled}
                            onCheckedChange={(v) => onUpdateSettings("pii_scrubbing_enabled", v)}
                        />
                    </div>
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Auto-share Scrubbed</Label>
                            <p className="text-[10px] text-muted-foreground">Automatically share PII-stripped memories</p>
                        </div>
                        <Switch
                            checked={settings.auto_share_scrubbed}
                            onCheckedChange={(v) => onUpdateSettings("auto_share_scrubbed", v)}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Rate Limiting */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Zap className="w-5 h-5 text-amber-500" />
                        <CardTitle className="text-lg">Rate Limiting</CardTitle>
                    </div>
                    <CardDescription className="text-xs">Control API usage by agents</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Enable Rate Limiting</Label>
                            <p className="text-[10px] text-muted-foreground">Limit requests per agent</p>
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
                            onChange={(e) => onUpdateSettings("rate_limit_per_minute", parseInt(e.target.value))}
                            disabled={!settings.rate_limit_enabled}
                        />
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
