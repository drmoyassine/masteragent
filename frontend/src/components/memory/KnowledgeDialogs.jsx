import { useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, X } from "lucide-react";

const CATEGORIES = [
  { value: "best_practices", label: "Best Practices" },
  { value: "lessons_learned", label: "Lessons Learned" },
  { value: "trade_knowledge", label: "Trade Knowledge" },
  { value: "skill", label: "Skill" },
  { value: "playbook", label: "Playbook" },
];

function TagInput({ tags, onChange }) {
  const [newTag, setNewTag] = useState("");

  const addTag = () => {
    const tag = newTag.trim();
    if (!tag || tags.includes(tag)) return;
    onChange([...tags, tag]);
    setNewTag("");
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {tags.map((tag, i) => (
          <Badge key={i} variant="secondary" className="gap-1 pr-1">
            {tag}
            <button onClick={() => onChange(tags.filter((_, j) => j !== i))} className="hover:text-destructive">
              <X className="w-3 h-3" />
            </button>
          </Badge>
        ))}
      </div>
      <div className="flex gap-2">
        <Input
          placeholder="Add tag..."
          value={newTag}
          onChange={(e) => setNewTag(e.target.value)}
          className="h-8 text-sm"
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTag())}
        />
        <Button variant="outline" size="sm" onClick={addTag}>
          <Plus className="w-3 h-3" />
        </Button>
      </div>
    </div>
  );
}

export function NewKnowledgeDialog({ open, onOpenChange, newKnowledge, setNewKnowledge, onCreate }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create New Knowledge</DialogTitle>
          <DialogDescription>Add a curated knowledge item to your knowledge base</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label>Name</Label>
            <Input value={newKnowledge.name} onChange={(e) => setNewKnowledge({ ...newKnowledge, name: e.target.value })} placeholder="Knowledge title" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Category</Label>
              <Select value={newKnowledge.category || "trade_knowledge"} onValueChange={(v) => setNewKnowledge({ ...newKnowledge, category: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map(c => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Status</Label>
              <Select value={newKnowledge.status || "draft"} onValueChange={(v) => setNewKnowledge({ ...newKnowledge, status: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Content</Label>
            <Textarea value={newKnowledge.content || ""} onChange={(e) => setNewKnowledge({ ...newKnowledge, content: e.target.value })} placeholder="Knowledge content" rows={5} />
          </div>
          <div>
            <Label>Summary</Label>
            <Textarea value={newKnowledge.summary || ""} onChange={(e) => setNewKnowledge({ ...newKnowledge, summary: e.target.value })} placeholder="One-line summary (optional)" rows={2} />
          </div>
          <div>
            <Label>Tags</Label>
            <TagInput tags={newKnowledge.tags || []} onChange={(tags) => setNewKnowledge({ ...newKnowledge, tags })} />
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

export function ImportSkillDialog({ open, onOpenChange, importText, setImportText, importCategory, setImportCategory, importing, onImport }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Install Skill / Playbook (SKILL.md)</DialogTitle>
          <DialogDescription>
            Paste an agent-skills-standard SKILL.md document. Stored verbatim, deduplicated against
            existing records, imported as a draft. Frontmatter name/description become name/summary.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex items-center gap-2">
            <Label>Category</Label>
            <Select value={importCategory} onValueChange={setImportCategory}>
              <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="skill">Skill</SelectItem>
                <SelectItem value="playbook">Playbook</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Textarea
            className="font-mono text-[12px]"
            rows={14}
            placeholder={"---\nname: my-skill\ndescription: what it does and when to use it\n---\n\n# My Skill\n..."}
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onImport} disabled={importing}>{importing ? "Importing…" : "Install"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
