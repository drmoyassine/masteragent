import React, { useState } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Plus, GraduationCap, Sparkles, Brain, Scissors, EyeOff, ArrowRight, CircleHelp } from "lucide-react";
import { InlineTaskConfigAccordion } from "./InlineTaskConfigAccordion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TASK_TYPE_LABELS } from "@/components/settings/LLMProviderSettings";
import api from "@/lib/api";
import { toast } from "sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

function OverrideLabel({ children, help }) {
  return <div className="flex items-center gap-1"><Label className="text-[10px]">{children}</Label><TooltipProvider delayDuration={120}><Tooltip><TooltipTrigger asChild><button type="button" aria-label={`Help: ${children}`} className="text-muted-foreground hover:text-foreground"><CircleHelp className="h-3 w-3" /></button></TooltipTrigger><TooltipContent className="max-w-xs text-xs">{help}</TooltipContent></Tooltip></TooltipProvider></div>;
}

// Knowledge-stage pathways are NOT a sequential pipeline — each is an independent
// producer that picks its node by task_type. This metadata makes each pathway's
// input/output/trigger legible in the UI (the whole point of the refactor).
const KNOWLEDGE_PATHWAYS = [
  {
    task_type: "knowledge_generation",
    title: "Declarative Knowledge", icon: GraduationCap, accent: "border-emerald-500/40",
    feeds: "Confirmed intelligence", produces: "best_practices · lessons_learned · trade_knowledge",
    trigger: "Nightly + threshold + drain",
  },
  {
    task_type: "telemetry_reflection",
    title: "Telemetry Reflection", icon: Sparkles, accent: "border-cyan-500/40",
    feeds: "AI thoughts & tool calls (internal_ai_*)", produces: "skill · playbook · best_practices · lessons · trade",
    trigger: "Nightly + backfill",
  },
  {
    task_type: "playbook_generation",
    title: "Playbook Extraction", icon: Brain, accent: "border-orange-500/40",
    feeds: "Intelligence clusters across ≥3 entities", produces: "playbook",
    trigger: "Nightly",
  },
  {
    task_type: "skill_generation",
    title: "Skill Decomposition", icon: Scissors, accent: "border-pink-500/40",
    feeds: "Playbook steps", produces: "skill",
    trigger: "Automatic (after each playbook)",
  },
  {
    task_type: "pii_scrubbing",
    title: "PII Scrubbing", icon: EyeOff, accent: "border-red-500/40",
    feeds: "Knowledge content before synthesis", produces: "PII redacted in place",
    trigger: "Inline (used by declarative + manual paths)",
  },
];

