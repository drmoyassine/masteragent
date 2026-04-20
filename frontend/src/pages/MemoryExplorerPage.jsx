import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { format, subDays, subMonths, formatISO } from "date-fns";
import api, {
  getInteractionsAdmin,
  getMemoriesAdmin,
  getInsightsAdmin,
  updateInsightAdmin,
  deleteInsightAdmin,
  getLessonsAdmin,
  getMemoryDetail,
  updateMemoryAdmin,
  deleteMemoryAdmin,
  bulkDeleteMemoriesAdmin,
  bulkReprocessMemoriesAdmin,
  updateInteractionAdmin,
  deleteInteractionAdmin,
  createLessonAdmin,
  updateLessonAdmin,
  deleteLessonAdmin,
  bulkDeleteInteractionsAdmin,
  bulkReprocessInteractionsAdmin,
  getInteractionFilterOptionsAdmin,
  getEntityTypes,
  getLessonTypes,
} from "@/lib/api";
import { MultiSelect } from "@/components/ui/multi-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Database,
  User,
  MessageSquare,
  GraduationCap,
  Calendar,
  Edit,
  Trash2,
  Plus,
  Check,
  RefreshCw,
  Lightbulb,
  Search,
  XCircle,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const stringToColor = (str) => {
  if (!str) return 'hsl(0, 0%, 50%)';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 70%, 40%)`;
};

export default function MemoryExplorerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Deep linking: initialize tab from URL, validate against available tabs
  const validTabs = ["interactions", "memories", "intelligence", "knowledge"];
  const urlTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(validTabs.includes(urlTab) ? urlTab : "interactions");
  const [loading, setLoading] = useState(false);
  const [processingBulk, setProcessingBulk] = useState(false);

  // Global filters
  const [appliedFilter, setAppliedFilter] = useState({ 
    entity_types: [], 
    interaction_types: [],
    entity_id: "",
    time_range: "all"
  });
  
  const [entityIdInput, setEntityIdInput] = useState("");

  // Config meta & Dynamic Options
  const [entityTypes, setEntityTypes] = useState([]);
  const [filterOptions, setFilterOptions] = useState({ entity_types: [], interaction_types: [] });
  const [lessonTypes, setLessonTypes] = useState([]);

  // Datasets
  const [interactions, setInteractions] = useState([]);
  const [memories, setMemories] = useState([]);
  const [intelligence, setInsights] = useState([]);
  const [knowledge, setLessons] = useState([]);

  // Additional knowledge state
  const [lessonStatusFilter, setLessonStatusFilter] = useState("all");
  const [editingLesson, setEditingLesson] = useState(null);
  const [newLesson, setNewLesson] = useState({ name: "", type: "", body: "", status: "draft" });
  const [showNewLessonDialog, setShowNewLessonDialog] = useState(false);

  // Memory detail state
  const [selectedMemory, setSelectedMemory] = useState(null);

  // Interaction Inspector State
  const [editingInteraction, setEditingInteraction] = useState(null);

  // Memory Inspector State
  const [editingMemory, setEditingMemory] = useState(null);

  // Intelligence Inspector State
  const [editingIntelligence, setEditingIntelligence] = useState(null);
  
  // Bulk Operations State
  const [selectedInteractionIds, setSelectedInteractionIds] = useState([]);
  const [selectedMemoryIds, setSelectedMemoryIds] = useState([]);

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      const [entityRes, lessonTypeRes] = await Promise.all([
        getEntityTypes(),
        getLessonTypes(),
      ]);
      setEntityTypes(entityRes.data);
      setLessonTypes(lessonTypeRes.data);
    } catch (error) {
      console.error("Failed to load config data:", error);
    }
  };

  // Debounce entityIdInput
  useEffect(() => {
    const handler = setTimeout(() => {
      const val = entityIdInput.trim();
      if (val.length === 0 || val.length >= 3) {
        setAppliedFilter(prev => ({ ...prev, entity_id: val }));
      }
    }, 500);
    return () => clearTimeout(handler);
  }, [entityIdInput]);

  const getFetchParams = useCallback(() => {
    const params = {};
    if (appliedFilter.entity_types && appliedFilter.entity_types.length > 0) {
      params.entity_types = appliedFilter.entity_types.join(",");
    }
    if (appliedFilter.interaction_types && appliedFilter.interaction_types.length > 0) {
      params.interaction_types = appliedFilter.interaction_types.join(",");
    }
    if (appliedFilter.entity_id && appliedFilter.entity_id.trim() !== "") {
      params.entity_id = appliedFilter.entity_id.trim();
    }
    if (appliedFilter.time_range && appliedFilter.time_range !== "all") {
        const now = new Date();
        let sinceDate;
        switch(appliedFilter.time_range) {
            case 'last_24h': sinceDate = subDays(now, 1); break;
            case 'last_3d': sinceDate = subDays(now, 3); break;
            case 'last_7d': sinceDate = subDays(now, 7); break;
            case 'last_30d': sinceDate = subDays(now, 30); break;
            case 'last_60d': sinceDate = subDays(now, 60); break;
            default: break;
        }
        if (sinceDate) {
            params.since = formatISO(sinceDate);
        }
    }
    return params;
  }, [appliedFilter]);

  const loadFilterOptions = useCallback(async () => {
      try {
          const res = await getInteractionFilterOptionsAdmin(getFetchParams());
          if (res.data) {
              setFilterOptions({
                  entity_types: (res.data.entity_types || []).map(e => ({ label: e, value: e })),
                  interaction_types: (res.data.interaction_types || []).map(i => ({ label: i, value: i }))
              });
          }
      } catch (error) {
          console.error("Failed to load filter options", error);
      }
  }, [getFetchParams]);

  // Loaders
  const loadInteractions = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getInteractionsAdmin(getFetchParams());
      setInteractions(res.data?.interactions || []);
    } catch (error) {
      toast.error("Failed to load interactions");
      setInteractions([]);
    } finally {
      setLoading(false);
    }
  }, [getFetchParams]);

  const loadMemories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getMemoriesAdmin(getFetchParams());
      setMemories(res.data?.memories || []);
    } catch (error) {
      toast.error("Failed to load memories");
      setMemories([]);
    } finally {
      setLoading(false);
    }
  }, [getFetchParams]);

  const loadInsights = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getInsightsAdmin(getFetchParams());
      setInsights(res.data?.intelligence || []);
    } catch (error) {
      toast.error("Failed to load intelligence");
      setInsights([]);
    } finally {
      setLoading(false);
    }
  }, [getFetchParams]);

  const loadLessons = useCallback(async () => {
    setLoading(true);
    try {
      const params = getFetchParams();
      if (lessonStatusFilter !== "all") params.status = lessonStatusFilter;
      const res = await getLessonsAdmin(params);
      setLessons(res.data?.knowledge || []);
    } catch (error) {
      console.error("Failed to load knowledge:", error);
      setLessons([]);
    } finally {
      setLoading(false);
    }
  }, [getFetchParams, lessonStatusFilter]);

  useEffect(() => {
    loadFilterOptions();
    if (activeTab === "interactions") loadInteractions();
    else if (activeTab === "memories") loadMemories();
    else if (activeTab === "intelligence") loadInsights();
    else if (activeTab === "knowledge") loadLessons();
  }, [activeTab, loadInteractions, loadMemories, loadInsights, loadLessons, loadFilterOptions]);

  // Modals interaction logic
  const handleCreateLesson = async () => {
    if (!newLesson.name || !newLesson.type || !newLesson.body) {
      toast.error("Please fill all fields");
      return;
    }
    try {
      await createLessonAdmin(newLesson);
      toast.success("Knowledge created");
      setShowNewLessonDialog(false);
      setNewLesson({ name: "", type: "", body: "", status: "draft" });
      loadLessons();
    } catch (error) {
      toast.error("Failed to create knowledge");
    }
  };

  const handleUpdateLesson = async () => {
    if (!editingLesson) return;
    try {
      await updateLessonAdmin(editingLesson.id, {
        name: editingLesson.name,
        type: editingLesson.type,
        body: editingLesson.body,
        status: editingLesson.status,
      });
      toast.success("Knowledge updated");
      setEditingLesson(null);
      loadLessons();
    } catch (error) {
      toast.error("Failed to update knowledge");
    }
  };

  const handleApproveLesson = async (lessonId) => {
    try {
      await updateLessonAdmin(lessonId, { status: "approved" });
      toast.success("Knowledge approved");
      loadLessons();
    } catch (error) {
      toast.error("Failed to approve knowledge");
    }
  };

  const handleDeleteLesson = async (lessonId) => {
    if (!window.confirm("Delete this knowledge?")) return;
    try {
      await deleteLessonAdmin(lessonId);
      toast.success("Knowledge deleted");
      loadLessons();
    } catch (error) {
      toast.error("Failed to delete knowledge");
    }
  };

  const loadMemoryDetail = async (memoryId) => {
    try {
      const res = await getMemoryDetail(memoryId);
      setSelectedMemory(res.data);
    } catch (error) {
      toast.error("Failed to load memory details");
    }
  };

  const getLessonTypeColor = (typeName) => {
    const type = lessonTypes.find(t => t.name === typeName);
    return type?.color || "#6B7280";
  };

  const handleUpdateInteraction = async () => {
    if (!editingInteraction) return;
    try {
      await updateInteractionAdmin(editingInteraction.id, {
        interaction_type: editingInteraction.interaction_type,
        primary_entity_type: editingInteraction.primary_entity_type,
        primary_entity_subtype: editingInteraction.primary_entity_subtype,
        primary_entity_id: editingInteraction.primary_entity_id,
        content: editingInteraction.content,
        source: editingInteraction.source,
      });
      toast.success("Interaction updated successfully");
      setEditingInteraction(null);
      loadInteractions();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to update interaction");
    }
  };

  const handleDeleteInteraction = async () => {
    if (!editingInteraction) return;
    if (!window.confirm("Delete this interaction? This action cannot be reversed.")) return;
    try {
      await deleteInteractionAdmin(editingInteraction.id);
      toast.success("Interaction deleted successfully");
      setEditingInteraction(null);
      loadInteractions();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to delete interaction");
    }
  };

  // Bulk Handlers
  const toggleSelectAllInteractions = (checked) => {
    if (checked) {
      setSelectedInteractionIds(interactions.map(i => i.id));
    } else {
      setSelectedInteractionIds([]);
    }
  };

  const toggleInteraction = (id) => {
    setSelectedInteractionIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selectedInteractionIds.length} interactions? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteInteractionsAdmin({ interaction_ids: selectedInteractionIds });
      toast.success(`Deleted ${res.data.deleted} interactions`);
      setSelectedInteractionIds([]);
      loadInteractions();
    } catch (error) {
      toast.error("Failed to delete interactions");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkReprocess = async () => {
    if (!window.confirm(`Queue ${selectedInteractionIds.length} interactions for background reprocessing?`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkReprocessInteractionsAdmin({ interaction_ids: selectedInteractionIds });
      toast.success(`Queued ${res.data.queued} interactions sequentially`);
      setSelectedInteractionIds([]);
      loadInteractions();
    } catch (error) {
      toast.error("Failed to queue interactions");
    } finally {
      setProcessingBulk(false);
    }
  };

  const toggleSelectAllMemories = (checked) => {
    if (checked) setSelectedMemoryIds(memories.map(m => m.id));
    else setSelectedMemoryIds([]);
  };

  const toggleMemory = (id) => {
    setSelectedMemoryIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const handleBulkDeleteMemories = async () => {
    if (!window.confirm(`Delete ${selectedMemoryIds.length} memories? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteMemoriesAdmin({ memory_ids: selectedMemoryIds });
      toast.success(`Deleted ${res.data.deleted} memories`);
      setSelectedMemoryIds([]);
      loadMemories();
    } catch (error) {
      toast.error("Failed to delete memories");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkReprocessMemories = async () => {
    if (!window.confirm(`Drop ${selectedMemoryIds.length} memories and re-queue their interactions?`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkReprocessMemoriesAdmin({ memory_ids: selectedMemoryIds });
      toast.success(`Dropped memories and re-queued ${res.data.queued} generation jobs`);
      setSelectedMemoryIds([]);
      loadMemories();
      loadInteractions();
    } catch (error) {
      toast.error("Failed to queue memories");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleUpdateIntelligence = async () => {
    if (!editingIntelligence) return;
    try {
      await updateInsightAdmin(editingIntelligence.id, {
        name: editingIntelligence.name,
        knowledge_type: editingIntelligence.knowledge_type,
        content: editingIntelligence.content,
        summary: editingIntelligence.summary,
      });
      toast.success("Intelligence updated");
      setEditingIntelligence(null);
      loadInsights();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to update intelligence");
    }
  };

  const handleApproveIntelligence = async (id) => {
    try {
      await updateInsightAdmin(id, { status: "confirmed" });
      toast.success("Intelligence confirmed");
      loadInsights();
    } catch (error) {
      toast.error("Failed to confirm intelligence");
    }
  };

  const handleDeleteIntelligence = async () => {
    if (!editingIntelligence) return;
    if (!window.confirm("Delete this intelligence record? This cannot be reversed.")) return;
    try {
      await deleteInsightAdmin(editingIntelligence.id);
      toast.success("Intelligence deleted");
      setEditingIntelligence(null);
      loadInsights();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to delete intelligence");
    }
  };

  const handleUpdateMemory = async () => {
    if (!editingMemory) return;
    try {
      await updateMemoryAdmin(editingMemory.id, {
        content_summary: editingMemory.content_summary,
      });
      toast.success("Memory updated successfully");
      setEditingMemory(null);
      loadMemories();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to update memory");
    }
  };

  const handleDeleteMemory = async () => {
    if (!editingMemory) return;
    if (!window.confirm("Delete this memory? This action cannot be reversed.")) return;
    try {
      await deleteMemoryAdmin(editingMemory.id);
      toast.success("Memory deleted successfully");
      setEditingMemory(null);
      loadMemories();
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Failed to delete memory");
    }
  };

  return (
    <div className="space-y-6" data-testid="memory-explorer-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory Explorer</h1>
          <p className="text-muted-foreground">View and curate agent memories across all 4 interaction tiers</p>
        </div>
      </div>

      {/* Global Filter Bar */}
      <Card className="bg-card">
        <CardContent className="p-4 flex flex-wrap gap-4 items-end">
          <div className="space-y-1">
            <Label>Entity Type</Label>
            <MultiSelect
              options={filterOptions.entity_types}
              selected={appliedFilter.entity_types}
              onChange={(val) => setAppliedFilter({ ...appliedFilter, entity_types: val })}
              placeholder="All Entity Types"
              className="w-48"
            />
          </div>
          <div className="space-y-1">
            <Label>Interaction Type</Label>
            <MultiSelect
              options={filterOptions.interaction_types}
              selected={appliedFilter.interaction_types}
              onChange={(val) => setAppliedFilter({ ...appliedFilter, interaction_types: val })}
              placeholder="All Interaction Types"
              className="w-64"
            />
          </div>
          <div className="space-y-1">
            <Label>Time Range</Label>
            <Select value={appliedFilter.time_range} onValueChange={(v) => setAppliedFilter({ ...appliedFilter, time_range: v })}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Time</SelectItem>
                <SelectItem value="last_24h">Last 24 Hours</SelectItem>
                <SelectItem value="last_3d">Last 3 Days</SelectItem>
                <SelectItem value="last_7d">Last 7 Days</SelectItem>
                <SelectItem value="last_30d">Last 30 Days</SelectItem>
                <SelectItem value="last_60d">Last 60 Days</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1 flex-1 min-w-[200px]">
            <Label>Entity ID (Debounced text filter)</Label>
            <Input
              placeholder="Start typing specific entity ID (min 3 chars)..."
              value={entityIdInput}
              onChange={(e) => setEntityIdInput(e.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={(tab) => {
        setActiveTab(tab);
        setSearchParams({ tab }, { replace: true });
      }} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
          <TabsTrigger value="interactions" className="gap-2" data-testid="tab-interactions">
            <User className="w-4 h-4" /> Interactions
          </TabsTrigger>
          <TabsTrigger value="memories" className="gap-2" data-testid="tab-daily">
            <Calendar className="w-4 h-4" /> Memories
          </TabsTrigger>
          <TabsTrigger value="intelligence" className="gap-2" data-testid="tab-intelligence">
            <Lightbulb className="w-4 h-4" /> Intelligence
          </TabsTrigger>
          <TabsTrigger value="knowledge" className="gap-2" data-testid="tab-knowledge">
            <GraduationCap className="w-4 h-4" /> Knowledge
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Interactions */}
        <TabsContent value="interactions" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Interactions (Tier 0)</CardTitle>
                <CardDescription>Raw inbound and outbound events</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {selectedInteractionIds.length > 0 && (
                    <div className="flex gap-2 bg-accent px-4 py-1.5 rounded-md items-center border shadow-sm animate-in fade-in zoom-in-95 duration-200">
                        <span className="text-sm font-medium mr-2">{selectedInteractionIds.length} selected</span>
                        <Button variant="outline" size="sm" onClick={handleBulkReprocess} disabled={processingBulk}>
                             {processingBulk ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                             Re-Process
                        </Button>
                        <Button variant="destructive" size="sm" onClick={handleBulkDelete} disabled={processingBulk}>
                             <Trash2 className="w-4 h-4 mr-2" />
                             Delete
                        </Button>
                    </div>
                )}
                <Button variant="outline" size="icon" onClick={loadInteractions} disabled={loading}>
                   <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
               <ScrollArea className="h-[500px]">
                 <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[40px]">
                            <Checkbox 
                                checked={interactions.length > 0 && selectedInteractionIds.length === interactions.length} 
                                onCheckedChange={(c) => toggleSelectAllInteractions(c)} 
                            />
                        </TableHead>
                        <TableHead>ID</TableHead>
                        <TableHead>Time</TableHead>
                        <TableHead>Interaction Type</TableHead>
                        <TableHead>Entity Type</TableHead>
                        <TableHead>Entity Sub-Type</TableHead>
                        <TableHead>Entity ID</TableHead>
                        <TableHead>Interaction Blob</TableHead>
                        <TableHead>Agent</TableHead>
                        <TableHead>Service Status</TableHead>
                        <TableHead>Memorization</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                       {interactions.length === 0 ? (
                          <TableRow><TableCell colSpan={10} className="text-center text-muted-foreground py-8">No interactions found.</TableCell></TableRow>
                       ) : interactions.map(i => (
                         <TableRow key={i.id} className={selectedInteractionIds.includes(i.id) ? "bg-accent/30" : ""}>
                            <TableCell>
                               <Checkbox 
                                   checked={selectedInteractionIds.includes(i.id)} 
                                   onCheckedChange={() => toggleInteraction(i.id)}
                                   onClick={(e) => e.stopPropagation()}
                               />
                            </TableCell>
                            <TableCell className="font-mono text-muted-foreground">#{i.seq_id}</TableCell>
                            <TableCell className="whitespace-nowrap">{format(new Date(i.timestamp), "MMM d, yyyy h:mm a")}</TableCell>
                            <TableCell>
                               <Badge variant="outline" style={{ borderColor: stringToColor(i.interaction_type), color: stringToColor(i.interaction_type) }}>
                                  {i.interaction_type}
                               </Badge>
                            </TableCell>
                            <TableCell>
                               <Badge variant="outline" style={{ borderColor: stringToColor(i.primary_entity_type), color: stringToColor(i.primary_entity_type) }}>
                                  {i.primary_entity_type}
                               </Badge>
                            </TableCell>
                            <TableCell>{i.primary_entity_subtype || "-"}</TableCell>
                            <TableCell className="font-mono text-xs">{i.primary_entity_id}</TableCell>
                            <TableCell className="max-w-xs truncate">{i.content}</TableCell>
                            <TableCell>{i.agent_name || i.agent_id}</TableCell>
                            <TableCell>
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
                            <TableCell>{i.status}</TableCell>
                            <TableCell>
                               <Button variant="ghost" size="icon" onClick={() => setEditingInteraction(i)}>
                                  <Edit className="w-4 h-4" />
                               </Button>
                            </TableCell>
                         </TableRow>
                       ))}
                    </TableBody>
                 </Table>
               </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Memories */}
        <TabsContent value="memories" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Memories (Tier 1)</CardTitle>
                <CardDescription>Daily summaries of interactions for entities</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {selectedMemoryIds.length > 0 && (
                    <div className="flex gap-2 bg-accent px-4 py-1.5 rounded-md items-center border shadow-sm animate-in fade-in zoom-in-95 duration-200">
                        <span className="text-sm font-medium mr-2">{selectedMemoryIds.length} selected</span>
                        <Button variant="outline" size="sm" onClick={handleBulkReprocessMemories} disabled={processingBulk}>
                             {processingBulk ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <RefreshCw className="w-4 h-4 mr-2" />}
                             Re-Process
                        </Button>
                        <Button variant="destructive" size="sm" onClick={handleBulkDeleteMemories} disabled={processingBulk}>
                             <Trash2 className="w-4 h-4 mr-2" />
                             Delete
                        </Button>
                    </div>
                )}
                <Button variant="outline" size="icon" onClick={loadMemories} disabled={loading}>
                   <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
               <ScrollArea className="h-[500px]">
                 <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-[40px]">
                            <Checkbox 
                                checked={memories.length > 0 && selectedMemoryIds.length === memories.length} 
                                onCheckedChange={(c) => toggleSelectAllMemories(c)} 
                            />
                        </TableHead>
                        <TableHead>ID</TableHead>
                        <TableHead>Date</TableHead>
                        <TableHead>Entity Type</TableHead>
                        <TableHead>Entity Subtype</TableHead>
                        <TableHead>Entity ID</TableHead>
                        <TableHead>Interactions</TableHead>
                        <TableHead>Service Status</TableHead>
                        <TableHead>Compacted</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                        {memories.length === 0 ? (
                          <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No memories found.</TableCell></TableRow>
                       ) : memories.map(m => (
                         <TooltipProvider key={m.id}>
                           <Tooltip delayDuration={300}>
                             <TooltipTrigger asChild>
                               <TableRow className="cursor-pointer hover:bg-accent/50" onClick={() => setEditingMemory(m)}>
                                  <TableCell onClick={(e) => e.stopPropagation()}>
                                     <Checkbox 
                                        checked={selectedMemoryIds.includes(m.id)} 
                                        onCheckedChange={() => toggleMemory(m.id)} 
                                     />
                                  </TableCell>
                                  <TableCell className="font-mono text-muted-foreground">#{m.seq_id}</TableCell>
                                  <TableCell className="whitespace-nowrap">{m.date}</TableCell>
                                  <TableCell>
                                     <Badge variant="outline" style={{ borderColor: stringToColor(m.primary_entity_type), color: stringToColor(m.primary_entity_type) }}>
                                        {m.primary_entity_type}
                                     </Badge>
                                  </TableCell>
                                  <TableCell>-</TableCell>
                                  <TableCell className="font-mono text-xs">{m.primary_entity_id}</TableCell>
                                  <TableCell>{m.interaction_count}</TableCell>
                                  <TableCell>
                                     <div className="flex gap-2 items-center">
                                       <TooltipProvider>
                                         <Tooltip>
                                           <TooltipTrigger>
                                             <Badge variant="outline" className={m.processing_errors?.summarization ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>
                                               {m.processing_errors?.summarization ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                                               Summarization
                                             </Badge>
                                           </TooltipTrigger>
                                           {m.processing_errors?.summarization && <TooltipContent side="top" className="bg-red-950 text-red-100 border-red-900 z-50"><p className="max-w-xs">{m.processing_errors.summarization}</p></TooltipContent>}
                                         </Tooltip>
                                       </TooltipProvider>
                                       <TooltipProvider>
                                         <Tooltip>
                                           <TooltipTrigger>
                                             <Badge variant="outline" className={m.processing_errors?.embeddings ? "border-red-500/50 text-red-500" : "border-emerald-500/50 text-emerald-500"}>
                                               {m.processing_errors?.embeddings ? <XCircle className="w-3 h-3 mr-1" /> : <CheckCircle2 className="w-3 h-3 mr-1" />}
                                               Embedding
                                             </Badge>
                                           </TooltipTrigger>
                                           {m.processing_errors?.embeddings && <TooltipContent side="top" className="bg-red-950 text-red-100 border-red-900 z-50"><p className="max-w-xs">{m.processing_errors.embeddings}</p></TooltipContent>}
                                         </Tooltip>
                                       </TooltipProvider>
                                     </div>
                                  </TableCell>
                                  <TableCell>{m.compacted ? <Check className="w-4 h-4 text-green-500" /> : ""}</TableCell>
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
               </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Intelligence */}
        <TabsContent value="intelligence" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Intelligence (Tier 2)</CardTitle>
                <CardDescription>Deal signals and behavioral patterns extracted from memories</CardDescription>
              </div>
              <Button variant="outline" size="icon" onClick={loadInsights} disabled={loading}>
                 <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </Button>
            </CardHeader>
            <CardContent>
               <ScrollArea className="h-[500px]">
                 <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Created</TableHead>
                        <TableHead>Entity</TableHead>
                        <TableHead>Signal</TableHead>
                        <TableHead>Intelligence Report</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                       {intelligence.length === 0 ? (
                          <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground py-8">No intelligence found.</TableCell></TableRow>
                       ) : intelligence.map(ins => (
                         <TableRow key={ins.id} className="cursor-pointer hover:bg-accent/50" onClick={() => setEditingIntelligence(ins)}>
                            <TableCell className="font-mono text-muted-foreground">#{ins.seq_id}</TableCell>
                            <TableCell className="whitespace-nowrap">{format(new Date(ins.created_at), "MMM d, yyyy")}</TableCell>
                            <TableCell>
                               <Badge variant="outline" style={{ borderColor: stringToColor(ins.primary_entity_type), color: stringToColor(ins.primary_entity_type) }}>
                                  {ins.primary_entity_type}
                               </Badge>
                               <span className="font-mono text-xs ml-2 text-muted-foreground">{ins.primary_entity_id}</span>
                            </TableCell>
                            <TableCell>
                               <Badge variant="outline" style={{ borderColor: stringToColor(ins.knowledge_type), color: stringToColor(ins.knowledge_type) }}>
                                  {ins.knowledge_type || "other"}
                               </Badge>
                            </TableCell>
                            <TableCell className="max-w-sm">
                               <div className="font-medium text-sm">{ins.name}</div>
                               <div className="text-xs text-muted-foreground line-clamp-2 mt-0.5">{ins.summary}</div>
                            </TableCell>
                            <TableCell>
                               <Badge variant={ins.status === "confirmed" ? "default" : "secondary"}>{ins.status}</Badge>
                            </TableCell>
                            <TableCell onClick={(e) => e.stopPropagation()}>
                               <div className="flex gap-1">
                                 {ins.status === "draft" && (
                                   <Button variant="ghost" size="icon" onClick={() => handleApproveIntelligence(ins.id)}>
                                     <Check className="w-4 h-4 text-green-500" />
                                   </Button>
                                 )}
                                 <Button variant="ghost" size="icon" onClick={() => setEditingIntelligence(ins)}>
                                   <Edit className="w-4 h-4" />
                                 </Button>
                               </div>
                            </TableCell>
                         </TableRow>
                       ))}
                    </TableBody>
                 </Table>
               </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: Knowledge */}
        <TabsContent value="knowledge" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Knowledge (Tier 3)</CardTitle>
                <CardDescription>Global system-wide rules extracted from intelligence</CardDescription>
              </div>
              <div className="flex items-center gap-2">
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
                <Button onClick={() => setShowNewLessonDialog(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  New Knowledge
                </Button>
              </div>
            </CardHeader>
            <CardContent>
               <ScrollArea className="h-[500px]">
                 <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Content</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                       {knowledge.length === 0 ? (
                          <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground py-8">No knowledge found.</TableCell></TableRow>
                       ) : knowledge.map(knowledge => (
                         <TableRow key={knowledge.id}>
                            <TableCell className="font-mono text-muted-foreground">#{knowledge.seq_id}</TableCell>
                            <TableCell>
                               <div className="flex items-center gap-2">
                                 <div className="w-3 h-3 rounded-full" style={{ backgroundColor: getLessonTypeColor(knowledge.type) }} />
                                 <Badge variant="outline">{knowledge.type}</Badge>
                               </div>
                            </TableCell>
                            <TableCell className="font-medium">{knowledge.name}</TableCell>
                            <TableCell className="max-w-[250px] truncate" title={knowledge.body}>{knowledge.body}</TableCell>
                            <TableCell>
                               <Badge variant={knowledge.status === "approved" ? "default" : "secondary"}>
                                 {knowledge.status}
                               </Badge>
                            </TableCell>
                            <TableCell>
                               <div className="flex gap-1">
                                 {knowledge.status === "draft" && (
                                   <Button variant="ghost" size="icon" onClick={() => handleApproveLesson(knowledge.id)}>
                                     <Check className="w-4 h-4 text-green-500" />
                                   </Button>
                                 )}
                                 <Button variant="ghost" size="icon" onClick={() => setEditingLesson(knowledge)}>
                                   <Edit className="w-4 h-4" />
                                 </Button>
                                 <Button variant="ghost" size="icon" onClick={() => handleDeleteLesson(knowledge.id)}>
                                   <Trash2 className="w-4 h-4 text-destructive" />
                                 </Button>
                               </div>
                            </TableCell>
                         </TableRow>
                       ))}
                    </TableBody>
                 </Table>
               </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Intelligence Inspector Dialog */}
      <Dialog open={!!editingIntelligence} onOpenChange={() => setEditingIntelligence(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>Intelligence Inspector</DialogTitle>
            <DialogDescription>Review and edit the intelligence report for this entity</DialogDescription>
          </DialogHeader>
          {editingIntelligence && (
            <ScrollArea className="flex-1 overflow-y-auto pr-4">
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Entity Type</Label>
                    <div className="font-medium">{editingIntelligence.primary_entity_type}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Entity ID</Label>
                    <div className="font-mono text-sm">{editingIntelligence.primary_entity_id}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Created</Label>
                    <div className="font-medium">{format(new Date(editingIntelligence.created_at), "MMM d, yyyy")}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Status</Label>
                    <Badge variant={editingIntelligence.status === "confirmed" ? "default" : "secondary"} className="mt-1">
                      {editingIntelligence.status}
                    </Badge>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Title</Label>
                    <Input
                      value={editingIntelligence.name || ""}
                      onChange={(e) => setEditingIntelligence({ ...editingIntelligence, name: e.target.value })}
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label>Signal Type</Label>
                    <Input
                      value={editingIntelligence.knowledge_type || ""}
                      onChange={(e) => setEditingIntelligence({ ...editingIntelligence, knowledge_type: e.target.value })}
                      className="mt-1 font-mono text-sm"
                      placeholder="e.g. risk, budget, objection"
                    />
                  </div>
                </div>

                <div>
                  <Label>Intelligence Report</Label>
                  <Textarea
                    value={editingIntelligence.content || ""}
                    onChange={(e) => setEditingIntelligence({ ...editingIntelligence, content: e.target.value })}
                    rows={7}
                    className="mt-1 text-sm"
                  />
                </div>

                <div>
                  <Label>Summary <span className="text-muted-foreground text-xs font-normal">(one-line actionable takeaway)</span></Label>
                  <Textarea
                    value={editingIntelligence.summary || ""}
                    onChange={(e) => setEditingIntelligence({ ...editingIntelligence, summary: e.target.value })}
                    rows={2}
                    className="mt-1 text-sm"
                  />
                </div>

                {editingIntelligence.source_memory_ids?.length > 0 && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Source Memories ({editingIntelligence.source_memory_ids.length})</Label>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {editingIntelligence.source_memory_ids.map((id, i) => (
                        <Badge key={i} variant="outline" className="font-mono text-xs">{id.slice(0, 8)}...</Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}
          <DialogFooter className="mt-4 sm:justify-between">
            <Button variant="destructive" onClick={handleDeleteIntelligence} disabled={!editingIntelligence}>
              <Trash2 className="w-4 h-4 mr-2" /> Delete
            </Button>
            <div className="flex gap-2">
              {editingIntelligence?.status === "draft" && (
                <Button variant="outline" onClick={() => { handleApproveIntelligence(editingIntelligence.id); setEditingIntelligence(null); }}>
                  <Check className="w-4 h-4 mr-2 text-green-500" /> Confirm
                </Button>
              )}
              <Button variant="outline" onClick={() => setEditingIntelligence(null)}>Cancel</Button>
              <Button onClick={handleUpdateIntelligence} disabled={!editingIntelligence}>Save Changes</Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Memory Inspector Dialog */}
      <Dialog open={!!editingMemory} onOpenChange={() => setEditingMemory(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>Memory Inspector</DialogTitle>
            <DialogDescription>View or edit aggregated memory properties</DialogDescription>
          </DialogHeader>

          {editingMemory && (
            <ScrollArea className="flex-1 overflow-y-auto pr-4">
              <div className="space-y-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs text-muted-foreground">Entity Type</Label>
                    <div className="font-medium">{editingMemory.primary_entity_type}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Entity ID</Label>
                    <div className="font-mono text-sm">{editingMemory.primary_entity_id}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Date Generated</Label>
                    <div className="font-medium">{editingMemory.date}</div>
                  </div>
                  <div>
                    <Label className="text-xs text-muted-foreground">Source Interactions</Label>
                    <div className="font-medium">{editingMemory.interaction_count} records</div>
                  </div>
                </div>
                
                <div>
                  <Label>Content Summary</Label>
                  <Textarea 
                    value={editingMemory.content_summary || ""} 
                    onChange={(e) => setEditingMemory({ ...editingMemory, content_summary: e.target.value })} 
                    rows={8} 
                    className="mt-1"
                  />
                </div>

                {editingMemory.intents?.length > 0 && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Intents Detected</Label>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {editingMemory.intents.map((intent, i) => (
                        <Badge key={i} variant="secondary">{intent}</Badge>
                      ))}
                    </div>
                  </div>
                )}
                {editingMemory.related_entities?.length > 0 && (
                  <div>
                    <Label className="text-xs text-muted-foreground">Related Entities</Label>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {editingMemory.related_entities.map((entity, i) => (
                        <Badge key={i} variant="outline">
                          <User className="w-3 h-3 mr-1" />
                          {typeof entity === "string" ? entity : entity.name || entity.entity_id}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </ScrollArea>
          )}

          <DialogFooter className="mt-4 sm:justify-between">
            <Button 
                variant="destructive" 
                onClick={handleDeleteMemory}
                disabled={!editingMemory}
            >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
            </Button>
            <div className="flex gap-2">
                <Button variant="outline" onClick={() => setEditingMemory(null)}>Cancel</Button>
                <Button onClick={handleUpdateMemory} disabled={!editingMemory}>
                    Save Changes
                </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Knowledge Dialog */}
      <Dialog open={showNewLessonDialog} onOpenChange={setShowNewLessonDialog}>
         <DialogContent>
           <DialogHeader>
             <DialogTitle>Create New Knowledge</DialogTitle>
             <DialogDescription>Add a curated knowledge to your knowledge base</DialogDescription>
           </DialogHeader>
           <div className="space-y-4 py-4">
             <div>
               <Label>Name</Label>
               <Input value={newLesson.name} onChange={(e) => setNewLesson({ ...newLesson, name: e.target.value })} placeholder="Knowledge title" />
             </div>
             <div>
               <Label>Type</Label>
               <Select value={newLesson.type} onValueChange={(v) => setNewLesson({ ...newLesson, type: v })}>
                 <SelectTrigger><SelectValue placeholder="Select type" /></SelectTrigger>
                 <SelectContent>
                   {lessonTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                 </SelectContent>
               </Select>
             </div>
             <div>
               <Label>Body</Label>
               <Textarea value={newLesson.body} onChange={(e) => setNewLesson({ ...newLesson, body: e.target.value })} placeholder="Knowledge content (Markdown supported)" rows={6} />
             </div>
             <div>
               <Label>Status</Label>
               <Select value={newLesson.status} onValueChange={(v) => setNewLesson({ ...newLesson, status: v })}>
                 <SelectTrigger><SelectValue /></SelectTrigger>
                 <SelectContent>
                   <SelectItem value="draft">Draft</SelectItem>
                   <SelectItem value="approved">Approved</SelectItem>
                 </SelectContent>
               </Select>
             </div>
           </div>
           <DialogFooter>
             <Button variant="outline" onClick={() => setShowNewLessonDialog(false)}>Cancel</Button>
             <Button onClick={handleCreateLesson}>Create Knowledge</Button>
           </DialogFooter>
         </DialogContent>
       </Dialog>

       {/* Edit Knowledge Dialog */}
       <Dialog open={!!editingLesson} onOpenChange={() => setEditingLesson(null)}>
         <DialogContent>
           <DialogHeader><DialogTitle>Edit Knowledge</DialogTitle></DialogHeader>
           {editingLesson && (
             <div className="space-y-4 py-4">
               <div>
                 <Label>Name</Label>
                 <Input value={editingLesson.name} onChange={(e) => setEditingLesson({ ...editingLesson, name: e.target.value })} />
               </div>
               <div>
                 <Label>Type</Label>
                 <Select value={editingLesson.type} onValueChange={(v) => setEditingLesson({ ...editingLesson, type: v })}>
                   <SelectTrigger><SelectValue /></SelectTrigger>
                   <SelectContent>
                     {lessonTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                   </SelectContent>
                 </Select>
               </div>
               <div>
                 <Label>Body</Label>
                 <Textarea value={editingLesson.body} onChange={(e) => setEditingLesson({ ...editingLesson, body: e.target.value })} rows={6} />
               </div>
               <div>
                 <Label>Status</Label>
                 <Select value={editingLesson.status} onValueChange={(v) => setEditingLesson({ ...editingLesson, status: v })}>
                   <SelectTrigger><SelectValue /></SelectTrigger>
                   <SelectContent>
                     <SelectItem value="draft">Draft</SelectItem>
                     <SelectItem value="approved">Approved</SelectItem>
                   </SelectContent>
                 </Select>
               </div>
             </div>
           )}
           <DialogFooter>
             <Button variant="outline" onClick={() => setEditingLesson(null)}>Cancel</Button>
             <Button onClick={handleUpdateLesson}>Update Knowledge</Button>
           </DialogFooter>
         </DialogContent>
       </Dialog>

       {/* Interaction Inspector Dialog */}
       <Dialog open={!!editingInteraction} onOpenChange={() => setEditingInteraction(null)}>
         <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
           <DialogHeader>
             <DialogTitle>Interaction Inspector</DialogTitle>
             <DialogDescription>
               {editingInteraction?.status === "pending" 
                 ? "Edit raw interaction properties before they are processed by the memory pipeline."
                 : "This interaction is locked because it has already been processed."}
             </DialogDescription>
           </DialogHeader>
           
           {editingInteraction && (
             <ScrollArea className="flex-1 pr-4">
               <div className="space-y-4 py-4">
                 <div className="grid grid-cols-2 gap-4">
                   <div>
                     <Label>Interaction Type</Label>
                     <Input 
                       value={editingInteraction.interaction_type} 
                       onChange={(e) => setEditingInteraction({ ...editingInteraction, interaction_type: e.target.value })}
                       disabled={editingInteraction.status !== "pending"}
                     />
                   </div>
                   <div>
                     <Label>Source</Label>
                     <Input 
                       value={editingInteraction.source} 
                       onChange={(e) => setEditingInteraction({ ...editingInteraction, source: e.target.value })}
                       disabled={editingInteraction.status !== "pending"}
                     />
                   </div>
                   <div>
                     <Label>Entity Type</Label>
                     <Select 
                       value={editingInteraction.primary_entity_type} 
                       onValueChange={(v) => setEditingInteraction({ ...editingInteraction, primary_entity_type: v })}
                       disabled={editingInteraction.status !== "pending"}
                     >
                       <SelectTrigger><SelectValue /></SelectTrigger>
                       <SelectContent>
                         {entityTypes.map(t => <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>)}
                       </SelectContent>
                     </Select>
                   </div>
                   <div>
                     <Label>Entity Sub-Type</Label>
                     <Input 
                       value={editingInteraction.primary_entity_subtype || ""} 
                       onChange={(e) => setEditingInteraction({ ...editingInteraction, primary_entity_subtype: e.target.value })}
                       disabled={editingInteraction.status !== "pending"}
                     />
                   </div>
                   <div className="col-span-2">
                     <Label>Entity ID</Label>
                     <Input 
                       value={editingInteraction.primary_entity_id} 
                       onChange={(e) => setEditingInteraction({ ...editingInteraction, primary_entity_id: e.target.value })}
                       disabled={editingInteraction.status !== "pending"}
                       className="font-mono text-sm"
                     />
                   </div>
                 </div>
                 
                 <div>
                   <Label>Interaction Blob</Label>
                   <Textarea 
                     value={editingInteraction.content} 
                     onChange={(e) => setEditingInteraction({ ...editingInteraction, content: e.target.value })} 
                     rows={10} 
                     disabled={editingInteraction.status !== "pending"}
                     className="font-mono text-sm"
                   />
                 </div>

                 {editingInteraction.processing_errors && Object.keys(editingInteraction.processing_errors).length > 0 && (
                   <div className="bg-red-950/20 border border-red-900/50 rounded-md p-3 mt-4">
                     <Label className="text-red-400 mb-2 block flex items-center"><AlertCircle className="w-4 h-4 mr-2" /> Captured Pipeline Errors</Label>
                     <pre className="text-xs text-red-300/80 font-mono overflow-x-auto">
                       {JSON.stringify(editingInteraction.processing_errors, null, 2)}
                     </pre>
                   </div>
                 )}
               </div>
             </ScrollArea>
           )}

           <DialogFooter className="mt-4 sm:justify-between">
             <Button 
               variant="destructive" 
               onClick={handleDeleteInteraction}
               disabled={!editingInteraction}
             >
               <Trash2 className="w-4 h-4 mr-2" />
               Delete
             </Button>
             <div className="flex gap-2">
               <Button variant="outline" onClick={() => setEditingInteraction(null)}>Cancel</Button>
               <Button 
                 onClick={handleUpdateInteraction} 
                 disabled={!editingInteraction || editingInteraction.status !== "pending"}
               >
                 Save Changes
               </Button>
             </div>
           </DialogFooter>
         </DialogContent>
       </Dialog>
    </div>
  );
}
