import React, { useState, useEffect, useCallback, useRef } from "react";
import {
    Database, Plus, Trash2, Settings, ChevronRight,
    Save, Loader2, Brain, Sparkles, Users, ChevronDown, BookOpen, Pencil, X, FileText
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
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

// ─── Default Intelligence Signals Template (structured) ─────────────────────
const DEFAULT_CONTACT_SIGNALS = [
    { name: "Budget & Readiness", description: "Evidence of confirmed budget, approved spending, pricing discussions, fiscal year timing, procurement process mentions" },
    { name: "Timeline & Momentum", description: "Deadline commitments, go-live dates, implementation timelines, urgency indicators, stalled deals, delays or acceleration" },
    { name: "Stakeholders & Decision Process", description: "New decision-makers surfaced, champions identified, blockers revealed, approval chains, committee involvement" },
    { name: "Qualification & Fit", description: "Use-case alignment, technical requirements match/mismatch, deal stage progression, trial/POC outcomes, competitive evaluations" },
    { name: "Objections & Risk", description: "Pricing pushback, feature gaps, integration concerns, competitor mentions, contract hesitation, legal/compliance blockers" },
    { name: "Pain Points & Needs", description: "Explicit pain statements, workflow friction, unmet needs, strategic priorities, growth plans, operational challenges" },
];

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

// ─── Signal Card List ────────────────────────────────────────────────────────
function SignalList({ signals, onChange, defaultTemplate, defaultLabel }) {
    const [newName, setNewName] = useState("");
    const [newDesc, setNewDesc] = useState("");
    const [editIdx, setEditIdx] = useState(null);
    const [editName, setEditName] = useState("");
    const [editDesc, setEditDesc] = useState("");

    const addSignal = () => {
        if (!newName.trim()) return;
        onChange([...(signals || []), { name: newName.trim(), description: newDesc.trim() }]);
        setNewName("");
        setNewDesc("");
    };

    const removeSignal = (idx) => {
        onChange((signals || []).filter((_, i) => i !== idx));
    };

    const startEdit = (idx) => {
        setEditIdx(idx);
        setEditName(signals[idx].name);
        setEditDesc(signals[idx].description);
    };

    const saveEdit = () => {
        if (editIdx === null) return;
        const updated = [...(signals || [])];
        updated[editIdx] = { name: editName.trim(), description: editDesc.trim() };
        onChange(updated);
        setEditIdx(null);
    };

    const cancelEdit = () => setEditIdx(null);

    return (
        <div className="space-y-2">
            {/* Existing signals */}
            {(signals || []).map((signal, idx) => (
                <div key={idx} className="border border-border/40 rounded-md p-2.5 bg-background/50 group">
                    {editIdx === idx ? (
                        <div className="space-y-2">
                            <Input
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                className="text-xs h-7 font-medium"
                                autoFocus
                            />
                            <Input
                                value={editDesc}
                                onChange={(e) => setEditDesc(e.target.value)}
                                className="text-xs h-7"
                                placeholder="Description..."
                            />
                            <div className="flex gap-1.5">
                                <Button size="sm" className="h-6 text-[10px] px-2" onClick={saveEdit}>Save</Button>
                                <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2" onClick={cancelEdit}>Cancel</Button>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-start gap-2">
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-medium">{signal.name}</p>
                                {signal.description && (
                                    <p className="text-[10px] text-muted-foreground mt-0.5 leading-relaxed">{signal.description}</p>
                                )}
                            </div>
                            <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                <button onClick={() => startEdit(idx)} className="p-1 hover:bg-muted rounded" title="Edit">
                                    <Pencil className="w-3 h-3 text-muted-foreground" />
                                </button>
                                <button onClick={() => removeSignal(idx)} className="p-1 hover:bg-destructive/10 rounded" title="Remove">
                                    <Trash2 className="w-3 h-3 text-muted-foreground hover:text-destructive" />
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            ))}

            {/* Empty state with template loader */}
            {(!signals || signals.length === 0) && defaultTemplate && (
                <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs gap-1 w-full border-dashed"
                    onClick={() => onChange(defaultTemplate)}
                >
                    <Sparkles className="w-3 h-3" /> {defaultLabel || "Load default signals"}
                </Button>
            )}

            {/* Add new signal */}
            <div className="border border-dashed border-border/50 rounded-md p-2.5 space-y-1.5">
                <div className="flex gap-2">
                    <Input
                        value={newName}
                        onChange={(e) => setNewName(e.target.value)}
                        placeholder="Signal name..."
                        className="text-xs h-7 flex-1"
                        onKeyDown={(e) => e.key === "Enter" && addSignal()}
                    />
                    <Button
                        size="sm"
                        variant="secondary"
                        className="h-7 text-[10px] px-2 shrink-0"
                        onClick={addSignal}
                        disabled={!newName.trim()}
                    >
                        <Plus className="w-3 h-3 mr-0.5" /> Add
                    </Button>
                </div>
                {newName.trim() && (
                    <Input
                        value={newDesc}
                        onChange={(e) => setNewDesc(e.target.value)}
                        placeholder="Description (what to look for)..."
                        className="text-xs h-7"
                        onKeyDown={(e) => e.key === "Enter" && addSignal()}
                    />
                )}
            </div>
        </div>
    );
}


// ─── Entity Detail Panel ────────────────────────────────────────────────────
function EntityDetailPanel({ entityType, entityTypes }) {
    const [config, setConfig] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    // Sub-types
    const [subtypes, setSubtypes] = useState([]);
    const [newSubtype, setNewSubtype] = useState("");

    // Signals (local draft state — structured arrays)
    const [intelSignals, setIntelSignals] = useState([]);
    const [knowledgeSignals, setKnowledgeSignals] = useState([]);

    // Entity Schema (field map + discovered schema)
    const [fieldMap, setFieldMap] = useState({});
    const [discoveredSchema, setDiscoveredSchema] = useState([]);

    // Dirty tracking
    const [signalsDirty, setSignalsDirty] = useState(false);
    const [schemaDirty, setSchemaDirty] = useState(false);

    // Sync triggers local state
    const [newTrigger, setNewTrigger] = useState("");

    // Accordion state
    const [openSections, setOpenSections] = useState({
        schema: true,
        subtypes: false,
        intelligence: false,
        knowledge: false,
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
            setIntelSignals(data.intelligence_signals_prompt || []);
            setKnowledgeSignals(data.knowledge_signals_prompt || []);
            setFieldMap(data.metadata_field_map || {});
            setDiscoveredSchema(data.discovered_schema || []);
            setSignalsDirty(false);
            setSchemaDirty(false);
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
            intelligence_signals_prompt: intelSignals.length > 0 ? intelSignals : null,
            knowledge_signals_prompt: knowledgeSignals.length > 0 ? knowledgeSignals : null,
        });
        setSignalsDirty(false);
    };

    const saveSchema = () => {
        saveField({ metadata_field_map: fieldMap });
        setSchemaDirty(false);
    };

    const updateFieldMap = (key, value) => {
        setFieldMap((prev) => ({ ...prev, [key]: value }));
        setSchemaDirty(true);
    };

    const addSyncTrigger = () => {
        if (!newTrigger.trim()) return;
        const triggers = fieldMap.profile_sync_triggers || ["initial_memory_context"];
        if (triggers.includes(newTrigger.trim())) return;
        updateFieldMap("profile_sync_triggers", [...triggers, newTrigger.trim()]);
        setNewTrigger("");
    };

    const removeSyncTrigger = (trigger) => {
        const triggers = (fieldMap.profile_sync_triggers || []).filter((t) => t !== trigger);
        updateFieldMap("profile_sync_triggers", triggers);
    };

    const toggleDisplayColumn = (col) => {
        const cols = fieldMap.display_columns || [];
        if (cols.includes(col)) {
            updateFieldMap("display_columns", cols.filter((c) => c !== col));
        } else {
            updateFieldMap("display_columns", [...cols, col]);
        }
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
            {/* ─── Entity Schema Mapping ──────────────────────── */}
            <Section id="schema" icon={FileText} title="Entity Schema" badge={discoveredSchema.length ? `${discoveredSchema.length} fields` : null}>
                <p className="text-[10px] text-muted-foreground leading-relaxed mb-2">
                    Map CRM fields to semantic roles. {discoveredSchema.length > 0 ? "Fields auto-detected from ingested data." : "Configure manually or ingest data to auto-detect fields."}
                </p>

                {/* Semantic role mappings */}
                <div className="space-y-2.5">
                    {[
                        { key: "name_field", label: "Display Name", placeholder: "e.g. full_name" },
                        { key: "subtype_field", label: "Subtype", placeholder: "e.g. contact_type" },
                        { key: "status_field", label: "Status", placeholder: "e.g. lead_stage" },
                        { key: "summary_field", label: "Summary", placeholder: "e.g. case_summary" },
                    ].map(({ key, label, placeholder }) => (
                        <div key={key} className="flex items-center gap-2">
                            <Label className="text-xs w-28 shrink-0">{label}</Label>
                            {discoveredSchema.length > 0 ? (
                                <select
                                    value={fieldMap[key] || ""}
                                    onChange={(e) => updateFieldMap(key, e.target.value || undefined)}
                                    className="flex-1 h-8 text-xs rounded-md border border-input bg-background px-2 focus:outline-none focus:ring-1 focus:ring-ring"
                                >
                                    <option value="">— not mapped —</option>
                                    {discoveredSchema.map((f) => (
                                        <option key={f} value={f}>{f}</option>
                                    ))}
                                </select>
                            ) : (
                                <Input
                                    value={fieldMap[key] || ""}
                                    onChange={(e) => updateFieldMap(key, e.target.value || undefined)}
                                    placeholder={placeholder}
                                    className="text-xs h-8 flex-1"
                                />
                            )}
                        </div>
                    ))}
                </div>

                {/* Sync Triggers */}
                <div className="mt-4 pt-3 border-t border-border/30">
                    <Label className="text-xs font-medium">Profile Sync Triggers</Label>
                    <p className="text-[10px] text-muted-foreground mb-2">
                        Interaction types that trigger entity profile extraction.
                    </p>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                        {(fieldMap.profile_sync_triggers || ["initial_memory_context"]).map((trigger) => (
                            <Badge key={trigger} variant="secondary" className="gap-1 pr-1 text-xs">
                                {trigger}
                                <button
                                    onClick={() => removeSyncTrigger(trigger)}
                                    className="ml-0.5 hover:text-destructive transition-colors"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            </Badge>
                        ))}
                    </div>
                    <div className="flex gap-2">
                        <Input
                            value={newTrigger}
                            onChange={(e) => setNewTrigger(e.target.value)}
                            placeholder="Add trigger type..."
                            className="text-xs h-8"
                            onKeyDown={(e) => e.key === "Enter" && addSyncTrigger()}
                        />
                        <Button
                            size="sm"
                            variant="secondary"
                            className="h-8 text-xs shrink-0"
                            onClick={addSyncTrigger}
                            disabled={!newTrigger.trim()}
                        >
                            <Plus className="w-3 h-3 mr-1" /> Add
                        </Button>
                    </div>
                </div>

                {/* Display Columns */}
                {discoveredSchema.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-border/30">
                        <Label className="text-xs font-medium">Display Columns</Label>
                        <p className="text-[10px] text-muted-foreground mb-2">
                            Select which fields appear as extra columns in the Memory Explorer tables.
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                            {discoveredSchema.map((col) => {
                                const isActive = (fieldMap.display_columns || []).includes(col);
                                return (
                                    <button
                                        key={col}
                                        onClick={() => toggleDisplayColumn(col)}
                                        className={`text-[10px] px-2 py-1 rounded-md border transition-colors ${
                                            isActive
                                                ? "bg-primary/10 border-primary/30 text-primary font-medium"
                                                : "border-border/40 text-muted-foreground hover:bg-muted/50"
                                        }`}
                                    >
                                        {col}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Save Schema */}
                {schemaDirty && (
                    <div className="flex justify-end pt-3">
                        <Button size="sm" onClick={saveSchema} disabled={saving} className="gap-1.5">
                            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                            Save Schema
                        </Button>
                    </div>
                )}
            </Section>

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
            <Section id="intelligence" icon={Brain} title="Intelligence Signals" badge={intelSignals.length || null}>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Define the signal categories the LLM should probe for when analyzing this entity type's memories.
                </p>
                <SignalList
                    signals={intelSignals}
                    onChange={(v) => { setIntelSignals(v); setSignalsDirty(true); }}
                    defaultTemplate={DEFAULT_CONTACT_SIGNALS}
                    defaultLabel="Load default contact signals"
                />
            </Section>

            {/* ─── Knowledge Signals ──────────────────────────── */}
            <Section id="knowledge" icon={BookOpen} title="Knowledge Signals" badge={knowledgeSignals.length || null}>
                <p className="text-[10px] text-muted-foreground leading-relaxed">
                    Define what types of generalizable knowledge should be extracted from confirmed intelligence.
                </p>
                <SignalList
                    signals={knowledgeSignals}
                    onChange={(v) => { setKnowledgeSignals(v); setSignalsDirty(true); }}
                />
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

            {/* ─── Add Entity Type Dialog ──────────────────────── */}
            <Dialog open={addTypeDialogOpen} onOpenChange={setAddTypeDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Add Entity Type</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label>Name</Label>
                            <Input
                                value={newType.name}
                                onChange={(e) => setNewType({ ...newType, name: e.target.value })}
                                placeholder="e.g. vendor"
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
