import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";
import { getKnowledgeAttachment, proposeKnowledgeDraft, proposeKnowledgeFromAttachments, uploadKnowledgeAttachment } from "@/lib/api";

const CATEGORIES = [
  { value: "best_practices", label: "Best Practices" },
  { value: "lessons_learned", label: "Lessons Learned" },
  { value: "trade_knowledge", label: "Trade Knowledge" },
  { value: "skill", label: "Skill" },
  { value: "playbook", label: "Playbook" },
];

function TagInput({ tags, onChange }) {
  const [newTag, setNewTag] = useState("");

  const addValues = (values) => {
    const next = [...(tags || [])];
    for (const value of values) {
      const tag = String(value || "").trim();
      if (tag && !next.includes(tag)) next.push(tag);
    }
    onChange(next);
  };
  const addTag = () => {
    addValues(newTag.split(","));
    setNewTag("");
  };
  const handleChange = (value) => {
    const parts = value.split(",");
    if (parts.length === 1) return setNewTag(value);
    addValues(parts.slice(0, -1));
    setNewTag(parts[parts.length - 1]);
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
          placeholder="Add tags (comma-separated)..."
          value={newTag}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={addTag}
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

const CATEGORY_FIELDS = {
  best_practices: [
    ["scope", "Scope", "scalar"], ["conditions", "Conditions", "array"], ["exceptions", "Exceptions", "array"],
  ],
  lessons_learned: [
    ["incident_context", "Incident context", "scalar"], ["causal_context", "Causal context", "scalar"],
    ["evidence", "Evidence", "array"], ["qualifications", "Qualifications", "array"],
  ],
  trade_knowledge: [
    ["domain", "Domain", "scalar"], ["jurisdiction", "Jurisdiction", "scalar"], ["material", "Material", "scalar"],
    ["environment", "Environment", "scalar"], ["product", "Product", "scalar"], ["qualifications", "Qualifications", "array"],
  ],
  skill: [
    ["purpose", "Purpose", "scalar"], ["trigger_desc", "When to use", "scalar"], ["procedure", "Procedure", "scalar"],
    ["inputs", "Inputs", "array"], ["outputs", "Outputs", "array"], ["prerequisites", "Prerequisites", "array"],
    ["tools", "Tools and integrations", "array"], ["permissions", "Permissions", "array"], ["side_effects", "Side effects", "array"],
    ["failure_conditions", "Failure conditions", "array"], ["safety_requirements", "Safety requirements", "array"], ["environments", "Applicable environments", "array"],
  ],
  playbook: [
    ["purpose", "Purpose", "scalar"], ["trigger_conditions", "Trigger conditions", "array"], ["prerequisites", "Prerequisites", "array"],
    ["steps", "Ordered steps", "steps"], ["branches", "Branches and decisions", "array"], ["escalation_rules", "Escalation rules", "array"],
    ["rollback", "Rollback and recovery", "array"], ["responsible_roles", "Responsible roles", "array"], ["tools", "Tools and integrations", "array"],
    ["completion_criteria", "Completion criteria", "array"], ["exit_conditions", "Exit conditions", "array"],
  ],
};

function displayMetadataValue(metadata, key, kind) {
  const value = metadata?.[key];
  if (kind === "steps") return (value || []).map((step, index) => `${step?.order || index + 1}. ${step?.action || step}`).join("\n");
  return Array.isArray(value) ? value.join("\n") : (value || "");
}

function StructuredFields({ category, knowledge, setKnowledge }) {
  const fields = CATEGORY_FIELDS[category] || [];
  const update = (key, kind, raw) => {
    let value = raw;
    if (kind === "array") value = raw.split("\n").map(v => v.trim()).filter(Boolean);
    if (kind === "steps") value = raw.split("\n").map(v => v.trim()).filter(Boolean).map((action, index) => {
      const match = action.match(/^(\d+)[.)]\s*(.*)$/);
      return { order: match ? Number(match[1]) : index + 1, action: match ? match[2] : action };
    });
    setKnowledge({ ...knowledge, metadata: { ...(knowledge.metadata || {}), [key]: value } });
  };
  if (!fields.length) return null;
  return <div className="rounded-md border p-3 space-y-3">
    <div><div className="text-sm font-medium">Structured contract</div><p className="text-[11px] text-muted-foreground">These fields are stored in metadata and are rendered into the SKILL.md contract for skills and playbooks.</p></div>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {fields.map(([key, label, kind]) => <div key={key} className={kind === "scalar" && key === "purpose" ? "md:col-span-2" : ""}>
        <Label>{label}</Label>
        <Textarea rows={kind === "scalar" ? 2 : 3} value={displayMetadataValue(knowledge.metadata, key, kind)} onChange={(e) => update(key, kind, e.target.value)} placeholder={kind === "array" || kind === "steps" ? "One item per line" : label} />
      </div>)}
    </div>
  </div>;
}

function AttachmentPanel({ open, knowledge, setKnowledge }) {
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [warnings, setWarnings] = useState([]);

  useEffect(() => { if (!open) { setAttachments([]); setWarnings([]); } }, [open]);

  const updateAttachment = (id, patch) => setAttachments(prev => prev.map(item => item.id === id ? { ...item, ...patch } : item));
  const poll = async (id, attempts = 0) => {
    if (attempts > 120) { updateAttachment(id, { status: "timeout" }); return; }
    try {
      const { data } = await getKnowledgeAttachment(id);
      updateAttachment(id, data);
      if (["queued", "extracting"].includes(data.status)) return setTimeout(() => poll(id, attempts + 1), 1500);
    } catch { if (attempts < 120) setTimeout(() => poll(id, attempts + 1), 1500); }
  };
  const upload = async (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        const { data } = await uploadKnowledgeAttachment(file);
        setAttachments(prev => [...prev.filter(item => item.id !== data.attachment_id), data]);
        poll(data.attachment_id);
      }
      toast.success("Document extraction queued");
    } catch (error) { toast.error(error?.response?.data?.detail || "Document upload failed"); }
    finally { setUploading(false); event.target.value = ""; }
  };
  const ready = attachments.filter(item => item.status === "ready");
  const propose = async () => {
    if (!ready.length || ready.length !== attachments.length) return toast.error("Wait for all documents to finish extraction");
    setProposing(true);
    try {
      const { data } = await proposeKnowledgeFromAttachments({ attachment_ids: ready.map(item => item.id), category: knowledge.category, name: knowledge.name, summary: knowledge.summary });
      const proposal = data.proposal || {};
      setWarnings([...(proposal.warnings || []), ...(proposal.contradictions || [])]);
      setKnowledge({ ...knowledge, name: proposal.name || knowledge.name, summary: proposal.summary || knowledge.summary, content: proposal.content || knowledge.content, metadata: { ...(proposal.metadata || knowledge.metadata || {}), source_traceability: proposal.source_traceability || [], consolidation_warnings: proposal.warnings || [], contradictions: proposal.contradictions || [] }, signals: proposal.signals || knowledge.signals || [], tags: proposal.tags || knowledge.tags || [], attachment_ids: ready.map(item => item.id) });
      toast.success("Editable knowledge proposal generated");
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not generate proposal"); }
    finally { setProposing(false); }
  };
  const insertText = async () => {
    const texts = [];
    for (const item of ready) {
      const { data } = await getKnowledgeAttachment(item.id);
      texts.push(`===== ${data.filename} =====\n${data.extracted_text || ""}`);
    }
    setKnowledge({ ...knowledge, content: texts.join("\n\n---\n\n"), attachment_ids: ready.map(item => item.id) });
  };
  return <div className="rounded-md border p-3 space-y-3">
    <div><div className="text-sm font-medium">Source documents</div><p className="text-[11px] text-muted-foreground">PDF, DOCX, XLSX, TXT, Markdown, and CSV. Extraction runs through the shared parser/OCR pipeline and can process bounded full documents.</p></div>
    <input type="file" multiple accept=".pdf,.docx,.xlsx,.txt,.md,.csv" onChange={upload} disabled={uploading} className="block w-full text-sm" />
    {attachments.map(item => <div key={item.id} className="flex items-center justify-between gap-2 rounded border px-2 py-1.5 text-xs"><span className="truncate">{item.filename || item.id}{item.extraction?.current_page ? ` — page ${item.extraction.current_page}/${item.extraction.total_pages}` : ""}{item.extraction?.pages_omitted ? ` — ${item.extraction.pages_omitted} pages omitted` : ""}</span><Badge variant="outline">{item.status}</Badge></div>)}
    {attachments.length > 0 && <div className="flex gap-2 flex-wrap"><Button type="button" size="sm" variant="outline" disabled={!ready.length} onClick={insertText}>Insert extracted text</Button><Button type="button" size="sm" disabled={!ready.length || ready.length !== attachments.length || proposing} onClick={propose}>{proposing ? "Generating…" : "Generate knowledge draft"}</Button></div>}
    {warnings.length > 0 && <div className="rounded border border-amber-500/40 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-300"><strong>Review warnings:</strong><ul className="list-disc pl-4">{warnings.map((warning, i) => <li key={i}>{typeof warning === "string" ? warning : JSON.stringify(warning)}</li>)}</ul></div>}
  </div>;
}