function EntityPathwayOverrides({ entityTypes, pathwayKey }) {
  const [configs, setConfigs] = useState({});
  const [loading, setLoading] = useState(false);
  const load = async () => {
    if (!entityTypes?.length) return;
    setLoading(true);
    const next = {};
    await Promise.all(entityTypes.map(async (entity) => {
      try {
        const { data } = await api.get(`/memory/entity-type-config/${entity.name}`);
        const overrides = data.knowledge_generation_overrides || {};
        if (pathwayKey === "declarative_knowledge" &&
            overrides?.declarative_knowledge?.evidence_threshold === undefined &&
            data.knowledge_extraction_threshold != null) {
          overrides.declarative_knowledge = {
            ...(overrides.declarative_knowledge || {}),
            evidence_threshold: data.knowledge_extraction_threshold,
          };
        }
        next[entity.name] = overrides;
      } catch { next[entity.name] = {}; }
    }));
    setConfigs(next); setLoading(false);
  };
  const save = async (entityName, field, value) => {
    const all = { ...(configs[entityName] || {}) };
    const pathway = { ...(all[pathwayKey] || {}) };
    if (value === "" || value === "inherit") delete pathway[field];
    else pathway[field] = value;
    if (Object.keys(pathway).length) all[pathwayKey] = pathway;
    else delete all[pathwayKey];
    setConfigs((current) => ({ ...current, [entityName]: all }));
    try { await api.patch(`/memory/entity-type-config/${entityName}`, { knowledge_generation_overrides: all }); }
    catch { toast.error(`Could not save ${entityName} override`); }
  };
  return (
    <details className="mt-3 rounded-md border bg-muted/10" onToggle={(e) => e.currentTarget.open && !Object.keys(configs).length && load()}>
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-semibold">Entity-specific overrides</summary>
      <div className="border-t p-3 space-y-2">
        {!loading && <div className={`grid gap-2 text-[10px] text-muted-foreground ${pathwayKey === "declarative_knowledge" ? "grid-cols-[1.2fr_1fr_1fr_1fr_1fr]" : "grid-cols-[1.2fr_1fr_1fr_1fr]"}`}>
          <span>Entity type</span>
          {pathwayKey === "declarative_knowledge" && <OverrideLabel help="Overrides the evidence count only for this entity type's Declarative Knowledge pathway. It wins over pathway and global values.">Evidence</OverrideLabel>}
          <OverrideLabel help="Overrides confidence only for this entity type and pathway. It wins over pathway and global values.">Confidence</OverrideLabel>
          <OverrideLabel help="Overrides output tokens only for this entity type and pathway. It wins over pathway and global values.">Tokens</OverrideLabel>
          <OverrideLabel help="Overrides the approval policy only for this entity type and pathway. It wins over pathway and global values.">Approval</OverrideLabel>
        </div>}
        {loading ? <p className="text-xs text-muted-foreground">Loading…</p> : (entityTypes || []).map((entity) => {
          const current = (configs[entity.name] || {})[pathwayKey] || {};
          return <div key={entity.name} className={`grid gap-2 items-center ${pathwayKey === "declarative_knowledge" ? "grid-cols-[1.2fr_1fr_1fr_1fr_1fr]" : "grid-cols-[1.2fr_1fr_1fr_1fr]"}`}>
            <span className="text-xs capitalize">{entity.icon || "📦"} {entity.name}</span>
            {pathwayKey === "declarative_knowledge" && <Input className="h-7 text-[11px]" type="number" min="1" placeholder="Global evidence" value={current.evidence_threshold ?? ""} onChange={(e) => save(entity.name, "evidence_threshold", e.target.value === "" ? "" : Number(e.target.value))} />}
            <Input className="h-7 text-[11px]" type="number" min="0" max="1" step="0.05" placeholder="Global confidence" value={current.min_confidence ?? ""} onChange={(e) => save(entity.name, "min_confidence", e.target.value === "" ? "" : Number(e.target.value))} />
            <Input className="h-7 text-[11px]" type="number" min="256" max="8000" placeholder="Global tokens" value={current.max_tokens ?? ""} onChange={(e) => save(entity.name, "max_tokens", e.target.value === "" ? "" : Number(e.target.value))} />
            <Select value={current.approval_policy || "inherit"} onValueChange={(v) => save(entity.name, "approval_policy", v)}><SelectTrigger className="h-7 text-[11px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="inherit">Global approval</SelectItem><SelectItem value="approve_immediately">Approved</SelectItem><SelectItem value="create_as_draft">Draft</SelectItem></SelectContent></Select>
          </div>;
        })}
      </div>
    </details>
  );
}

function SortablePipelineNode({ config, ...props }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
  } = useSortable({ id: config.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div ref={setNodeRef} style={style} className="flex items-start gap-2 bg-background mb-4">
      <div 
        {...attributes} 
        {...listeners} 
        className="mt-6 cursor-grab text-muted-foreground hover:text-foreground active:cursor-grabbing"
      >
        <GripVertical className="w-5 h-5" />
      </div>
      {config.task_type === 'vision' ? (
        <div className="flex-1 flex border-l-2 border-dashed border-purple-500/50 pl-4 relative my-2">
            <div className="absolute -left-[14px] top-6 bg-background text-purple-400 text-[10px] font-mono font-bold px-1 py-0.5 border border-purple-500/50 rounded">
               IF
            </div>
            <div className="flex-1">
               <div className="text-[10px] text-purple-500 mb-1.5 ml-1 font-mono uppercase tracking-wider font-semibold">
                  ↳ Condition: Image or Document Attachment Detected
               </div>
               <InlineTaskConfigAccordion config={config} {...props}>
                   {props.renderNodeExtras && props.renderNodeExtras(config)}
               </InlineTaskConfigAccordion>
            </div>
        </div>
      ) : (
        <div className="flex-1">
          <InlineTaskConfigAccordion config={config} {...props}>
              {props.renderNodeExtras && props.renderNodeExtras(config)}
          </InlineTaskConfigAccordion>
        </div>
      )}
    </div>
  );
}

