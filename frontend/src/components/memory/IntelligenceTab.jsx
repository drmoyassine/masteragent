import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { RefreshCw, Trash2, Check, Edit } from "lucide-react";
import { stringToColor } from "./utils";

export default function IntelligenceTab({
  intelligence, selectedIds, toggleAll, toggleOne,
  onEdit, onApprove, onBulkDelete,
  loading, visCols, renderColumnToggle, onLoad, processingBulk,
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Intelligence (Tier 2)</CardTitle>
          <CardDescription>Deal signals and behavioral patterns extracted from memories</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <div className="flex gap-2 bg-accent px-4 py-1.5 rounded-md items-center border shadow-sm animate-in fade-in zoom-in-95 duration-200">
              <span className="text-sm font-medium mr-2">{selectedIds.length} selected</span>
              <Button variant="destructive" size="sm" onClick={onBulkDelete} disabled={processingBulk}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </div>
          )}
          <Button variant="outline" size="icon" onClick={onLoad} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {renderColumnToggle("intelligence")}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[500px] overflow-auto relative rounded-md border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-background shadow-[0_1px_0_0_hsl(var(--border))]">
              <TableRow>
                {visCols("intelligence").map(col => {
                  if (col.key === "select") return (
                    <TableHead key={col.key} className="w-[40px]">
                      <Checkbox checked={intelligence.length > 0 && selectedIds.length === intelligence.length} onCheckedChange={(c) => toggleAll(c)} />
                    </TableHead>
                  );
                  return <TableHead key={col.key}>{col.label}</TableHead>;
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {intelligence.length === 0 ? (
                <TableRow><TableCell colSpan={visCols("intelligence").length} className="text-center text-muted-foreground py-8">No intelligence found.</TableCell></TableRow>
              ) : intelligence.map(ins => (
                <TooltipProvider key={ins.id}>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <TableRow className={`cursor-pointer hover:bg-accent/50 ${selectedIds.includes(ins.id) ? "bg-accent/30" : ""}`} onClick={() => onEdit(ins)}>
                        {visCols("intelligence").map(col => {
                          switch (col.key) {
                            case "select": return <TableCell key={col.key} onClick={(e) => e.stopPropagation()}><Checkbox checked={selectedIds.includes(ins.id)} onCheckedChange={() => toggleOne(ins.id)} /></TableCell>;
                            case "seq_id": return <TableCell key={col.key} className="font-mono text-muted-foreground">#{ins.seq_id}</TableCell>;
                            case "created_at": return <TableCell key={col.key} className="whitespace-nowrap">{format(new Date(ins.created_at), "MMM d, yyyy")}</TableCell>;
                            case "entity": return (<TableCell key={col.key}><Badge variant="outline" style={{ borderColor: stringToColor(ins.primary_entity_type), color: stringToColor(ins.primary_entity_type) }}>{ins.primary_entity_type}</Badge><span className="font-mono text-xs ml-2 text-muted-foreground">{ins.entity_display_name || ins.primary_entity_id}</span></TableCell>);
                            case "signal": return (<TableCell key={col.key}><Badge variant="outline" style={{ borderColor: stringToColor(ins.knowledge_type), color: stringToColor(ins.knowledge_type) }}>{ins.knowledge_type || "other"}</Badge></TableCell>);
                            case "report": return (<TableCell key={col.key} className="max-w-sm"><div className="font-medium text-sm">{ins.name}</div><div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{ins.summary}</div></TableCell>);
                            case "status": return (<TableCell key={col.key}><Badge variant={ins.status === "confirmed" ? "default" : "secondary"}>{ins.status}</Badge></TableCell>);
                            case "actions": return (<TableCell key={col.key} onClick={(e) => e.stopPropagation()}><div className="flex gap-1">{ins.status === "draft" && (<Button variant="ghost" size="icon" onClick={() => onApprove(ins.id)}><Check className="w-4 h-4 text-green-500" /></Button>)}<Button variant="ghost" size="icon" onClick={() => onEdit(ins)}><Edit className="w-4 h-4" /></Button></div></TableCell>);
                            default: { if (col.key.startsWith('dyn_')) { const pk = col.key.slice(4); const v = ins.entity_properties?.[pk]; return <TableCell key={col.key} className="text-xs">{v != null ? String(v) : "-"}</TableCell>; } return <TableCell key={col.key}>-</TableCell>; }
                          }
                        })}
                      </TableRow>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-2xl bg-secondary text-secondary-foreground border-border break-words shadow-lg pointer-events-none z-40">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{ins.content || ins.summary}</p>
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
