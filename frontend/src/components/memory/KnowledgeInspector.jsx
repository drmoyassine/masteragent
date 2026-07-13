import { useState } from "react";
import { format } from "date-fns";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Trash2, Check, X, Plus, ThumbsUp, ThumbsDown } from "lucide-react";
import KnowledgeLineagePanel from "./KnowledgeLineagePanel";

const CATEGORY_COLORS = {
  best_practices: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300",
  lessons_learned: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300",
  trade_knowledge: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
  skill: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300",
  playbook: "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-300",
};

export default function KnowledgeInspector({ editingKnowledge, setEditingKnowledge, onUpdate, onApprove, onDelete, onFeedback, onOpenKnowledge }) {
  const [newTag, setNewTag] = useState("");

  if (!editingKnowledge) return null;

  const cat = editingKnowledge.category || "trade_knowledge";
  const meta = editingKnowledge.metadata || {};
  const feedbackDisabled = editingKnowledge.source_pathway === "system";

  const addTag = () => {
    const tag = newTag.trim();
    if (!tag) return;
    const tags = [...(editingKnowledge.tags || [])];
    if (!tags.includes(tag)) {
      tags.push(tag);
      setEditingKnowledge({ ...editingKnowledge, tags });
    }
    setNewTag("");
  };

  const removeTag = (tag) => {
    setEditingKnowledge({
      ...editingKnowledge,
      tags: (editingKnowledge.tags || []).filter(t => t !== tag),
    });
  };

  const handleFeedback = (outcome) => {
    if (onFeedback) onFeedback(editingKnowledge.id, outcome);
  };

  return (
    <Dialog open={!!editingKnowledge} onOpenChange={() => setEditingKnowledge(null)}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Knowledge Inspector
            <Badge className={CATEGORY_COLORS[cat] || "bg-gray-100 text-gray-800"}>
              {cat.replace(/_/g, " ")}
            </Badge>
          </DialogTitle>
          <DialogDescription>Review and edit this knowledge record</DialogDescription>
        </DialogHeader>
        <ScrollArea className="flex-1 overflow-y-auto pr-4">
          <div className="space-y-4 py-4">
            {/* Header metadata grid */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label className="text-xs text-muted-foreground">Created</Label>
                <div className="font-medium">
                  {editingKnowledge.created_at ? format(new Date(editingKnowledge.created_at), "MMM d, yyyy HH:mm") : "—"}
                </div>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Status</Label>
                <Badge variant={editingKnowledge.status === "active" ? "default" : "secondary"} className="mt-1">
                  {editingKnowledge.status || "draft"}
                </Badge>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Source Pathway</Label>
                <Badge variant="outline" className="mt-1">{editingKnowledge.source_pathway || "experiential"}</Badge>
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Quality Score</Label>
                <div className={`font-mono font-medium ${editingKnowledge.quality_score >= 0.7 ? "text-green-600" : editingKnowledge.quality_score >= 0.4 ? "text-amber-600" : "text-red-600"}`}>
                  {editingKnowledge.quality_score != null ? editingKnowledge.quality_score.toFixed(3) : "—"}
                </div>
                {editingKnowledge.quality_components?.score_basis === "human_approved_manual" && (
                  <div className="text-[11px] text-green-600">Human-approved manual record</div>
                )}
              </div>
              {(editingKnowledge.merge_count > 0) && (
                <>
                  <div>
                    <Label className="text-xs text-muted-foreground">Merge Count</Label>
                    <div className="font-mono">{editingKnowledge.merge_count}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Last Merged</Label>
                    <div className="font-medium">
                      {editingKnowledge.last_merged_at ? format(new Date(editingKnowledge.last_merged_at), "MMM d, yyyy") : "—"}
                    </div>
                  </div>
                </>
              )}
              {editingKnowledge.version > 1 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Version</Label>
                  <div className="font-mono">v{editingKnowledge.version}{editingKnowledge.parent_id && ` (parent: ${editingKnowledge.parent_id.slice(0, 8)}...)`}</div>
                </div>
              )}
            </div>

            {editingKnowledge.quality_components?.components && (
              <div className="rounded-md border p-3 space-y-2">
                <Label className="text-xs text-muted-foreground">Score breakdown</Label>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {Object.entries(editingKnowledge.quality_components.components).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-2"><span className="text-muted-foreground">{key.replace(/_/g, " ")}</span><span className="font-mono">{Number(value).toFixed(2)}</span></div>
                  ))}
                </div>
              </div>
            )}

            <Separator />

            {/* Name */}
            <div>
              <Label>Name</Label>
              <Input
                value={editingKnowledge.name || ""}
                onChange={(e) => setEditingKnowledge({ ...editingKnowledge, name: e.target.value })}
                className="mt-1"
              />
            </div>

            {/* Content */}
            <div>
              <Label>Content</Label>
              <Textarea
                value={editingKnowledge.content || ""}
                onChange={(e) => setEditingKnowledge({ ...editingKnowledge, content: e.target.value })}
                rows={6}
                className="mt-1 text-sm"
              />
            </div>

            {/* Summary */}
            <div>
              <Label>Summary</Label>
              <Textarea
                value={editingKnowledge.summary || ""}
                onChange={(e) => setEditingKnowledge({ ...editingKnowledge, summary: e.target.value })}
                rows={2}
                className="mt-1 text-sm"
              />
            </div>

            {/* Signals (domain topics, separate from category) */}
            <div>
              <Label>Signals</Label>
              <Input
                value={(editingKnowledge.signals || []).join(", ")}
                onChange={(e) => setEditingKnowledge({ ...editingKnowledge, signals: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })}
                className="mt-1 font-mono text-sm"
                placeholder="Comma-separated defined signal names"
              />
            </div>

            {/* Tags */}
            <div>
              <Label>Tags</Label>
              <div className="flex flex-wrap gap-1.5 mt-1 mb-2">
                {(editingKnowledge.tags || []).map((tag, i) => (
                  <Badge key={i} variant="secondary" className="gap-1 pr-1">
                    {tag}
                    <button onClick={() => removeTag(tag)} className="hover:text-destructive">
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

            {/* Category-specific metadata */}
            {cat === "playbook" && (
              <>
                <Separator />
                <div>
                  <Label className="text-xs text-muted-foreground">Playbook Details</Label>
                  <div className="mt-2 space-y-3">
                    {meta.trigger_conditions?.length > 0 && (
                      <div>
                        <Label className="text-sm font-medium">Trigger Conditions</Label>
                        <ul className="mt-1 space-y-1">
                          {meta.trigger_conditions.map((tc, i) => (
                            <li key={i} className="text-sm bg-muted/50 rounded px-2 py-1">{typeof tc === "string" ? tc : JSON.stringify(tc)}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {meta.steps?.length > 0 && (
                      <div>
                        <Label className="text-sm font-medium">Steps ({meta.steps.length})</Label>
                        <ol className="mt-1 space-y-1">
                          {meta.steps.map((step, i) => (
                            <li key={i} className="text-sm flex gap-2">
                              <span className="font-mono text-muted-foreground">{step.order || i + 1}.</span>
                              <span>{step.action || step}</span>
                              {step.skill_id && <Badge variant="outline" className="text-xs ml-auto">skill: {step.skill_id.slice(0, 8)}</Badge>}
                            </li>
                          ))}
                        </ol>
                      </div>
                    )}
                    {meta.skill_ids?.length > 0 && (
                      <div>
                        <Label className="text-sm font-medium">Linked Skills</Label>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {meta.skill_ids.map((sid, i) => (
                            <Badge key={i} variant="outline" className="font-mono text-xs">{sid.slice(0, 8)}...</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {cat === "skill" && (
              <>
                <Separator />
                <div>
                  <Label className="text-xs text-muted-foreground">Skill Details</Label>
                  <div className="mt-2 space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <Label className="text-sm font-medium">Type</Label>
                        <Badge variant="outline" className="ml-2">{meta.skill_type || "hard"}</Badge>
                      </div>
                      <div>
                        <Label className="text-sm font-medium">Trigger</Label>
                        <span className="text-sm ml-1">{meta.trigger_desc || "—"}</span>
                      </div>
                    </div>
                    {meta.procedure && (
                      <div>
                        <Label className="text-sm font-medium">Procedure</Label>
                        <p className="text-sm mt-1 bg-muted/50 rounded p-2">{meta.procedure}</p>
                      </div>
                    )}
                    {meta.playbook_ids?.length > 0 && (
                      <div>
                        <Label className="text-sm font-medium">Linked Playbooks</Label>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {meta.playbook_ids.map((pid, i) => (
                            <Badge key={i} variant="outline" className="font-mono text-xs">{pid.slice(0, 8)}...</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {/* Feedback */}
            <Separator />
            <div>
              <Label className="text-xs text-muted-foreground">Feedback</Label>
              <div className="flex items-center gap-3 mt-2">
                <div className="flex items-center gap-1">
                  <ThumbsUp className="w-4 h-4 text-green-600" />
                  <span className="font-mono text-sm">{editingKnowledge.success_count || 0}</span>
                </div>
                <div className="flex items-center gap-1">
                  <ThumbsDown className="w-4 h-4 text-red-600" />
                  <span className="font-mono text-sm">{editingKnowledge.failure_count || 0}</span>
                </div>
                {onFeedback && !feedbackDisabled && (
                  <>
                    <Button variant="outline" size="sm" className="ml-2" onClick={() => handleFeedback("success")}>
                      <ThumbsUp className="w-3 h-3 mr-1" /> Success
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => handleFeedback("failure")}>
                      <ThumbsDown className="w-3 h-3 mr-1" /> Failure
                    </Button>
                  </>
                )}
                {feedbackDisabled && (
                  <span className="ml-2 text-xs text-muted-foreground">System skills do not collect usage feedback.</span>
                )}
              </div>
              {editingKnowledge.feedback_notes?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {editingKnowledge.feedback_notes.map((note, i) => (
                    <div key={i} className="text-xs flex gap-2 items-center">
                      <Badge variant={note.outcome === "success" ? "default" : "destructive"} className="text-[10px] px-1.5 py-0">
                        {note.outcome}
                      </Badge>
                      <span className="text-muted-foreground">{note.notes || note.timestamp}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Source intelligence */}
            {editingKnowledge.source_intelligence_ids?.length > 0 && (
              <>
                <Separator />
                <div>
                  <Label className="text-xs text-muted-foreground">Source Intelligence ({editingKnowledge.source_intelligence_ids.length})</Label>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {editingKnowledge.source_intelligence_ids.map((id, i) => (
                      <Badge key={i} variant="outline" className="font-mono text-xs">{id.slice(0, 8)}...</Badge>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Consolidation lineage (canonical + retired records) */}
            <KnowledgeLineagePanel knowledgeId={editingKnowledge.id} onOpenKnowledge={onOpenKnowledge} />
          </div>
        </ScrollArea>
        <DialogFooter className="mt-4 sm:justify-between">
          <Button variant="destructive" onClick={() => onDelete(editingKnowledge.id)} disabled={!editingKnowledge}>
            <Trash2 className="w-4 h-4 mr-2" /> Delete
          </Button>
          <div className="flex gap-2">
            {(editingKnowledge.status === "draft") && onApprove && (
              <Button variant="outline" onClick={() => { onApprove(editingKnowledge.id); setEditingKnowledge(null); }}>
                <Check className="w-4 h-4 mr-2 text-green-500" /> Activate
              </Button>
            )}
            <Button variant="outline" onClick={() => setEditingKnowledge(null)}>Cancel</Button>
            <Button onClick={onUpdate} disabled={!editingKnowledge}>Save Changes</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
