import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { RefreshCw, Trash2, CheckCircle2, XCircle, Check } from "lucide-react";
import { stringToColor } from "./utils";

export default function MemoriesTab({
  memories, selectedIds, toggleAll, toggleOne,
  onEdit, onBulkDelete, onBulkReprocess,
  loading, visCols, renderColumnToggle, onLoad, processingBulk,
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Memories (Tier 1)</CardTitle>
          <CardDescription>Daily summaries of interactions for entities</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <div className="flex gap-2 bg-accent px-4 py-1.5 rounded-md items-center border shadow-sm animate-in fade-in zoom-in-95 duration-200">
              <span className="text-sm font-medium mr-2">{selectedIds.length} selected</span>
              <Button variant="outline" size="sm" onClick={onBulkReprocess} disabled={processingBulk}>
                {processingBulk ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                Re-Process
              </Button>
              <Button variant="destructive" size="sm" onClick={onBulkDelete} disabled={processingBulk}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </div>
          )}
          <Button variant="outline" size="icon" onClick={onLoad} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {renderColumnToggle("memories")}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[500px] overflow-auto relative rounded-md border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-background shadow-[0_1px_0_0_hsl(var(--border))]">
              <TableRow>
                {visCols("memories").map(col => {
                  if (col.key === "select") return (
                    <TableHead key={col.key} className="w-[40px]">
                      <Checkbox checked={memories.length > 0 && selectedIds.length === memories.length} onCheckedChange={(c) => toggleAll(c)} />
                    </TableHead>
                  );
                  return <TableHead key={col.key}>{col.label}</TableHead>;
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {memories.length === 0 ? (
                <TableRow><TableCell colSpan={visCols("memories").length} className="text-center text-muted-foreground py-8">No memories found.</TableCell></TableRow>
              ) : memories.map(m => (
                <TooltipProvider key={m.id}>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <TableRow className="cursor-pointer hover:bg-accent/50" onClick={() => onEdit(m)}>
                        {visCols("memories").map(col => {
                          switch (col.key) {
                            case "select": return <TableCell key={col.key} onClick={(e) => e.stopPropagation()}><Checkbox checked={selectedIds.includes(m.id)} onCheckedChange={() => toggleOne(m.id)} /></TableCell>;
                            case "seq_id": return <TableCell key={col.key} className="font-mono text-muted-foreground">#{m.seq_id}</TableCell>;
                            case "date": return <TableCell key={col.key} className="whitespace-nowrap">{m.date}</TableCell>;
                            case "entity_type": return <TableCell key={col.key}><Badge variant="outline" style={{ borderColor: stringToColor(m.primary_entity_type), color: stringToColor(m.primary_entity_type) }}>{m.primary_entity_type}</Badge></TableCell>;
                            case "entity_subtype": return <TableCell key={col.key} className="text-xs">{m.entity_subtype_resolved || "-"}</TableCell>;
                            case "entity_id": return (<TableCell key={col.key}><div className="flex flex-col">{m.entity_display_name && <span className="text-xs font-medium">{m.entity_display_name}</span>}<span className="font-mono text-xs text-muted-foreground">{m.primary_entity_id}</span></div></TableCell>);
                            case "interaction_count": return <TableCell key={col.key}>{m.interaction_count}</TableCell>;
                            case "service_status": return (<TableCell key={col.key}><div className="flex gap-2 items-center"><TooltipProvider><Tooltip><TooltipTrigger><Badge variant="outline" className={m.processing_errors?.summarization ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>{m.processing_errors?.summarization ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}Summarization</Badge></TooltipTrigger>{m.processing_errors?.summarization && <TooltipContent side="top" className="bg-red-950 text-red-100 border-red-900 z-50"><p className="max-w-xs">{m.processing_errors.summarization}</p></TooltipContent>}</Tooltip></TooltipProvider><TooltipProvider><Tooltip><TooltipTrigger><Badge variant="outline" className={m.processing_errors?.embeddings ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>{m.processing_errors?.embeddings ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}Embedding</Badge></TooltipTrigger>{m.processing_errors?.embeddings && <TooltipContent side="top" className="bg-red-950 text-red-100 border-red-900 z-50"><p className="max-w-xs">{m.processing_errors.embeddings}</p></TooltipContent>}</Tooltip></TooltipProvider></div></TableCell>);
                            case "compacted": return <TableCell key={col.key}>{m.compacted ? <Check className="w-4 h-4 text-green-500" /> : ""}</TableCell>;
                            default: { if (col.key.startsWith('dyn_')) { const pk = col.key.slice(4); const v = m.entity_properties?.[pk]; return <TableCell key={col.key} className="text-xs">{v != null ? String(v) : "-"}</TableCell>; } return <TableCell key={col.key}>-</TableCell>; }
                          }
                        })}
                      </TableRow>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-2xl bg-secondary text-secondary-foreground border-border break-words shadow-lg pointer-events-none z-40">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{m.content_summary}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}
