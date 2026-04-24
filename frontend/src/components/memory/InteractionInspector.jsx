import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2, AlertCircle } from "lucide-react";

export default function InteractionInspector({ editingInteraction, setEditingInteraction, entityTypes, onUpdate, onDelete }) {
  return (
    <Dialog open={!!editingInteraction} onOpenChange={() => setEditingInteraction(null)}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Interaction Inspector</DialogTitle>
          <DialogDescription>
            {editingInteraction?.status === "pending"
              ? "Edit raw interaction properties before they are processed by the memory pipeline."
              : "This interaction is locked because it has already been processed."}
          </DialogDescription>
        </DialogHeader>

        {editingInteraction && (
          <ScrollArea className="flex-1 pr-4">
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Interaction Type</Label>
                  <Input
                    value={editingInteraction.interaction_type}
                    onChange={(e) => setEditingInteraction({ ...editingInteraction, interaction_type: e.target.value })}
                    disabled={editingInteraction.status !== "pending"}
                  />
                </div>
                <div>
                  <Label>Source</Label>
                  <Input
                    value={editingInteraction.source}
                    onChange={(e) => setEditingInteraction({ ...editingInteraction, source: e.target.value })}
                    disabled={editingInteraction.status !== "pending"}
                  />
                </div>
                <div>
                  <Label>Entity Type</Label>
                  <Select
                    value={editingInteraction.primary_entity_type}
                    onValueChange={(v) => setEditingInteraction({ ...editingInteraction, primary_entity_type: v })}
                    disabled={editingInteraction.status !== "pending"}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {entityTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Entity Sub-Type</Label>
                  <Input
                    value={editingInteraction.primary_entity_subtype || ""}
                    onChange={(e) => setEditingInteraction({ ...editingInteraction, primary_entity_subtype: e.target.value })}
                    disabled={editingInteraction.status !== "pending"}
                  />
                </div>
                <div className="col-span-2">
                  <Label>Entity ID</Label>
                  <Input
                    value={editingInteraction.primary_entity_id}
                    onChange={(e) => setEditingInteraction({ ...editingInteraction, primary_entity_id: e.target.value })}
                    disabled={editingInteraction.status !== "pending"}
                    className="font-mono text-sm"
                  />
                </div>
              </div>

              <div>
                <Label>Interaction Blob</Label>
                <Textarea
                  value={editingInteraction.content}
                  onChange={(e) => setEditingInteraction({ ...editingInteraction, content: e.target.value })}
                  rows={10}
                  disabled={editingInteraction.status !== "pending"}
                  className="font-mono text-sm"
                />
              </div>

              {editingInteraction.processing_errors && Object.keys(editingInteraction.processing_errors).length > 0 && (
                <div className="bg-red-950/20 border border-red-900/50 rounded-md p-3 mt-4">
                  <Label className="text-red-400 mb-2 block flex items-center"><AlertCircle className="w-4 h-4 mr-2" /> Captured Pipeline Errors</Label>
                  <pre className="text-xs text-red-300/80 font-mono overflow-x-auto">
                    {JSON.stringify(editingInteraction.processing_errors, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </ScrollArea>
        )}

        <DialogFooter className="mt-4 sm:justify-between">
          <Button variant="destructive" onClick={onDelete} disabled={!editingInteraction}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setEditingInteraction(null)}>Cancel</Button>
            <Button
              onClick={onUpdate}
              disabled={!editingInteraction || editingInteraction.status !== "pending"}
            >
              Save Changes
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