export function DraggablePipeline({ 
  pipelineConfigs, 
  pipelineStage,
  onReorder, 
  title, 
  llmProviders,
  onSaveConfig,
  onAddConfig,
  modelLists,
  fetchingModels,
  fetchErrors,
  onFetchModels,
  onDeleteConfig,
  renderNodeExtras
}) {
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [selectedTaskType, setSelectedTaskType] = useState("");

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (active && over && active.id !== over.id) {
      const oldIndex = pipelineConfigs.findIndex(i => i.id === active.id);
      const newIndex = pipelineConfigs.findIndex(i => i.id === over.id);
      const newArray = arrayMove(pipelineConfigs, oldIndex, newIndex);
      onReorder(newArray);
    }
  };

  const handleAddStep = async () => {
    if (!selectedTaskType || !onAddConfig) return;
    const nextOrder = pipelineConfigs ? pipelineConfigs.length : 0;
    await onAddConfig({
      task_type: selectedTaskType,
      pipeline_stage: pipelineStage,
      execution_order: nextOrder,
      is_active: false,
    });
    setSelectedTaskType("");
    setAddDialogOpen(false);
  };

  const addButton = (
    <Button 
      variant="outline" 
      size="sm" 
      className="w-full mt-2 border-dashed gap-1.5"
      onClick={() => setAddDialogOpen(true)}
    >
      <Plus className="w-3.5 h-3.5" />
      Add Pipeline Step
    </Button>
  );

  if (!pipelineConfigs || pipelineConfigs.length === 0) {
      return (
        <div className="space-y-2 relative">
            <h4 className="text-sm font-semibold">{title}</h4>
            <div className="flex justify-center p-6 border border-dashed rounded-md text-sm text-muted-foreground">
                No active nodes in this pipeline.
            </div>
            {addButton}
            <AddStepDialog
              open={addDialogOpen}
              onOpenChange={setAddDialogOpen}
              selectedTaskType={selectedTaskType}
              onSelectTaskType={setSelectedTaskType}
              onAdd={handleAddStep}
            />
        </div>
      );
  }

  return (
    <div className="space-y-2 relative">
      <h4 className="text-sm font-semibold">{title}</h4>
      <DndContext 
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext 
          items={pipelineConfigs.map(c => c.id)}
          strategy={verticalListSortingStrategy}
        >
          {pipelineConfigs.map((config) => (
            <SortablePipelineNode 
              key={config.id} 
              config={config} 
              llmProviders={llmProviders}
              onSaveConfig={onSaveConfig}
              models={modelLists[config.id] || []}
              loadingModels={fetchingModels[config.id]}
              error={fetchErrors[config.id]}
              onFetchModels={onFetchModels}
              isToggleable={true}
              toggleChecked={config.is_active}
              onToggleChange={(val) => onSaveConfig(config.id, { is_active: val })}
              onDeleteConfig={onDeleteConfig}
              renderNodeExtras={renderNodeExtras}
            />
          ))}
        </SortableContext>
      </DndContext>
      {addButton}
      <AddStepDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        selectedTaskType={selectedTaskType}
        onSelectTaskType={setSelectedTaskType}
        onAdd={handleAddStep}
      />
    </div>
  );
}

