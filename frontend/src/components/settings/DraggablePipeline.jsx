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
import { GripVertical, Plus } from "lucide-react";
import { InlineTaskConfigAccordion } from "./InlineTaskConfigAccordion";
import { Button } from "@/components/ui/button";
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
