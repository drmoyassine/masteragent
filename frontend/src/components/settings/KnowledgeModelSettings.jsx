import React, { useState, useEffect, useCallback, useRef } from "react";
import {
    Database, Plus, Trash2, BookOpen, Settings, ChevronRight,
    Save, Loader2, Brain, Sparkles, Users, ChevronDown, Smile
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
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
import { toast } from "sonner";
import {
    getEntityTypeConfig,
    updateEntityTypeConfig,
    updateEntityType,
    getEntitySubtypes,
    createEntitySubtype,
    deleteEntitySubtype,
} from "@/lib/api";

// ─── Default Intelligence Signals Template ─────────────────────────────────
const CONTACT_INTELLIGENCE_SIGNALS = `## BUDGET & READINESS
- Evidence of confirmed budget, approved spending, or pricing discussions
- Funding stage, fiscal year timing, procurement process mentions

## TIMELINE & MOMENTUM
- Deadline commitments, go-live dates, implementation timelines
- Urgency indicators, stalled deals, delays, or acceleration signals

## STAKEHOLDERS & DECISION PROCESS
- New decision-makers surfaced, champions identified, blockers revealed
- Internal politics, approval chains, committee involvement

## QUALIFICATION & FIT
- Use-case alignment, technical requirements match/mismatch
- Deal stage progression, trial/POC outcomes, competitive evaluations

## OBJECTIONS & RISK
- Pricing pushback, feature gaps, integration concerns
- Competitor mentions, contract hesitation, legal/compliance blockers

## PAIN POINTS & NEEDS
- Explicit pain statements, workflow friction, unmet needs
- Strategic priorities, growth plans, operational challenges`;

// ─── Curated Entity Emoji Set ───────────────────────────────────────────────
const ENTITY_ICONS = [
    "👤","👥","🏢","🏭","🏫","🏥","🏦","🏛️",
    "📋","📦","📁","📂","🗂️","📊","📈","📉",
    "🤝","🎯","💼","🔑","⚙️","🔧","🛠️","🔩",
    "💡","🚀","⭐","🌐","🔗","💬","📧","📞",
    "🛒","💳","💰","🏷️","🎁","📣","📡","🤖",
];

// ─── Emoji Picker ────────────────────────────────────────────────────────────
function EmojiPicker({ currentIcon, onSelect, size = "text-lg" }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    return (
        <div className="relative" ref={ref}>
            <button
                onClick={() => setOpen((v) => !v)}
                title="Change icon"
                className={`${size} leading-none hover:scale-110 transition-transform cursor-pointer select-none p-1 rounded hover:bg-muted/50`}
            >
                {currentIcon || "📁"}
            </button>
            {open && (
                <div className="absolute z-50 top-full left-0 mt-1 p-2 bg-popover border border-border rounded-lg shadow-xl grid grid-cols-8 gap-0.5 w-56">
                    {ENTITY_ICONS.map((emoji) => (
                        <button
                            key={emoji}
                            onClick={() => { onSelect(emoji); setOpen(false); }}
                            className={`text-base p-1 rounded hover:bg-muted/70 transition-colors ${
                                currentIcon === emoji ? "bg-primary/20 ring-1 ring-primary" : ""
                            }`}
                        >
                            {emoji}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}


function EntityDetailPanel({ entityType, entityTypes }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // Sub-types
    const [subtypes, setSubtypes] = useState([]);
    const [newSubtype, setNewSubtype] = useState("");


    // Signals (local draft state)
    const [intelSignals, setIntelSignals] = useState("");
    const [knowledgeSignals, setKnowledgeSignals] = useState("");
    const [signalsDirty, setSignalsDirty] = useState(false);

    // Accordion state
    const [openSections, setOpenSections] = useState({
        subtypes: false,
        intelligence: true,
        knowledge: false,
        thresholds: false,
    });

    const toggleSection = (key) =>
        setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));

    // Find the entity type object to get its ID for subtypes
    const entityTypeObj = entityTypes?.find((et) => et.name === entityType);

    const loadConfig = useCallback(async () => {
        setLoading(true);
        try {
            const res = await getEntityTypeConfig(entityType);
            const data = res.data;
            setConfig(data);
            setIntelSignals(data.intelligence_signals_prompt || "");
            setKnowledgeSignals(data.knowledge_signals_prompt || "");
            setSignalsDirty(false);
        } catch {
            // Config may not exist yet
            setConfig({});
        }
        setLoading(false);
    }, [entityType]);

    const loadSubtypes = useCallback(async () => {
        if (!entityTypeObj?.id) return;
        try {
            const res = await getEntitySubtypes(entityTypeObj.id);
            setSubtypes(res.data || []);
        } catch {
            setSubtypes([]);
        }
    }, [entityTypeObj?.id]);

    useEffect(() => {
        loadConfig();
        loadSubtypes();
    }, [loadConfig, loadSubtypes]);

    const saveField = async (updates) => {
        setSaving(true);
        try {
            await updateEntityTypeConfig(entityType, updates);
            setConfig((prev) => ({ ...prev, ...updates }));
            toast.success("Configuration saved");
        } catch {
            toast.error("Failed to save configuration");
        } finally {
            setSaving(false);
        }
    };


    const saveSignals = () => {
        saveField({
            intelligence_signals_prompt: intelSignals || null,
            knowledge_signals_prompt: knowledgeSignals || null,
        });
        setSignalsDirty(false);
    };

    const handleAddSubtype = async () => {
        if (!newSubtype.trim() || !entityTypeObj?.id) return;
        try {
            await createEntitySubtype({
                entity_type_id: entityTypeObj.id,
                name: newSubtype.trim(),
            });
            setNewSubtype("");
            loadSubtypes();
            toast.success("Sub-type added");
        } catch {
            toast.error("Failed to add sub-type");
        }
    };

    const handleDeleteSubtype = async (id) => {
        try {
            await deleteEntitySubtype(id);
            loadSubtypes();
            toast.success("Sub-type removed");
        } catch {
            toast.error("Failed to remove sub-type");
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
        );
    }

    // Accordion section helper
    const Section = ({ id, icon: Icon, title, badge, children }) => (
        <div className="border border-border/50 rounded-lg overflow-hidden">
            <button
                onClick={() => toggleSection(id)}
                className="w-full flex items-center gap-2.5 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
            >
                <Icon className="w-4 h-4 text-primary shrink-0" />
                <span className="text-sm font-medium flex-1">{title}</span>
                {badge && (
                    <Badge variant="secondary" className="text-[10px] h-5">{badge}</Badge>
                )}
                <ChevronDown
                    className={`w-4 h-4 text-muted-foreground transition-transform ${openSections[id] ? "rotate-180" : ""
                        }`}
                />
            </button>
            {openSections[id] && (
                <div className="px-4 pb-4 pt-1 space-y-3 border-t border-border/30 bg-muted/10">
                    {children}
                </div>
            )}
        </div>
    );

    return (
        <div className="space-y-3">
            {/* ─── Sub-types ──────────────────────────────────── */}
            <Section id="subtypes" icon={Users} title="Sub-types" badge={subtypes.length || null}>
                <div className="flex flex-wrap gap-1.5">
                    {subtypes.map((st) => (
                        <Badge
                            key={st.id}
                            variant="secondary"
                            className="gap-1 pr-1 text-xs"
                        >
                            {st.name}
                            <button
                                onClick={() => handleDeleteSubtype(st.id)}
                                className="ml-0.5 hover:text-destructive transition-colors"
                            >
                                <Trash2 className="w-3 h-3" />
                            </button>
                        </Badge>
                    ))}
                    {subtypes.length === 0 && (
                        <p className="text-xs text-muted-foreground">No sub-types defined.</p>
                    )}
                </div>
                <div className="flex gap-2">
                    <Input
                        value={newSubtype}
                        onChange={(e) => setNewSubtype(e.target.value)}
                        placeholder="Add sub-type..."
                        className="text-xs h-8"
                        onKeyDown={(e) => e.key === "Enter" && handleAddSubtype()}
                    />
                    <Button
                        size="sm"
                        variant="secondary"
                        className="h-8 text-xs shrink-0"
                        onClick={handleAddSubtype}
                        disabled={!newSubtype.trim()}
                    >
                        <Plus className="w-3 h-3 mr-1" /> Add
                    </Button>
                </div>
            </Section>


            {/* ─── Intelligence Signals ──────────────────────── */}
            <Section id="intelligence" icon={Brain} title="Intelligence Signals" badge={intelSignals ? "configured" : null}>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Define the signal categories the LLM should probe for when analyzing this entity type's memories.
                    This text gets injected into the intelligence generation prompt as <code className="text-[10px] bg-muted px-1 rounded">{"{{ intelligence_signals }}"}</code>.
                </p>
                <Textarea
                    value={intelSignals}
                    onChange={(e) => {
                        setIntelSignals(e.target.value);
                        setSignalsDirty(true);
                    }}
                    className="text-xs font-mono h-48 resize-y"
                    placeholder="## BUDGET & READINESS&#10;- Evidence of confirmed budget...&#10;&#10;## TIMELINE & MOMENTUM&#10;- Deadline commitments..."
                />
                {!intelSignals && (
                    <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-xs gap-1"
                        onClick={() => {
                            setIntelSignals(CONTACT_INTELLIGENCE_SIGNALS);
                            setSignalsDirty(true);
                        }}
                    >
                        <Sparkles className="w-3 h-3" /> Load default contact signals
                    </Button>
                )}
            </Section>

            {/* ─── Knowledge Signals ──────────────────────────── */}
            <Section id="knowledge" icon={BookOpen} title="Knowledge Signals" badge={knowledgeSignals ? "configured" : null}>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Define what types of generalizable knowledge should be extracted from this entity type's intelligence.
                    Injected as <code className="text-[10px] bg-muted px-1 rounded">{"{{ knowledge_signals }}"}</code>.
                </p>
                <Textarea
                    value={knowledgeSignals}
                    onChange={(e) => {
                        setKnowledgeSignals(e.target.value);
                        setSignalsDirty(true);
                    }}
                    className="text-xs font-mono h-32 resize-y"
                    placeholder="## PROCESS PATTERNS&#10;- Recurring workflows...&#10;&#10;## RISK INDICATORS&#10;- Common failure patterns..."
                />
            </Section>

            {/* ─── Thresholds & Automation ────────────────────── */}
            <Section id="thresholds" icon={Settings} title="Thresholds & Automation">
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                        <Label className="text-xs">Intelligence extraction threshold</Label>
                        <p className="text-[10px] text-muted-foreground">
                            Memories needed before running intelligence extraction
                        </p>
                        <Input
                            type="number"
                            min={1}
                            value={config?.intelligence_extraction_threshold ?? 10}
                            onChange={(e) =>
                                saveField({
                                    intelligence_extraction_threshold:
                                        parseInt(e.target.value) || 10,
                                })
                            }
                            className="text-xs h-8 w-24"
                        />
                    </div>
                    <div className="space-y-1">
                        <Label className="text-xs">Knowledge extraction threshold</Label>
                        <p className="text-[10px] text-muted-foreground">
                            Intelligence items needed before knowledge generation
                        </p>
                        <Input
                            type="number"
                            min={1}
                            value={config?.knowledge_extraction_threshold ?? ""}
                            onChange={(e) =>
                                saveField({
                                    knowledge_extraction_threshold:
                                        parseInt(e.target.value) || null,
                                })
                            }
                            className="text-xs h-8 w-24"
                            placeholder="global"
                        />
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-4 pt-2">
                    <div className="flex items-center justify-between">
                        <div>
                            <Label className="text-xs">Auto-approve intelligence</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Skip draft → confirmed review
                            </p>
                        </div>
                        <Switch
                            checked={config?.intelligence_auto_approve ?? false}
                            onCheckedChange={(v) =>
                                saveField({ Intelligence_auto_approve: v })
                            }
                        />
                    </div>
                    <div className="flex items-center justify-between">
                        <div>
                            <Label className="text-xs">Auto-promote knowledge</Label>
                            <p className="text-[10px] text-muted-foreground">
                                Auto-generate from confirmed intelligence
                            </p>
                        </div>
                        <Switch
                            checked={config?.knowledge_auto_promote ?? false}
                            onCheckedChange={(v) =>
                                saveField({ knowledge_auto_promote: v })
                            }
                        />
                    </div>
                </div>
            </Section>

            {/* ─── Save Signals FAB ───────────────────────────── */}
            {signalsDirty && (
                <div className="sticky bottom-4 flex justify-end pt-2">
                    <Button onClick={saveSignals} disabled={saving} className="gap-1.5 shadow-lg">
                        {saving ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Save className="w-4 h-4" />
                        )}
                        Save Signal Configuration
                    </Button>
                </div>
            )}
        </div>
    );
}

// ─── Main Component ─────────────────────────────────────────────────────────
export function KnowledgeModelSettings({
    entityTypes,
    lessonTypes,
    newType,
    setNewType,
    addTypeDialogOpen,
    setAddTypeDialogOpen,
    onAddType,
    onDeleteType,
    onReload,
    loading,
}) {
    const [selectedEntity, setSelectedEntity] = useState(null);

    // Auto-select first entity type on load
    useEffect(() => {
        if (!selectedEntity && entityTypes?.length > 0) {
            setSelectedEntity(entityTypes[0].name);
        }
    }, [entityTypes, selectedEntity]);

    return (
        <div className="flex gap-6 max-w-6xl h-[calc(100vh-200px)]">
            {/* ─── Left Panel: Entity List ────────────────────── */}
            <div className="w-56 shrink-0 flex flex-col">
                <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                        Entity Types
                    </h3>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => {
                            setNewType({ name: "", description: "", type: "entity" });
                            setAddTypeDialogOpen(true);
                        }}
                    >
                        <Plus className="w-4 h-4" />
                    </Button>
                </div>

                <div className="space-y-1 flex-1 overflow-y-auto">
                    {entityTypes.map((et) => {
                        const isActive = selectedEntity === et.name;
                        return (
                            <button
                                key={et.id}
                                onClick={() => setSelectedEntity(et.name)}
                                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all group ${isActive
                                        ? "bg-primary/10 border border-primary/30 text-primary"
                                        : "hover:bg-muted/50 border border-transparent"
                                    }`}
                            >
                                <span onClick={(e) => e.stopPropagation()}>
                                    <EmojiPicker
                                        size="text-base"
                                        currentIcon={et.icon}
                                        onSelect={async (emoji) => {
                                            try {
                                                await updateEntityType(et.id, { icon: emoji });
                                                onReload();
                                            } catch { toast.error("Failed to update icon"); }
                                        }}
                                    />
                                </span>
                                <div className="flex-1 min-w-0">
                                    <p className={`text-sm truncate ${isActive ? "font-semibold" : "font-medium"}`}>
                                        {et.name}
                                    </p>
                                    {et.description && (
                                        <p className="text-[10px] text-muted-foreground truncate">
                                            {et.description}
                                        </p>
                                    )}
                                </div>
                                {isActive && (
                                    <ChevronRight className="w-4 h-4 text-primary shrink-0" />
                                )}
                            </button>
                        );
                    })}

                    {entityTypes.length === 0 && (
                        <p className="text-xs text-muted-foreground text-center py-8">
                            No entity types defined.
                        </p>
                    )}
                </div>

                {/* Knowledge Types link (secondary) */}
                <div className="border-t border-border/50 pt-3 mt-3">
                    <button
                        onClick={() => {
                            setNewType({ name: "", description: "", type: "lesson" });
                            setAddTypeDialogOpen(true);
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/30 rounded-lg transition-colors"
                    >
                        <BookOpen className="w-4 h-4 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium">Knowledge Types</p>
                            <p className="text-[10px] text-muted-foreground">
                                {lessonTypes?.length || 0} types defined
                            </p>
                        </div>
                        <Plus className="w-3 h-3 text-muted-foreground" />
                    </button>
                    {lessonTypes?.length > 0 && (
                        <div className="flex flex-wrap gap-1 px-3 mt-1.5">
                            {lessonTypes.map((lt) => (
                                <Badge
                                    key={lt.id}
                                    variant="outline"
                                    className="text-[10px] h-5 gap-1 pr-1"
                                    style={{ borderColor: lt.color || "#6B7280" }}
                                >
                                    <span
                                        className="w-1.5 h-1.5 rounded-full"
                                        style={{ backgroundColor: lt.color || "#6B7280" }}
                                    />
                                    {lt.name}
                                    <button
                                        onClick={() => onDeleteType("lesson", lt.id)}
                                        className="hover:text-destructive transition-colors"
                                    >
                                        <Trash2 className="w-2.5 h-2.5" />
                                    </button>
                                </Badge>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* ─── Right Panel: Entity Config ─────────────────── */}
            <div className="flex-1 overflow-y-auto pr-1">
                {selectedEntity ? (
                    <div>
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                                {(() => {
                                    const et = entityTypes.find((e) => e.name === selectedEntity);
                                    return (
                                        <EmojiPicker
                                            size="text-2xl"
                                            currentIcon={et?.icon}
                                            onSelect={async (emoji) => {
                                                if (!et) return;
                                                try {
                                                    await updateEntityType(et.id, { icon: emoji });
                                                    onReload();
                                                } catch { toast.error("Failed to update icon"); }
                                            }}
                                        />
                                    );
                                })()}
                                <div>
                                    <h2 className="text-lg font-semibold capitalize">{selectedEntity}</h2>
                                    <p className="text-xs text-muted-foreground">
                                        {entityTypes.find((et) => et.name === selectedEntity)?.description || "Entity type configuration"}
                                    </p>
                                </div>
                            </div>
                            <Button
                                variant="ghost"
                                size="sm"
                                className="text-xs text-muted-foreground hover:text-destructive"
                                onClick={() => {
                                    const et = entityTypes.find((e) => e.name === selectedEntity);
                                    if (et) onDeleteType("entity", et.id);
                                }}
                            >
                                <Trash2 className="w-3.5 h-3.5 mr-1" /> Delete Entity Type
                            </Button>
                        </div>

                        <EntityDetailPanel
                            key={selectedEntity}
                            entityType={selectedEntity}
                            entityTypes={entityTypes}
                        />
                    </div>
                ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                        <div className="text-center">
                            <Database className="w-10 h-10 mx-auto mb-3 opacity-30" />
                            <p className="text-sm">Select an entity type to configure</p>
                        </div>
                    </div>
                )}
            </div>

            {/* ─── Add Type Dialog ─────────────────────────────── */}
            <Dialog open={addTypeDialogOpen} onOpenChange={setAddTypeDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            Add {newType.type === "entity" ? "Entity" : "Knowledge"} Type
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                value={newType.name}
                                onChange={(e) => setNewType({ ...newType, name: e.target.value })}
                                placeholder={newType.type === "entity" ? "e.g. vendor" : "e.g. compliance"}
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
                        <Button variant="ghost" onClick={() => setAddTypeDialogOpen(false)}>
                            Cancel
                        </Button>
                        <Button onClick={onAddType} disabled={!newType.name.trim()}>
                            Add Type
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