export function NewKnowledgeDialog({ open, onOpenChange, newKnowledge, setNewKnowledge, onCreate }) {
  const [proposing, setProposing] = useState(false);
  const generateDraft = async () => {
    if (!newKnowledge.content?.trim() && !(newKnowledge.attachment_ids || []).length) {
      toast.error("Add source content or upload a document first");
      return;
    }
    setProposing(true);
    try {
      const { data } = await proposeKnowledgeDraft({
        category: newKnowledge.category || "trade_knowledge",
        name: newKnowledge.name,
        summary: newKnowledge.summary,
        content: newKnowledge.content,
        signals: newKnowledge.signals || [],
        tags: newKnowledge.tags || [],
        metadata: newKnowledge.metadata || {},
        attachment_ids: newKnowledge.attachment_ids || [],
      });
      const proposal = data.proposal || {};
      setNewKnowledge({
        ...newKnowledge,
        name: proposal.name || newKnowledge.name,
        summary: proposal.summary || newKnowledge.summary,
        content: proposal.content || newKnowledge.content,
        signals: proposal.signals || newKnowledge.signals || [],
        tags: proposal.tags || newKnowledge.tags || [],
        metadata: { ...(newKnowledge.metadata || {}), ...(proposal.metadata || {}), source_traceability: proposal.source_traceability || [], consolidation_warnings: proposal.warnings || [], contradictions: proposal.contradictions || [] },
        status: "draft",
      });
      toast.success("Editable structured draft generated");
    } catch (error) { toast.error(error?.response?.data?.detail || "Could not generate draft"); }
    finally { setProposing(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
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
                  <SelectItem value="active">Approved</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <Label>Content {(["skill", "playbook"].includes(newKnowledge.category)) && <span className="text-xs text-muted-foreground">(body; SKILL.md wrapper is generated automatically)</span>}</Label>
            <Textarea value={newKnowledge.content || ""} onChange={(e) => setNewKnowledge({ ...newKnowledge, content: e.target.value })} placeholder={newKnowledge.category === "skill" ? "Procedure or operational behavior" : newKnowledge.category === "playbook" ? "Procedure body; ordered steps go below" : "Knowledge content"} rows={7} />
          </div>
          <div>
            <Label>Summary</Label>
            <Textarea value={newKnowledge.summary || ""} onChange={(e) => setNewKnowledge({ ...newKnowledge, summary: e.target.value })} placeholder="One-line summary (optional)" rows={2} />
          </div>
          <div>
            <Label>Signals <span className="text-xs text-muted-foreground">(comma-separated or press Enter)</span></Label>
            <TagInput tags={newKnowledge.signals || []} onChange={(signals) => setNewKnowledge({ ...newKnowledge, signals })} />
          </div>
          <div>
            <Label>Tags <span className="text-xs text-muted-foreground">(comma-separated or press Enter)</span></Label>
            <TagInput tags={newKnowledge.tags || []} onChange={(tags) => setNewKnowledge({ ...newKnowledge, tags })} />
          </div>
          <StructuredFields category={newKnowledge.category || "trade_knowledge"} knowledge={newKnowledge} setKnowledge={setNewKnowledge} />
          <AttachmentPanel open={open} knowledge={newKnowledge} setKnowledge={setNewKnowledge} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" variant="outline" onClick={generateDraft} disabled={proposing}>{proposing ? "Generating…" : "Generate structured draft"}</Button>
          <Button onClick={onCreate}>Save Knowledge</Button>
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
