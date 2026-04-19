import React, { useState, useEffect } from "react";
import { Database, Plus, Trash2, Tag, BookOpen, MessageSquare, Settings, ChevronRight, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { toast } from "sonner";
import { getEntityTypeConfig, updateEntityTypeConfig } from "@/lib/api";

const DEFAULT_NER_SCHEMA = {
    labels: ["person", "organization", "location", "product", "event", "date"],
};

function EntityTypeConfigPanel({ entityTypeName }) {
    const [config, setConfig] = useState(null);
    const [open, setOpen] = useState(false);
    const [nerSchemaText, setNerSchemaText] = useState("");
    const [nerSchemaError, setNerSchemaError] = useState("");
    const [saving, setSaving] = useState(false);

    const load = async () => {
        try {
            const res = await getEntityTypeConfig(entityTypeName);
            setConfig(res.data);
            setNerSchemaText(
                res.data.ner_schema
                    ? JSON.stringify(res.data.ner_schema, null, 2)
                    : JSON.stringify(DEFAULT_NER_SCHEMA, null, 2)
            );
        } catch {
            // config may not exist yet — that's fine
        }
    };

    useEffect(() => {
        if (open && !config) load();
    }, [open]);

    const save = async (updates) => {
        setSaving(true);
        try {
            await updateEntityTypeConfig(entityTypeName, updates);
            setConfig(prev => ({ ...prev, ...updates }));
            toast.success(`${entityTypeName} config saved`);
        } catch {
            toast.error("Failed to save config");
        } finally {
            setSaving(false);
        }
    };

    const saveNerSchema = () => {
        try {
            const parsed = JSON.parse(nerSchemaText);
            setNerSchemaError("");
            save({ ner_schema: parsed });
        } catch {
            setNerSchemaError("Invalid JSON");
        }
    };

    if (!config && !open) {
        return (
            <Collapsible open={open} onOpenChange={setOpen}>
                <CollapsibleTrigger asChild>
                    <button className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mt-1 transition-colors">
                        <Settings className="w-3 h-3" />
                        Configure NER &amp; thresholds
                        <ChevronRight className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} />
                    </button>
                </CollapsibleTrigger>
                <CollapsibleContent />
            </Collapsible>
        );
    }

    return (
        <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger asChild>
                <button className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground mt-1 transition-colors">
                    <Settings className="w-3 h-3" />
                    Configure NER &amp; schema
                    <ChevronRight className={`w-3 h-3 transition-transform ${open ? "rotate-90" : ""}`} />
                </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
                {config && (
                    <div className="mt-3 space-y-4 p-3 bg-muted/30 rounded-lg border border-border/50">

                        {/* NER toggle + confidence */}
                        <div className="flex items-center justify-between">
                            <div>
                                <Label className="text-xs">NER enabled</Label>
                                <p className="text-[10px] text-muted-foreground">Extract entities from interactions</p>
                            </div>
                            <Switch
                                checked={config.ner_enabled ?? true}
                                onCheckedChange={v => { setConfig(p => ({ ...p, ner_enabled: v })); save({ ner_enabled: v }); }}
                            />
                        </div>

                        {/* NER Schema */}
                        <div className="space-y-1">
                            <div className="flex items-center gap-1.5">
                                <Label className="text-xs font-mono">NER Schema (JSON)</Label>
                                <Info className="w-3 h-3 text-muted-foreground" title='{"labels": ["person","organization",...]}' />
                            </div>
                            <Textarea
                                value={nerSchemaText}
                                onChange={e => { setNerSchemaText(e.target.value); setNerSchemaError(""); }}
                                className="text-xs font-mono h-24 resize-none"
                                placeholder='{"labels": ["person", "organization", ...]}'
                            />
                            {nerSchemaError && <p className="text-[10px] text-destructive">{nerSchemaError}</p>}
                            <Button size="sm" variant="secondary" className="h-7 text-xs" onClick={saveNerSchema} disabled={saving}>
                                Save Schema
                            </Button>
                        </div>

                        {/* Auto-approve / auto-promote */}
                        <div className="grid grid-cols-2 gap-3">
                            <div className="flex items-center justify-between">
                                <div>
                                    <Label className="text-xs">Auto-approve insights</Label>
                                </div>
                                <Switch
                                    checked={config.insight_auto_approve ?? false}
                                    onCheckedChange={v => { setConfig(p => ({ ...p, insight_auto_approve: v })); save({ insight_auto_approve: v }); }}
                                />
                            </div>
                            <div className="flex items-center justify-between">
                                <div>
                                    <Label className="text-xs">Auto-promote lessons</Label>
                                </div>
                                <Switch
                                    checked={config.lesson_auto_promote ?? false}
                                    onCheckedChange={v => { setConfig(p => ({ ...p, lesson_auto_promote: v })); save({ lesson_auto_promote: v }); }}
                                />
                            </div>
                        </div>
                    </div>
                )}
            </CollapsibleContent>
        </Collapsible>
    );
}

