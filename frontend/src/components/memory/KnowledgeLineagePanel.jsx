import { useEffect, useState } from "react";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GitMerge, ArrowRight, Undo2, Loader2 } from "lucide-react";
import { getConsolidationLineage, reverseConsolidationEvent } from "@/lib/api";
import { toast } from "sonner";

/**
 * Renders consolidation lineage for a knowledge record:
 *  - canonical records: predecessors (merged_from) + the event that absorbed them
 *  - retired records: the successor (merged_into) it points to
 * Admins can reverse an applied event from here (dependency-validated).
 */
export default function KnowledgeLineagePanel({ knowledgeId, onOpenKnowledge }) {
  const [lineage, setLineage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [reversing, setReversing] = useState(false);

  useEffect(() => {
    let alive = true;
    if (!knowledgeId) return;
    setLoading(true);
    getConsolidationLineage(knowledgeId)
      .then(({ data }) => { if (alive) setLineage(data); })
      .catch(() => { if (alive) setLineage(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [knowledgeId]);

  if (loading) return <div className="text-xs text-muted-foreground flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> loading lineage…</div>;
  if (!lineage) return null;

  const hasLineage = lineage.merged_into || (lineage.merged_from && lineage.merged_from.length) || lineage.consolidation_event_id;
  if (!hasLineage) return null;

  const event = lineage.event || {};
  const canReverse = !!lineage.consolidation_event_id && event.action === "apply" && !event.reversed_event_id;

  async function handleReverse() {
    if (!lineage.consolidation_event_id) return;
    setReversing(true);
    try {
      await reverseConsolidationEvent(lineage.consolidation_event_id);
      toast.success("Consolidation reversed");
      // Reload lineage
      const { data } = await getConsolidationLineage(knowledgeId);
      setLineage(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reversal failed (a later consolidation may depend on it)");
    } finally { setReversing(false); }
  }

  return (
    <div className="space-y-2">
      <Label className="text-xs text-muted-foreground flex items-center gap-1"><GitMerge className="w-3 h-3" /> Consolidation lineage</Label>

      {lineage.merged_into && (
        <div className="rounded-md border p-2 text-xs">
          <span className="text-muted-foreground">Retired into successor:</span>
          <div className="flex items-center gap-1 mt-1">
            <code className="font-mono">{lineage.merged_into.slice(0, 12)}…</code>
            <ArrowRight className="w-3 h-3" />
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onOpenKnowledge?.(lineage.merged_into)}>
              Open canonical
            </Button>
          </div>
        </div>
      )}

      {lineage.merged_from && lineage.merged_from.length > 0 && (
        <div className="rounded-md border p-2 text-xs">
          <span className="text-muted-foreground">Absorbed {lineage.merged_from.length} predecessor(s):</span>
          <div className="flex flex-wrap gap-1 mt-1">
            {lineage.merged_from.map((id) => (
              <Badge key={id} variant="outline" className="font-mono">{id.slice(0, 8)}…</Badge>
            ))}
          </div>
        </div>
      )}

      {lineage.consolidation_event_id && (
        <div className="rounded-md border p-2 text-xs space-y-1">
          <div><span className="text-muted-foreground">Event:</span> <code className="font-mono">{lineage.consolidation_event_id.slice(0, 12)}…</code></div>
          {event.canonical_strategy && <div><span className="text-muted-foreground">Strategy:</span> {event.canonical_strategy.replace(/_/g, " ")}</div>}
          {event.contradictions?.length > 0 && (
            <div className="text-amber-700">Contradictions: {event.contradictions.length}</div>
          )}
          {canReverse && (
            <Button size="sm" variant="outline" onClick={handleReverse} disabled={reversing} className="mt-1 h-7 text-xs">
              {reversing ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : <Undo2 className="w-3 h-3 mr-1" />}
              Reverse consolidation
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
