import React from "react";
import { Settings, Scissors, GraduationCap, ShieldAlert, Zap } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";

export function GeneralMemorySettings({ settings, onUpdateSettings }) {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-5xl">
            {/* Chunking Settings */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <Scissors className="w-5 h-5 text-blue-500" />
                        <CardTitle className="text-lg">Chunking Strategy</CardTitle>
                    </div>
                    <CardDescription className="text-xs">Configure text chunking for vector storage</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Chunk Size (tokens)</Label>
                        <Input
                            type="number"
                            value={settings.chunk_size || 400}
                            onChange={(e) => onUpdateSettings("chunk_size", parseInt(e.target.value))}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label className="text-xs font-mono">Chunk Overlap (tokens)</Label>
                        <Input
                            type="number"
                            value={settings.chunk_overlap || 80}
                            onChange={(e) => onUpdateSettings("chunk_overlap", parseInt(e.target.value))}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Lesson Settings */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <GraduationCap className="w-5 h-5 text-green-500" />
                        <CardTitle className="text-lg">Lesson Mining</CardTitle>
                    </div>
                    <CardDescription className="text-xs">Configure automated lesson extraction</CardDescription>
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
                    <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                            <Label>Require Approval</Label>
                            <p className="text-[10px] text-muted-foreground">New lessons start as drafts</p>
                        </div>
                        <Switch
                            checked={settings.lesson_approval_required}
                            onCheckedChange={(v) => onUpdateSettings("lesson_approval_required", v)}
                        />
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
