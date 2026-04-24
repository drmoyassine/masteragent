import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { RefreshCw, Trash2, CheckCircle2, XCircle, Edit } from "lucide-react";
import { stringToColor } from "./utils";

export default function InteractionsTab({
  interactions, selectedIds, toggleAll, toggleOne,
  onEdit, onBulkDelete, onBulkReprocess,
  loading, visCols, renderColumnToggle, onLoad, processingBulk,
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Interactions (Tier 0)</CardTitle>
          <CardDescription>Raw inbound and outbound events</CardDescription>
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
          {renderColumnToggle("interactions")}
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-[500px] overflow-auto relative rounded-md border">
          <Table>
            <TableHeader className="sticky top-0 z-10 bg-background shadow-[0_1px_0_0_hsl(var(--border))]">
              <TableRow>
                {visCols("interactions").map(col => {
                  if (col.key === "select") return (
                    <TableHead key={col.key} className="w-[40px]">
                      <Checkbox
                        checked={interactions.length > 0 && selectedIds.length === interactions.length}
                        onCheckedChange={(c) => toggleAll(c)}
                      />
                    </TableHead>
                  );
                  return <TableHead key={col.key}>{col.label}</TableHead>;
                })}
              </TableRow>
            </TableHeader>
            <TableBody>
              {interactions.length === 0 ? (
                <TableRow><TableCell colSpan={visCols("interactions").length} className="text-center text-muted-foreground py-8">No interactions found.</TableCell></TableRow>
              ) : interactions.map(i => (
                <TooltipProvider key={i.id}>
                  <Tooltip delayDuration={300}>
                    <TooltipTrigger asChild>
                      <TableRow className={selectedIds.includes(i.id) ? "bg-accent/30" : ""}>
                        {visCols("interactions").map(col => {
                          switch (col.key) {
                            case "select":
                              return (
                                <TableCell key={col.key}>
                                  <Checkbox checked={selectedIds.includes(i.id)} onCheckedChange={() => toggleOne(i.id)} onClick={(e) => e.stopPropagation()} />
                                </TableCell>
                              );
                            case "seq_id":
                              return <TableCell key={col.key} className="font-mono text-muted-foreground">#{i.seq_id}</TableCell>;
                            case "timestamp":
                              return <TableCell key={col.key} className="whitespace-nowrap">{format(new Date(i.timestamp), "MMM d, yyyy h:mm a")}</TableCell>;
                            case "interaction_type":
                              return (
                                <TableCell key={col.key}>
                                  <Badge variant="outline" style={{ borderColor: stringToColor(i.interaction_type), color: stringToColor(i.interaction_type) }}>
                                    {i.interaction_type}
                                  </Badge>
                                </TableCell>
                              );
                            case "entity_type":
                              return (
                                <TableCell key={col.key}>
                                  <Badge variant="outline" style={{ borderColor: stringToColor(i.primary_entity_type), color: stringToColor(i.primary_entity_type) }}>
                                    {i.primary_entity_type}
                                  </Badge>
                                </TableCell>
                              );
                            case "entity_subtype":
                              return <TableCell key={col.key}>{i.primary_entity_subtype || i.entity_subtype_resolved || "-"}</TableCell>;
                            case "entity_id":
                              return (
                                <TableCell key={col.key}>
                                  {i.entity_display_name ? (
                                    <div>
                                      <div className="text-sm font-medium">{i.entity_display_name}</div>
                                      <div className="font-mono text-[10px] text-muted-foreground">#{i.primary_entity_id}</div>
                                    </div>
                                  ) : (
                                    <span className="font-mono text-xs">{i.primary_entity_id}</span>
                                  )}
                                </TableCell>
                              );
                            case "content":
                              return <TableCell key={col.key} className="max-w-xs truncate">{i.content}</TableCell>;
                            case "agent":
                              return <TableCell key={col.key}>{i.agent_name || i.agent_id}</TableCell>;
                            case "service_status":
                              return (
                                <TableCell key={col.key}>
                                  <div className="flex gap-2 items-center">
                                    {i.has_attachments && (
                                      <TooltipProvider>
                                        <Tooltip>
                                          <TooltipTrigger>
                                            <Badge variant="outline" className={i.processing_errors?.vision ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>
                                              {i.processing_errors?.vision ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                                              Vision
                                            </Badge>
                                          </TooltipTrigger>
                                          {i.processing_errors?.vision && <TooltipContent className="bg-red-950 text-red-100 border-red-900"><p className="max-w-xs">{i.processing_errors.vision}</p></TooltipContent>}
                                        </Tooltip>
                                      </TooltipProvider>
                                    )}
                                    <TooltipProvider>
                                      <Tooltip>
                                        <TooltipTrigger>
                                          <Badge variant="outline" className={i.processing_errors?.embeddings ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>
                                            {i.processing_errors?.embeddings ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                                            Embedding
                                          </Badge>
                                        </TooltipTrigger>
                                        {i.processing_errors?.embeddings && <TooltipContent className="bg-red-950 text-red-100 border-red-900"><p className="max-w-xs">{i.processing_errors.embeddings}</p></TooltipContent>}
                                      </Tooltip>
                                    </TooltipProvider>
                                  </div>
                                </TableCell>
                              );
                            case "status":
                              return <TableCell key={col.key}>{i.status}</TableCell>;
                            case "actions":
                              return (
                                <TableCell key={col.key}>
                                  <Button variant="ghost" size="icon" onClick={() => onEdit(i)}>
                                    <Edit className="w-4 h-4" />
                                  </Button>
                                </TableCell>
                              );
                            default: {
                              if (col.key.startsWith('dyn_')) {
                                const propKey = col.key.slice(4);
                                const val = i.entity_properties?.[propKey];
                                return <TableCell key={col.key} className="text-xs">{val != null ? String(val) : "-"}</TableCell>;
                              }
                              return <TableCell key={col.key}>-</TableCell>;
                            }
                          }
                        })}
                      </TableRow>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-2xl bg-secondary text-secondary-foreground border-border break-words shadow-lg pointer-events-none z-40">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap line-clamp-4">{i.content}</p>
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
