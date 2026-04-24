import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export function NewKnowledgeDialog({ open, onOpenChange, newLesson, setNewLesson, lessonTypes, onCreate }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Knowledge</DialogTitle>
          <DialogDescription>Add a curated knowledge to your knowledge base</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label>Name</Label>
            <Input value={newLesson.name} onChange={(e) => setNewLesson({ ...newLesson, name: e.target.value })} placeholder="Knowledge title" />
          </div>
          <div>
            <Label>Type</Label>
            <Select value={newLesson.type} onValueChange={(v) => setNewLesson({ ...newLesson, type: v })}>
              <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
              <SelectContent>
                {lessonTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Body</Label>
            <Textarea value={newLesson.body} onChange={(e) => setNewLesson({ ...newLesson, body: e.target.value })} placeholder="Knowledge content (Markdown supported)" rows={6} />
          </div>
          <div>
            <Label>Status</Label>
            <Select value={newLesson.status} onValueChange={(v) => setNewLesson({ ...newLesson, status: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="draft">Draft</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onCreate}>Create Knowledge</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function EditKnowledgeDialog({ editingLesson, setEditingLesson, lessonTypes, onUpdate }) {
  return (
    <Dialog open={!!editingLesson} onOpenChange={() => setEditingLesson(null)}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit Knowledge</DialogTitle></DialogHeader>
        {editingLesson && (
          <div className="space-y-4 py-4">
            <div>
              <Label>Name</Label>
              <Input value={editingLesson.name} onChange={(e) => setEditingLesson({ ...editingLesson, name: e.target.value })} />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={editingLesson.type} onValueChange={(v) => setEditingLesson({ ...editingLesson, type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {lessonTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Body</Label>
              <Textarea value={editingLesson.body} onChange={(e) => setEditingLesson({ ...editingLesson, body: e.target.value })} rows={6} />
            </div>
            <div>
              <Label>Status</Label>
              <Select value={editingLesson.status} onValueChange={(v) => setEditingLesson({ ...editingLesson, status: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => setEditingLesson(null)}>Cancel</Button>
          <Button onClick={onUpdate}>Update Knowledge</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
