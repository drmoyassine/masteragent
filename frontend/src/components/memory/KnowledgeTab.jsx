import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash2, Check, Edit, Plus } from "lucide-react";

export default function KnowledgeTab({
  knowledge, selectedIds, toggleAll, toggleOne,
  onEdit, onApprove, onDelete, onBulkDelete,
  lessonStatusFilter, setLessonStatusFilter,
  onShowNewDialog, lessonTypes, getLessonTypeColor,
  loading, visCols, renderColumnToggle,
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Knowledge (Tier 3)</CardTitle>
          <CardDescription>Global system-wide rules extracted from intelligence</CardDescription>
        </div>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <div className="flex gap-2 bg-accent px-4 py-1.5 rounded-md items-center border shadow-sm animate-in fade-in zoom-in-95 duration-200">
              <span className="text-sm font-medium mr-2">{selectedIds.length} selected</span>
              <Button variant="destructive" size="sm" onClick={onBulkDelete}>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </div>
          )}
          <Select value={lessonStatusFilter} onValueChange={setLessonStatusFilter}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="draft">Drafts</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={onShowNewDialog}>
            <Plus className="w-4 h-4 mr-2" />
            New Knowledge
          </Button>
          {renderColumnToggle("knowledge")}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[500px] overflow-auto relative rounded-md border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-background shadow-[0_1px_0_0_hsl(var(--border))]">
              <TableRow>
                {visCols("knowledge").map(col => {
                  if (col.key === "select") return (
                    <TableHead key={col.key} className="w-[40px]">
                      <Checkbox checked={knowledge.length > 0 && selectedIds.length === knowledge.length} onCheckedChange={(c) => toggleAll(c)} />
                    </TableHead>
                  );
                  return <TableHead key={col.key}>{col.label}</TableHead>;
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {knowledge.length === 0 ? (
                <TableRow><TableCell colSpan={visCols("knowledge").length} className="text-center text-muted-foreground py-8">No knowledge found.</TableCell></TableRow>
              ) : knowledge.map(k => (
                <TooltipProvider key={k.id}>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <TableRow className={`cursor-pointer hover:bg-accent/50 ${selectedIds.includes(k.id) ? "bg-accent/30" : ""}`}>
                        {visCols("knowledge").map(col => {
                          switch (col.key) {
                            case "select": return <TableCell key={col.key} onClick={(e) => e.stopPropagation()}><Checkbox checked={selectedIds.includes(k.id)} onCheckedChange={() => toggleOne(k.id)} /></TableCell>;
                            case "seq_id": return <TableCell key={col.key} className="font-mono text-muted-foreground">#{k.seq_id}</TableCell>;
                            case "type": return (<TableCell key={col.key}><div className="flex items-center gap-2"><div className="w-3 h-3 rounded-full" style={{ backgroundColor: getLessonTypeColor(k.knowledge_type) }} /><Badge variant="outline">{k.knowledge_type}</Badge></div></TableCell>);
                            case "name": return <TableCell key={col.key} className="font-medium">{k.name}</TableCell>;
                            case "content": return <TableCell key={col.key} className="max-w-[250px] truncate">{k.content}</TableCell>;
                            case "status": return (<TableCell key={col.key}><Badge variant={k.visibility === "approved" ? "default" : "secondary"}>{k.visibility}</Badge></TableCell>);
                            case "actions": return (<TableCell key={col.key} onClick={(e) => e.stopPropagation()}><div className="flex gap-1">{k.visibility === "draft" && (<Button variant="ghost" size="icon" onClick={() => onApprove(k.id)}><Check className="w-4 h-4 text-green-500" /></Button>)}<Button variant="ghost" size="icon" onClick={() => onEdit(k)}><Edit className="w-4 h-4" /></Button><Button variant="ghost" size="icon" onClick={() => onDelete(k.id)}><Trash2 className="w-4 h-4 text-destructive" /></Button></div></TableCell>);
                            default: return <TableCell key={col.key}>-</TableCell>;
                          }
                        })}
                      </TableRow>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-2xl bg-secondary text-secondary-foreground border-border break-words shadow-lg pointer-events-none z-40">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{k.summary || k.content}</p>
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
