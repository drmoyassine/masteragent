import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, GitMerge, AlertTriangle, CheckCircle2, ArrowLeft, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import {
  consolidationPreview, applyConsolidation, regenerateConsolidationPreview,
  getConsolidationMetrics, getKnowledgeDetail,
} from "@/lib/api";

const STEPS = ["Sources", "Proposal", "Edit", "Confirm", "Result"];

/**
 * Multi-step consolidation dialog.
 * Sources → Generate/Review Proposal → Edit Canonical → Confirm → Result.
 *
 * Embedding similarity only GROUPS candidates; the merge decision comes from the
 * category-aware LLM proposal shown here plus admin review. Preview never
 * mutates; apply is transactional.
 */
export default function KnowledgeConsolidationDialog({ open, onOpenChange, selectedIds, onApplied }) {
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sources, setSources] = useState([]);
  const [preview, setPreview] = useState(null); // { preview, sources, metrics, proposal }
  const [selectionMetrics, setSelectionMetrics] = useState(null);
  const [strategy, setStrategy] = useState("update_existing");
  const [targetId, setTargetId] = useState("");
  const [canonical, setCanonical] = useState({ name: "", summary: "", content: "", signals: [], tags: [], metadata: {} });
  const [metadataText, setMetadataText] = useState("{}");
  const [metadataError, setMetadataError] = useState("");
  const [event, setEvent] = useState(null);
  const [error, setError] = useState("");

  const selectionKey = (selectedIds || []).join(",");
  // Reset whenever the dialog opens for a new selection.
  useEffect(() => {
    if (open) {
      setStep(0); setPreview(null); setSelectionMetrics(null); setEvent(null); setError(""); setSources([]);
      setMetadataText("{}"); setMetadataError("");
      setStrategy("update_existing"); setTargetId((selectedIds || [])[0] || "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selectionKey]);

  // Load the full source records when entering the Sources step.
  useEffect(() => {
    if (open && selectedIds?.length && sources.length === 0) {
      (async () => {
        try {
          const rows = await Promise.all((selectedIds || []).map((id) => getKnowledgeDetail(id).then((r) => r.data)));
          setSources(rows);
          const { data: metricData } = await getConsolidationMetrics({ knowledge_ids: selectedIds, origin: "manual" });
          setSelectionMetrics(metricData);
        } catch (e) { setError("Failed to load source records."); }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selectionKey]);

  const category = sources[0]?.category;
  const metrics = preview?.metrics || {};

  async function generateProposal() {
    setLoading(true); setError("");
    try {
      const { data } = await consolidationPreview({ knowledge_ids: selectedIds, origin: "manual", options: { canonical_strategy: strategy, canonical_target_id: targetId || null } });
      setPreview(data);
      const c = data?.proposal?.canonical;
      if (c) {
        setCanonical({ name: c.name || "", summary: c.summary || "", content: c.content || "", signals: c.signals || [], tags: c.tags || [], metadata: c.metadata || {} });
        setMetadataText(JSON.stringify(c.metadata || {}, null, 2));
        setMetadataError("");
      }
      setStep(1);
    } catch (e) {
      setError(_errMsg(e, "Failed to generate proposal"));
    } finally { setLoading(false); }
  }

  async function applyIt() {
    setLoading(true); setError("");
    try {
      const { data } = await applyConsolidation({
        preview_id: preview.preview.id,
        canonical_strategy: strategy,
        canonical_target_id: strategy === "update_existing" ? targetId : null,
        approved_canonical: canonical,
      });
      setEvent(data);
      setStep(4);
      toast.success("Consolidation applied");
      onApplied?.();
    } catch (e) {
      setError(_errMsg(e, "Failed to apply consolidation"));
    } finally { setLoading(false); }
  }

  async function regenerateProposal() {
    if (!preview?.preview?.id) return;
    setLoading(true); setError("");
    try {
      const { data } = await regenerateConsolidationPreview(preview.preview.id);
      setPreview(data);
      const c = data?.proposal?.canonical;
      setCanonical(c ? {
        name: c.name || "", summary: c.summary || "", content: c.content || "",
        signals: c.signals || [], tags: c.tags || [], metadata: c.metadata || {},
      } : { name: "", summary: "", content: "", signals: [], tags: [], metadata: {} });
      setMetadataText(JSON.stringify(c?.metadata || {}, null, 2));
      setMetadataError("");
      toast.success("Proposal regenerated from current source versions");
    } catch (e) {
      setError(_errMsg(e, "Failed to regenerate proposal"));
    } finally { setLoading(false); }
  }

  function close() { onOpenChange(false); }

  function updateMetadata(value) {
    setMetadataText(value);
    try {
      const parsed = JSON.parse(value || "{}");
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("Metadata must be a JSON object");
      setCanonical((current) => ({ ...current, metadata: parsed }));
      setMetadataError("");
    } catch (e) {
      setMetadataError(e.message || "Invalid metadata JSON");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitMerge className="w-5 h-5" /> Knowledge Consolidation
            <Badge>{STEPS[step]}</Badge>
            {category && <Badge variant="outline">{category.replace(/_/g, " ")}</Badge>}
          </DialogTitle>
          <DialogDescription>
            Candidate similarity only groups records — it never decides a merge. Review the proposal, edit, then apply.
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {error && (
            <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{error}</span>
            </div>
          )}

          {/* Step 0: Sources + metrics */}
          {step === 0 && (
            <div className="space-y-3">
              <div className="text-sm font-medium">Selected records ({sources.length})</div>
              <div className="space-y-2">
                {sources.map((s) => (
                  <div key={s.id} className="rounded-md border p-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium truncate">{s.name}</span>
                      <Badge variant="outline">{s.status}</Badge>
                    </div>
                    <div className="text-xs text-muted-foreground line-clamp-2">{s.summary || s.content}</div>
                  </div>
                ))}
              </div>
              <div className="rounded-md bg-muted/40 p-3 text-xs text-muted-foreground">
                A category-aware LLM will read the full content of these records (never their embeddings) and propose a canonical merge.
              </div>
              {selectionMetrics && <MetricBar metrics={selectionMetrics} />}
            </div>
          )}

          {/* Step 1: Proposal review */}
          {step === 1 && preview && (
            <ProposalReview preview={preview} metrics={metrics} />
          )}

          {/* Step 2: Edit canonical */}
          {step === 2 && (
            <div className="space-y-3">
              <div className="text-sm font-medium">Edit the canonical record</div>
              <div className="space-y-1.5">
                <Label className="text-xs">Name</Label>
                <Input value={canonical.name} onChange={(e) => setCanonical({ ...canonical, name: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Summary</Label>
                <Textarea rows={2} value={canonical.summary} onChange={(e) => setCanonical({ ...canonical, summary: e.target.value })} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Content{category === "skill" || category === "playbook" ? " (SKILL.md body)" : ""}</Label>
                <Textarea rows={10} className="font-mono text-xs" value={canonical.content} onChange={(e) => setCanonical({ ...canonical, content: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">Signals (comma-separated)</Label>
                  <Input value={(canonical.signals || []).join(", ")} onChange={(e) => setCanonical({ ...canonical, signals: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Tags (comma-separated)</Label>
                  <Input value={(canonical.tags || []).join(", ")} onChange={(e) => setCanonical({ ...canonical, tags: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) })} />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Metadata (JSON)</Label>
                <Textarea rows={6} className="font-mono text-xs" value={metadataText} onChange={(e) => updateMetadata(e.target.value)} />
                {metadataError && <div className="text-xs text-destructive">{metadataError}</div>}
              </div>
            </div>
          )}

          {/* Step 3: Confirm */}
          {step === 3 && (
            <div className="space-y-3">
              <CanonicalDiff original={preview?.proposal?.canonical} edited={canonical} />
              <div className="space-y-1.5">
                <Label className="text-xs">Canonical strategy</Label>
                <Select value={strategy} onValueChange={setStrategy}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="update_existing">Update one selected record (retire the rest)</SelectItem>
                    <SelectItem value="create_new">Create a new canonical record (retire all sources)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {strategy === "update_existing" && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Record to keep & update</Label>
                  <Select value={targetId} onValueChange={setTargetId}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {sources.map((s) => (
                        <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs">
                Applying retires {strategy === "create_new" ? "all" : "the other"} source(s) and is reversible from the lineage panel.
              </div>
            </div>
          )}

          {/* Step 4: Result */}
          {step === 4 && event && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-emerald-600">
                <CheckCircle2 className="w-5 h-5" /> <span className="font-medium">Consolidation applied</span>
              </div>
              <div className="rounded-md border p-3 text-sm space-y-1">
                <div>Event ID: <code className="text-xs">{event.event?.id}</code></div>
                <div>Canonical: <code className="text-xs">{event.event?.canonical_id}</code></div>
                <div>Strategy: {event.event?.canonical_strategy}</div>
                <div>Retired sources: {(event.sources || []).filter((s) => s.role === "absorbed").length}</div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="mt-2">
          {step > 0 && step < 4 && (
            <Button variant="outline" onClick={() => setStep(step - 1)} disabled={loading}>
              <ArrowLeft className="w-4 h-4 mr-2" /> Back
            </Button>
          )}
          <Button variant="ghost" onClick={close} disabled={loading}>Close</Button>

          {step === 0 && (
            <Button onClick={generateProposal} disabled={loading || sources.length < 2}>
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <GitMerge className="w-4 h-4 mr-2" />}
              Generate Proposal
            </Button>
          )}
          {step === 1 && (
            <>
              <Button variant="outline" onClick={regenerateProposal} disabled={loading}>
                Regenerate Proposal
              </Button>
              <Button onClick={() => setStep(2)} disabled={loading || !preview?.proposal?.canonical}>
                Edit Canonical <ArrowRight className="w-4 h-4 ml-2" />
              </Button>
            </>
          )}
          {step === 2 && (
            <Button onClick={() => setStep(3)} disabled={loading || !!metadataError}>
              Review & Confirm <ArrowRight className="w-4 h-4 ml-2" />
            </Button>
          )}
          {step === 3 && (
            <Button onClick={applyIt} disabled={loading || (strategy === "update_existing" && !targetId)}>
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
              Apply Consolidation
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProposalReview({ preview, metrics }) {
  const p = preview.proposal || {};
  const recColors = {
    merge: "bg-emerald-100 text-emerald-800",
    merge_with_warnings: "bg-amber-100 text-amber-800",
    keep_separate: "bg-blue-100 text-blue-800",
    split_cluster: "bg-purple-100 text-purple-800",
    manual_review: "bg-rose-100 text-rose-800",
  };
  return (
    <div className="space-y-3">
      {preview.preview?.state === "failed" && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
          Proposal validation failed: {(preview.preview?.validation_errors || []).join("; ") || "unknown validation error"}. Regenerate before continuing.
        </div>
      )}
      <div className="flex items-center gap-2">
        <Badge className={recColors[p.recommendation] || "bg-gray-100"}>{(p.recommendation || "—").replace(/_/g, " ")}</Badge>
        {typeof p.confidence === "number" && (
          <span className="text-xs text-muted-foreground">confidence {(p.confidence * 100).toFixed(0)}%</span>
        )}
      </div>
      <MetricBar metrics={metrics} />
      {p.rationale && (
        <div className="rounded-md border p-3 text-sm"><span className="font-medium">Rationale:</span> {p.rationale}</div>
      )}
      <DetailList title="Preserved information" items={p.preserved_information} tone="emerald" />
      <DetailList title="Removed repetition" items={p.removed_repetition} tone="muted" />
      <DetailList title="Warnings" items={p.warnings} tone="amber" />
      <DetailList title="Contradictions" items={p.contradictions} tone="rose" />
      <DetailList title="Unreconciled information" items={p.unreconciled_information} tone="amber" />
      {Array.isArray(p.source_traceability) && p.source_traceability.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-medium">Source traceability</div>
          {p.source_traceability.map((t) => (
            <div key={t.source_id} className="rounded-md border p-2 text-xs">
              <code>{t.source_id}</code>
              {t.retained_items?.length > 0 && <div className="mt-1 text-emerald-700">Kept: {t.retained_items.join("; ")}</div>}
              {t.omitted_as_repetition?.length > 0 && <div className="text-muted-foreground">Omitted: {t.omitted_as_repetition.join("; ")}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function MetricBar({ metrics }) {
  const rows = [
    ["Pairwise min", metrics.pairwise_min],
    ["Cohesion (mean)", metrics.cohesion],
    ["Pairwise max", metrics.pairwise_max],
  ].filter(([, v]) => typeof v === "number");
  const compat = metrics.embedding_compatible || {};
  return (
    <div className="flex flex-wrap gap-2 text-xs">
      {rows.map(([k, v]) => (
        <span key={k} className="rounded-md bg-muted px-2 py-1">{k}: {Number(v).toFixed(3)}</span>
      ))}
      <span className={`rounded-md px-2 py-1 ${compat.all_compatible === false ? "bg-amber-100 text-amber-800" : "bg-muted"}`}>
        embedding {compat.all_compatible === false ? "mismatch" : "compatible"}
      </span>
    </div>
  );
}

function DetailList({ title, items, tone }) {
  if (!items || items.length === 0) return null;
  const toneClass = {
    emerald: "text-emerald-700", muted: "text-muted-foreground",
    amber: "text-amber-700", rose: "text-rose-700",
  }[tone] || "";
  return (
    <div className="space-y-1">
      <div className="text-sm font-medium">{title}</div>
      <ul className={`list-disc pl-5 text-xs space-y-0.5 ${toneClass}`}>
        {items.map((it, i) => <li key={i}>{typeof it === "string" ? it : JSON.stringify(it)}</li>)}
      </ul>
    </div>
  );
}

function CanonicalDiff({ original, edited }) {
  const fields = ["name", "summary", "content"];
  const edits = fields.filter((f) => (original?.[f] || "") !== (edited?.[f] || ""));
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium">Review {edits.length > 0 ? "your edits" : "the canonical record"}</div>
      {edits.length > 0 && (
        <div className="rounded-md border border-amber-300/50 bg-amber-50 dark:bg-amber-950/30 p-2 text-xs">
          Edited fields: {edits.join(", ")}
        </div>
      )}
      <div className="rounded-md border p-3 text-sm space-y-1">
        <div className="font-medium">{edited.name}</div>
        {edited.summary && <div className="text-muted-foreground text-xs">{edited.summary}</div>}
        <pre className="whitespace-pre-wrap text-xs font-mono mt-1 max-h-40 overflow-y-auto">{edited.content}</pre>
      </div>
    </div>
  );
}

function _errMsg(e, fallback) {
  const detail = e?.response?.data?.detail || e?.message;
  return detail ? `${fallback}: ${detail}` : fallback;
}
