import { format } from "date-fns";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Trash2, Check } from "lucide-react";

export default function IntelligenceInspector({ editingIntelligence, setEditingIntelligence, onUpdate, onApprove, onDelete }) {
  return (
    <Dialog open={!!editingIntelligence} onOpenChange={() => setEditingIntelligence(null)}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Intelligence Inspector</DialogTitle>
          <DialogDescription>Review and edit the intelligence report for this entity</DialogDescription>
        </DialogHeader>
        {editingIntelligence && (
          <ScrollArea className="flex-1 overflow-y-auto pr-4">
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs text-muted-foreground">Entity Type</Label>
                  <div className="font-medium">{editingIntelligence.primary_entity_type}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Entity ID</Label>
                  <div className="font-mono text-sm">{editingIntelligence.primary_entity_id}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Created</Label>
                  <div className="font-medium">{format(new Date(editingIntelligence.created_at), "MMM d, yyyy")}</div>
                </div>
                <div>
                  <Label className="text-xs text-muted-foreground">Status</Label>
                  <Badge variant={editingIntelligence.status === "confirmed" ? "default" : "secondary"} className="mt-1">
                    {editingIntelligence.status}
                  </Badge>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Title</Label>
                  <Input
                    value={editingIntelligence.name || ""}
                    onChange={(e) => setEditingIntelligence({ ...editingIntelligence, name: e.target.value })}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label>Signal Type</Label>
                  <Input
                    value={editingIntelligence.knowledge_type || ""}
                    onChange={(e) => setEditingIntelligence({ ...editingIntelligence, knowledge_type: e.target.value })}
                    className="mt-1 font-mono text-sm"
                    placeholder="e.g. risk, budget, objection"
                  />
                </div>
              </div>

              <div>
                <Label>Intelligence Report</Label>
                <Textarea
                  value={editingIntelligence.content || ""}
                  onChange={(e) => setEditingIntelligence({ ...editingIntelligence, content: e.target.value })}
                  rows={7}
                  className="mt-1 text-sm"
                />
              </div>

              <div>
                <Label>Summary <span className="text-muted-foreground text-xs font-normal">(one-line actionable takeaway)</span></Label>
                <Textarea
                  value={editingIntelligence.summary || ""}
                  onChange={(e) => setEditingIntelligence({ ...editingIntelligence, summary: e.target.value })}
                  rows={2}
                  className="mt-1 text-sm"
                />
              </div>

              {editingIntelligence.source_memory_ids?.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Source Memories ({editingIntelligence.source_memory_ids.length})</Label>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {editingIntelligence.source_memory_ids.map((id, i) => (
                      <Badge key={i} variant="outline" className="font-mono text-xs">{id.slice(0, 8)}...</Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        )}
        <DialogFooter className="mt-4 sm:justify-between">
          <Button variant="destructive" onClick={onDelete} disabled={!editingIntelligence}>
            <Trash2 className="w-4 h-4 mr-2" /> Delete
          </Button>
          <div className="flex gap-2">
            {editingIntelligence?.status === "draft" && (
              <Button variant="outline" onClick={() => { onApprove(editingIntelligence.id); setEditingIntelligence(null); }}>
                <Check className="w-4 h-4 mr-2 text-green-500" /> Confirm
              </Button>
            )}
            <Button variant="outline" onClick={() => setEditingIntelligence(null)}>Cancel</Button>
            <Button onClick={onUpdate} disabled={!editingIntelligence}>Save Changes</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