export function KnowledgeModelSettings({
    entityTypes,
    lessonTypes,
    channelTypes,
    newType,
    setNewType,
    addTypeDialogOpen,
    setAddTypeDialogOpen,
    onAddType,
    onDeleteType,
    loading
}) {
    const sections = [
        { title: "Entity Types", icon: Tag, data: entityTypes, type: "entity", description: "Categories of things the system tracks" },
        { title: "Lesson Types", icon: BookOpen, data: lessonTypes, type: "lesson", description: "Types of lessons extracted from insights" },
        { title: "Channel Types", icon: MessageSquare, data: channelTypes, type: "channel", description: "Sources of information (email, call, webhook...)" },
    ];

    return (
        <div className="space-y-6 max-w-4xl">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {sections.map((section) => {
                    const Icon = section.icon;
                    return (
                        <Card key={section.type}>
                            <CardHeader className="pb-3">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Icon className="w-5 h-5 text-primary" />
                                        <CardTitle className="text-lg">{section.title}</CardTitle>
                                    </div>
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => {
                                            setNewType({ name: "", description: "", type: section.type });
                                            setAddTypeDialogOpen(true);
                                        }}
                                    >
                                        <Plus className="w-4 h-4" />
                                    </Button>
                                </div>
                                <CardDescription className="text-xs">{section.description}</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {section.data.length === 0 ? (
                                        <p className="text-xs text-muted-foreground py-4 text-center border border-dashed rounded-lg">
                                            No {section.title.toLowerCase()} defined.
                                        </p>
                                    ) : (
                                        section.data.map((item) => (
                                            <div key={item.id} className="rounded border bg-card/50 text-sm p-2">
                                                <div className="flex items-center justify-between">
                                                    <div className="min-w-0">
                                                        <p className="font-medium truncate">{item.name || item.label}</p>
                                                        <p className="text-[10px] text-muted-foreground truncate">{item.description}</p>
                                                    </div>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                                                        onClick={() => onDeleteType(section.type, item.id)}
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </Button>
                                                </div>
                                                {/* Entity types get inline config panel */}
                                                {section.type === "entity" && (
                                                    <EntityTypeConfigPanel entityTypeName={item.name} />
                                                )}
                                            </div>
                                        ))
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    );
                })}
            </div>

            <Dialog open={addTypeDialogOpen} onOpenChange={setAddTypeDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add {newType.type?.charAt(0).toUpperCase() + newType.type?.slice(1)} Type</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                value={newType.name}
                                onChange={(e) => setNewType({ ...newType, name: e.target.value })}
                                placeholder="e.g. Project"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Description</Label>
                            <Input
                                value={newType.description}
                                onChange={(e) => setNewType({ ...newType, description: e.target.value })}
                                placeholder="Brief description..."
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setAddTypeDialogOpen(false)}>Cancel</Button>
                        <Button onClick={onAddType} disabled={!newType.name.trim()}>Add Type</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
