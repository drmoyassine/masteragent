import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Trash2, User } from "lucide-react";

export default function MemoryInspector({ editingMemory, setEditingMemory, onUpdate, onDelete }) {
  return (
    <Dialog open={!!editingMemory} onOpenChange={() => setEditingMemory(null)}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Memory Inspector</DialogTitle>
          <DialogDescription>View or edit aggregated memory properties</DialogDescription>
        </DialogHeader>

        {editingMemory && (
          <ScrollArea className="flex-1 overflow-y-auto pr-4">
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Entity Type</Label>
                  <div className="font-medium">{editingMemory.primary_entity_type}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Entity ID</Label>
                  <div className="font-mono text-sm">{editingMemory.primary_entity_id}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Date Generated</Label>
                  <div className="font-medium">{editingMemory.date}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Source Interactions</Label>
                  <div className="font-medium">{editingMemory.interaction_count} records</div>
                </div>
              </div>

              <div>
                <Label>Content Summary</Label>
                <Textarea
                  value={editingMemory.content_summary || ""}
                  onChange={(e) => setEditingMemory({ ...editingMemory, content_summary: e.target.value })}
                  rows={8}
                  className="mt-1"
                />
              </div>

              {editingMemory.intents?.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Intents Detected</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {editingMemory.intents.map((intent, i) => (
                      <Badge key={i} variant="secondary">{intent}</Badge>
                    ))}
                  </div>
                </div>
              )}
              {editingMemory.related_entities?.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Related Entities</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {editingMemory.related_entities.map((entity, i) => (
                      <Badge key={i} variant="outline">
                        <User className="w-3 h-3 mr-1" />
                        {typeof entity === "string" ? entity : entity.name || entity.entity_id}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        )}

        <DialogFooter className="mt-4 sm:justify-between">
          <Button variant="destructive" onClick={onDelete} disabled={!editingMemory}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setEditingMemory(null)}>Cancel</Button>
            <Button onClick={onUpdate} disabled={!editingMemory}>
              Save Changes
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