function AddStepDialog({ open, onOpenChange, selectedTaskType, onSelectTaskType, onAdd }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Pipeline Step</DialogTitle>
          <DialogDescription>
            Select a node type to add to this pipeline. It will be created in a disabled state so you can configure it first.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <Select value={selectedTaskType} onValueChange={onSelectTaskType}>
            <SelectTrigger>
              <SelectValue placeholder="Select task type..." />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(TASK_TYPE_LABELS).map(([key, meta]) => {
                const Icon = meta.icon;
                return (
                  <SelectItem key={key} value={key}>
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4" />
                      {meta.label}
                    </div>
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onAdd} disabled={!selectedTaskType}>Add Step</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Knowledge Pathways (replaces the misleading ordered-pipeline view) ───────
// The knowledge stage is a set of INDEPENDENT producers (each picks its node by
// task_type), not a sequential pipeline. This renders one card per pathway with
// its input → output → trigger metadata + the node's editor (model + prompt),
// so what each node does is legible and the editable prompt is the one the code
// actually uses.
export function KnowledgePathways({
  pipelineConfigs,
  llmProviders,
  onSaveConfig,
  onDeleteConfig,
  modelLists,
  fetchingModels,
  fetchErrors,
  onFetchModels,
  settings,
  onUpdateSettings,
  entityTypes,
}) {
  const findByType = (tt) => (pipelineConfigs || []).find((c) => c.task_type === tt);

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-muted-foreground">
        These are independent generation pathways, not sequential steps. Each produces a different
        kind of knowledge from different input; edit a prompt to tune that pathway specifically.
      </p>
      {KNOWLEDGE_PATHWAYS.map((pw) => {
        const Icon = pw.icon;
        const node = findByType(pw.task_type);
        const pathwayKey = ({
          knowledge_generation: "declarative_knowledge",
          telemetry_reflection: "telemetry_reflection",
          playbook_generation: "playbook_extraction",
          skill_generation: "skill_extraction",
        })[pw.task_type];
        const overrides = pathwayKey
          ? ((settings?.knowledge_generation_pathway_overrides || {})[pathwayKey] || {})
          : null;
        const setOverride = (field, value) => {
          if (!pathwayKey || !onUpdateSettings) return;
          const all = { ...(settings?.knowledge_generation_pathway_overrides || {}) };
          const next = { ...(all[pathwayKey] || {}) };
          if (value === "inherit" || value === "") delete next[field];
          else next[field] = value;
          if (Object.keys(next).length) all[pathwayKey] = next;
          else delete all[pathwayKey];
          onUpdateSettings("knowledge_generation_pathway_overrides", all);
        };
        return (
          <div key={pw.task_type} className={`rounded-lg border ${pw.accent} bg-background overflow-hidden`}>
            <div className="px-4 py-2.5 border-b bg-muted/30 flex items-center gap-2 flex-wrap">
              <Icon className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-semibold">{pw.title}</span>
              <Badge variant="outline" className="text-[10px] font-mono ml-auto">{pw.trigger}</Badge>
            </div>
            <div className="px-4 py-2 text-[11px] text-muted-foreground flex items-center gap-2 flex-wrap border-b">
              <span><span className="font-medium text-foreground">Feeds on:</span> {pw.feeds}</span>
              <ArrowRight className="w-3 h-3" />
              <span><span className="font-medium text-foreground">Produces:</span> {pw.produces}</span>
            </div>
            <div className="p-3">
              {overrides && (
                <div className="mb-3 rounded-md border bg-muted/20 p-3">
                  <div className="text-[11px] font-semibold mb-2">Pathway overrides</div>
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <div className="space-y-1">
                      <OverrideLabel help="Overrides the global enabled switch for this pathway only.">Enabled</OverrideLabel>
                      <Select value={overrides.enabled === undefined ? "inherit" : String(overrides.enabled)}
                        onValueChange={(v) => setOverride("enabled", v === "inherit" ? v : v === "true")}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="inherit">Use global</SelectItem><SelectItem value="true">Enabled</SelectItem><SelectItem value="false">Disabled</SelectItem></SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <OverrideLabel help="Overrides the global minimum generation confidence for this pathway. It is not a similarity score.">Minimum confidence</OverrideLabel>
                      <Input className="h-8 text-xs" type="number" min="0" max="1" step="0.05"
                        placeholder="Use global" value={overrides.min_confidence ?? ""}
                        onChange={(e) => setOverride("min_confidence", e.target.value === "" ? "" : Number(e.target.value))} />
                    </div>
                    <div className="space-y-1">
                      <OverrideLabel help="Overrides the global maximum response length for this pathway.">Max tokens</OverrideLabel>
                      <Input className="h-8 text-xs" type="number" min="256" max="8000"
                        placeholder="Use global" value={overrides.max_tokens ?? ""}
                        onChange={(e) => setOverride("max_tokens", e.target.value === "" ? "" : Number(e.target.value))} />
                    </div>
                    <div className="space-y-1">
                      <OverrideLabel help="Overrides whether records from this pathway begin as Approved or Draft.">Approval policy</OverrideLabel>
                      <Select value={overrides.approval_policy || "inherit"} onValueChange={(v) => setOverride("approval_policy", v)}>
                        <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent><SelectItem value="inherit">Use global</SelectItem><SelectItem value="approve_immediately">Approved</SelectItem><SelectItem value="create_as_draft">Draft</SelectItem></SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )}
              {pathwayKey && <EntityPathwayOverrides entityTypes={entityTypes} pathwayKey={pathwayKey} />}
              {node ? (
                <InlineTaskConfigAccordion
                  config={node}
                  llmProviders={llmProviders}
                  onSaveConfig={onSaveConfig}
                  models={modelLists[node.id] || []}
                  loadingModels={fetchingModels[node.id]}
                  error={fetchErrors[node.id]}
                  onFetchModels={onFetchModels}
                  isToggleable={true}
                  toggleChecked={node.is_active}
                  onToggleChange={(val) => onSaveConfig(node.id, { is_active: val })}
                  onDeleteConfig={onDeleteConfig}
                />
              ) : (
                <div className="text-xs text-muted-foreground italic py-2">
                  No {pw.task_type} node configured — this pathway will use its built-in default prompt and is inactive until a node is added.
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
