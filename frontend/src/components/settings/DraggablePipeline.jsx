import React from "react";
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
import { GripVertical } from "lucide-react";
import { InlineTaskConfigAccordion } from "./InlineTaskConfigAccordion";
import { Button } from "@/components/ui/button";

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
  onReorder, 
  title, 
  llmProviders,
  onSaveConfig,
  modelLists,
  fetchingModels,
  fetchErrors,
  onFetchModels,
  onDeleteConfig,
  renderNodeExtras
}) {
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

  if (!pipelineConfigs || pipelineConfigs.length === 0) {
      return (
        <div className="space-y-2 relative">
            <h4 className="text-sm font-semibold">{title}</h4>
            <div className="flex justify-center p-6 border border-dashed rounded-md text-sm text-muted-foreground">
                No active nodes in this pipeline.
            </div>
            <Button variant="outline" size="sm" className="w-full mt-2 border-dashed">
                + Add Pipeline Step
            </Button>
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
      <Button variant="outline" size="sm" className="w-full mt-2 border-dashed">
        + Add Pipeline Step
      </Button>
    </div>
  );
}
