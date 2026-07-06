import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Trash2, Check, Edit, Plus, Search, Download, Archive, ArchiveRestore, Pin } from "lucide-react";

const SUBTABS = [
  { value: "all", label: "All" },
  { value: "best_practices", label: "Best Practices" },
  { value: "lessons_learned", label: "Lessons" },
  { value: "trade_knowledge", label: "Trade" },
  { value: "playbook", label: "Playbooks" },
  { value: "skill", label: "Skills" },
];

const CATEGORY_COLORS = {
  best_practices: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300",
  lessons_learned: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300",
  trade_knowledge: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300",
  skill: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300",
  playbook: "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-300",
};

const CATEGORY_OPTIONS = [
  { value: "all", label: "All Categories" },
  { value: "best_practices", label: "Best Practices" },
  { value: "lessons_learned", label: "Lessons Learned" },
  { value: "trade_knowledge", label: "Trade Knowledge" },
  { value: "skill", label: "Skills" },
  { value: "playbook", label: "Playbooks" },
];

export default function KnowledgeTab({
  knowledge, selectedIds, toggleAll, toggleOne,
  onEdit, onApprove, onDelete, onBulkDelete,
  knowledgeStatusFilter, setKnowledgeStatusFilter,
  categoryFilter = "all", setCategoryFilter,
  tagSearch = "", setTagSearch,
  onShowNewDialog, onShowImportDialog, onArchive, onToggleAlwaysInject,
  loading, visCols, renderColumnToggle,
}) {
  const showInstall = categoryFilter === "skill" || categoryFilter === "playbook";
  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Knowledge Base</CardTitle>
            <CardDescription>Global experiential knowledge, playbooks & skills. Toggle "Always On" to pin a record into every agent's context (e.g. limited-time offers, announcements).</CardDescription>
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
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                placeholder="Search tags..."
                value={tagSearch}
                onChange={(e) => setTagSearch(e.target.value)}
                className="w-[140px] pl-8 h-9"
              />
            </div>
            <Select value={knowledgeStatusFilter} onValueChange={setKnowledgeStatusFilter}>
              <SelectTrigger className="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="draft">Drafts</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="retired">Archived</SelectItem>
              </SelectContent>
            </Select>
            {showInstall && (
              <Button variant="outline" onClick={onShowImportDialog}>
                <Download className="w-4 h-4 mr-2" />
                Install
              </Button>
            )}
            <Button onClick={onShowNewDialog}>
              <Plus className="w-4 h-4 mr-2" />
              New
            </Button>
            {renderColumnToggle("knowledge")}
          </div>
        </div>
        {/* Category sub-tabs */}
        <div className="flex items-center gap-1 border-b -mb-2">
          {SUBTABS.map(t => (
            <button
              key={t.value}
              onClick={() => setCategoryFilter(t.value)}
              className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-colors ${
                categoryFilter === t.value
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {t.label}
            </button>
          ))}
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
                      <TableRow className={`cursor-pointer hover:bg-accent/50 ${selectedIds.includes(k.id) ? "bg-accent/30" : ""}`} onClick={() => onEdit(k)}>
                        {visCols("knowledge").map(col => {
                          switch (col.key) {
                            case "select": return <TableCell key={col.key} onClick={(e) => e.stopPropagation()}><Checkbox checked={selectedIds.includes(k.id)} onCheckedChange={() => toggleOne(k.id)} /></TableCell>;
                            case "seq_id": return <TableCell key={col.key} className="font-mono text-muted-foreground">#{k.seq_id}</TableCell>;
                            case "category": {
                              const cat = k.category || "trade_knowledge";
                              return (<TableCell key={col.key}>
                                <Badge className={CATEGORY_COLORS[cat] || "bg-gray-100 text-gray-800"}>{cat.replace(/_/g, " ")}</Badge>
                              </TableCell>);
                            }
                            case "name": return <TableCell key={col.key} className="font-medium">{k.name}</TableCell>;
                            case "content": return <TableCell key={col.key} className="max-w-[250px] truncate">{k.content}</TableCell>;
                            case "always_inject": {
                              const on = !!(k.metadata && k.metadata.always_inject);
                              const isSystem = k.source_pathway === "system";
                              return (<TableCell key={col.key} onClick={(e) => e.stopPropagation()}>
                                <div className="flex items-center gap-1.5">
                                  <Switch checked={on} disabled={isSystem} onCheckedChange={() => onToggleAlwaysInject && onToggleAlwaysInject(k)} />
                                  {on && <Pin className="w-3 h-3 text-primary" />}
                                </div>
                              </TableCell>);
                            }
                            case "quality_score": {
                              const qs = k.quality_score;
                              const color = qs == null ? "text-muted-foreground" : qs >= 0.7 ? "text-green-600" : qs >= 0.4 ? "text-amber-600" : "text-red-600";
                              return <TableCell key={col.key} className={`font-mono ${color}`}>{qs != null ? qs.toFixed(2) : "—"}</TableCell>;
                            }
                            case "merge_count": return <TableCell key={col.key} className="text-center">{k.merge_count || 0}</TableCell>;
                            case "source_pathway": return (<TableCell key={col.key}><Badge variant="outline" className="text-xs">{k.source_pathway || "—"}</Badge></TableCell>);
                            case "status": return (<TableCell key={col.key}><Badge variant={k.status === "active" || k.visibility === "approved" ? "default" : "secondary"}>{k.status || k.visibility}</Badge></TableCell>);
                            case "actions": {
                              const isRetired = k.status === "retired";
                              return (<TableCell key={col.key} onClick={(e) => e.stopPropagation()}><div className="flex gap-1">
                                {(k.status === "draft" || k.visibility === "draft") && (<Button variant="ghost" size="icon" title="Activate" onClick={() => onApprove(k.id)}><Check className="w-4 h-4 text-green-500" /></Button>)}
                                <Button variant="ghost" size="icon" title="Edit" onClick={() => onEdit(k)}><Edit className="w-4 h-4" /></Button>
                                {onArchive && (isRetired
                                  ? <Button variant="ghost" size="icon" title="Restore" onClick={() => onArchive(k.id, false)}><ArchiveRestore className="w-4 h-4 text-amber-500" /></Button>
                                  : <Button variant="ghost" size="icon" title="Archive" onClick={() => onArchive(k.id, true)}><Archive className="w-4 h-4 text-muted-foreground" /></Button>)}
                                <Button variant="ghost" size="icon" title="Delete" onClick={() => onDelete(k.id)}><Trash2 className="w-4 h-4 text-destructive" /></Button>
                              </div></TableCell>);
                            }
                            default: return <TableCell key={col.key}>-</TableCell>;
                          }
                        })}
                      </TableRow>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" className="max-w-2xl bg-secondary text-secondary-foreground border-border break-words shadow-lg pointer-events-none z-40">
                      <p className="text-sm leading-relaxed whitespace-pre-wrap">{k.summary || k.content}</p>
                      {k.tags && k.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {k.tags.map((t, i) => <Badge key={i} variant="outline" className="text-xs">{t}</Badge>)}
                        </div>
                      )}
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
