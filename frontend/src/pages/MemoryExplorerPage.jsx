import { useState, useEffect, useCallback } from "react";
import { useBulkSelection } from "@/hooks/useBulkSelection";
import { useColumnConfig } from "@/hooks/useColumnConfig";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { formatISO, subDays } from "date-fns";
import {
  getInteractionsAdmin,
  getMemoriesAdmin,
  getInsightsAdmin,
  updateInsightAdmin,
  deleteInsightAdmin,
  getLessonsAdmin,
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
  getEntityTypeConfig,
  bulkDeleteIntelligenceAdmin,
  bulkApproveIntelligenceAdmin,
  reprocessIntelligence,
  bulkDeleteKnowledgeAdmin,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  User,
  Calendar,
  Lightbulb,
  GraduationCap,
  RefreshCw,
  Settings2,
  Eye,
  EyeOff,
  ChevronUp,
  ChevronDown
} from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

// Extracted components
import InteractionsTab from "@/components/memory/InteractionsTab";
import MemoriesTab from "@/components/memory/MemoriesTab";
import IntelligenceTab from "@/components/memory/IntelligenceTab";
import KnowledgeTab from "@/components/memory/KnowledgeTab";
import InteractionInspector from "@/components/memory/InteractionInspector";
import MemoryInspector from "@/components/memory/MemoryInspector";
import IntelligenceInspector from "@/components/memory/IntelligenceInspector";
import { NewKnowledgeDialog, EditKnowledgeDialog } from "@/components/memory/KnowledgeDialogs";
import FilterBar from "@/components/memory/FilterBar";

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

  // Inspector state
  const [editingInteraction, setEditingInteraction] = useState(null);
  const [editingMemory, setEditingMemory] = useState(null);
  const [editingIntelligence, setEditingIntelligence] = useState(null);

  // Bulk Operations
  const {
    selectedIds: selectedInteractionIds,
    toggleAll: toggleSelectAllInteractions,
    toggleOne: toggleInteraction,
    clear: clearInteractionSelection,
  } = useBulkSelection(interactions);
  const {
    selectedIds: selectedMemoryIds,
    toggleAll: toggleSelectAllMemories,
    toggleOne: toggleMemory,
    clear: clearMemorySelection,
  } = useBulkSelection(memories);
  const {
    selectedIds: selectedIntelligenceIds,
    toggleAll: toggleSelectAllIntelligence,
    toggleOne: toggleIntelligenceItem,
    clear: clearIntelligenceSelection,
  } = useBulkSelection(intelligence);
  const {
    selectedIds: selectedKnowledgeIds,
    toggleAll: toggleSelectAllKnowledge,
    toggleOne: toggleKnowledgeItem,
    clear: clearKnowledgeSelection,
  } = useBulkSelection(knowledge);

  // ─── Generic Column Config System ─────────────────────────────────────
  const COLUMN_DEFS = {
    interactions: [
      { key: "select", label: "", fixed: true },
      { key: "seq_id", label: "ID" },
      { key: "timestamp", label: "Time" },
      { key: "interaction_type", label: "Interaction Type" },
      { key: "entity_type", label: "Entity Type" },
      { key: "entity_subtype", label: "Sub-Type" },
      { key: "entity_id", label: "Entity" },
      { key: "content", label: "Content" },
      { key: "agent", label: "Agent" },
      { key: "service_status", label: "Service Status" },
      { key: "status", label: "Memorization" },
      { key: "actions", label: "Actions", fixed: true },
    ],
    memories: [
      { key: "select", label: "", fixed: true },
      { key: "seq_id", label: "ID" },
      { key: "date", label: "Date" },
      { key: "entity_type", label: "Entity Type" },
      { key: "entity_subtype", label: "Entity Subtype" },
      { key: "entity_id", label: "Entity" },
      { key: "interaction_count", label: "Interactions" },
      { key: "service_status", label: "Service Status" },
      { key: "compacted", label: "Compacted" },
    ],
    intelligence: [
      { key: "select", label: "", fixed: true },
      { key: "seq_id", label: "ID" },
      { key: "created_at", label: "Created" },
      { key: "entity", label: "Entity" },
      { key: "signal", label: "Signal" },
      { key: "report", label: "Intelligence Report" },
      { key: "status", label: "Status" },
      { key: "actions", label: "Actions", fixed: true },
    ],
    knowledge: [
      { key: "select", label: "", fixed: true },
      { key: "seq_id", label: "ID" },
      { key: "type", label: "Type" },
      { key: "name", label: "Name" },
      { key: "content", label: "Content" },
      { key: "status", label: "Status" },
      { key: "actions", label: "Actions", fixed: true },
    ],
  };

  const { colCfg, setColCfg, toggleCol, moveCol, visCols } = useColumnConfig(COLUMN_DEFS);

  const renderColumnToggle = (tableKey) => (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" title="Toggle columns">
          <Settings2 className="w-4 h-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-0">
        <div className="px-3 py-2 border-b border-border/50">
          <p className="text-sm font-medium">Toggle Columns</p>
          <p className="text-[10px] text-muted-foreground">Show/hide and reorder table columns</p>
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          {colCfg[tableKey].filter(c => !c.fixed).map(col => (
            <div key={col.key} className="flex items-center gap-2 px-3 py-1.5 hover:bg-muted/50">
              <button onClick={() => toggleCol(tableKey, col.key)}
                className={`p-0.5 rounded transition-colors ${col.visible ? 'text-primary' : 'text-muted-foreground/40'}`}>
                {col.visible ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
              </button>
              <span className={`text-xs flex-1 ${col.visible ? '' : 'text-muted-foreground/50'}`}>{col.label}</span>
              <div className="flex gap-0.5">
                <button onClick={() => moveCol(tableKey, col.key, -1)} className="p-0.5 text-muted-foreground hover:text-foreground rounded" title="Move up">
                  <ChevronUp className="w-3 h-3" />
                </button>
                <button onClick={() => moveCol(tableKey, col.key, 1)} className="p-0.5 text-muted-foreground hover:text-foreground rounded" title="Move down">
                  <ChevronDown className="w-3 h-3" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );

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

      const dynamicColKeys = new Set();
      for (const et of entityRes.data) {
        try {
          const cfgRes = await getEntityTypeConfig(et.name);
          const fieldMap = cfgRes.data?.metadata_field_map || {};
          (fieldMap.display_columns || []).forEach(c => dynamicColKeys.add(c));
        } catch { /* config may not exist */ }
      }

      if (dynamicColKeys.size > 0) {
        setColCfg(prev => {
          const updated = { ...prev };
          for (const tableKey of ["interactions", "memories", "intelligence"]) {
            const existingKeys = new Set(updated[tableKey].map(c => c.key));
            const newDynamic = [...dynamicColKeys]
              .filter(k => !existingKeys.has(`dyn_${k}`))
              .map(k => ({ key: `dyn_${k}`, label: k.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), visible: true, dynamic: true }));
            if (newDynamic.length > 0) {
              const actionsIdx = updated[tableKey].findIndex(c => c.key === 'actions');
              const arr = [...updated[tableKey]];
              arr.splice(actionsIdx >= 0 ? actionsIdx : arr.length, 0, ...newDynamic);
              updated[tableKey] = arr;
              localStorage.setItem(`me-cols-${tableKey}`, JSON.stringify(arr));
            }
          }
          return updated;
        });
      }
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

  // ─── Knowledge Handlers ─────────────────────────────────────
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

  const getLessonTypeColor = (typeName) => {
    const type = lessonTypes.find(t => t.name === typeName);
    return type?.color || "#6B7280";
  };

  // ─── Interaction Handlers ─────────────────────────────────────
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

  // ─── Memory Handlers ─────────────────────────────────────
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

  // ─── Intelligence Handlers ─────────────────────────────────────
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

  // ─── Bulk Action Handlers ─────────────────────────────────────
  const handleBulkDelete = async () => {
    if (!window.confirm(`Delete ${selectedInteractionIds.length} interactions? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteInteractionsAdmin({ interaction_ids: selectedInteractionIds });
      toast.success(`Deleted ${res.data.deleted} interactions`);
      clearInteractionSelection();
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
      clearInteractionSelection();
      loadInteractions();
    } catch (error) {
      toast.error("Failed to queue interactions");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkDeleteMemories = async () => {
    if (!window.confirm(`Delete ${selectedMemoryIds.length} memories? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteMemoriesAdmin({ memory_ids: selectedMemoryIds });
      toast.success(`Deleted ${res.data.deleted} memories`);
      clearMemorySelection();
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
      clearMemorySelection();
      loadMemories();
      loadInteractions();
    } catch (error) {
      toast.error("Failed to queue memories");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkDeleteIntelligence = async () => {
    if (!window.confirm(`Delete ${selectedIntelligenceIds.length} intelligence records? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteIntelligenceAdmin({ intelligence_ids: selectedIntelligenceIds });
      toast.success(`Deleted ${res.data.deleted} intelligence records`);
      clearIntelligenceSelection();
      loadInsights();
    } catch (error) {
      toast.error("Failed to delete intelligence");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkReprocessIntelligence = async () => {
    setProcessingBulk(true);
    try {
      const res = await reprocessIntelligence(selectedIntelligenceIds);
      toast.success(res.data.message);
      clearIntelligenceSelection();
    } catch (error) {
      toast.error("Failed to queue reprocess");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkApproveIntelligence = async () => {
    setProcessingBulk(true);
    try {
      const res = await bulkApproveIntelligenceAdmin({ intelligence_ids: selectedIntelligenceIds });
      toast.success(`Approved ${res.data.approved} intelligence records`);
      clearIntelligenceSelection();
      loadInsights();
    } catch (error) {
      toast.error("Failed to approve intelligence");
    } finally {
      setProcessingBulk(false);
    }
  };

  const handleBulkDeleteKnowledge = async () => {
    if (!window.confirm(`Delete ${selectedKnowledgeIds.length} knowledge records? This cannot be reversed.`)) return;
    setProcessingBulk(true);
    try {
      const res = await bulkDeleteKnowledgeAdmin({ knowledge_ids: selectedKnowledgeIds });
      toast.success(`Deleted ${res.data.deleted} knowledge records`);
      clearKnowledgeSelection();
      loadLessons();
    } catch (error) {
      toast.error("Failed to delete knowledge");
    } finally {
      setProcessingBulk(false);
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
      <FilterBar
        appliedFilter={appliedFilter}
        setAppliedFilter={setAppliedFilter}
        entityIdInput={entityIdInput}
        setEntityIdInput={setEntityIdInput}
        filterOptions={filterOptions}
      />

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

        <TabsContent value="interactions" className="space-y-4">
          <InteractionsTab
            interactions={interactions}
            selectedIds={selectedInteractionIds}
            toggleAll={toggleSelectAllInteractions}
            toggleOne={toggleInteraction}
            onEdit={setEditingInteraction}
            onBulkDelete={handleBulkDelete}
            onBulkReprocess={handleBulkReprocess}
            loading={loading}
            visCols={visCols}
            renderColumnToggle={renderColumnToggle}
            onLoad={loadInteractions}
            processingBulk={processingBulk}
          />
        </TabsContent>

        <TabsContent value="memories" className="space-y-4">
          <MemoriesTab
            memories={memories}
            selectedIds={selectedMemoryIds}
            toggleAll={toggleSelectAllMemories}
            toggleOne={toggleMemory}
            onEdit={setEditingMemory}
            onBulkDelete={handleBulkDeleteMemories}
            onBulkReprocess={handleBulkReprocessMemories}
            loading={loading}
            visCols={visCols}
            renderColumnToggle={renderColumnToggle}
            onLoad={loadMemories}
            processingBulk={processingBulk}
          />
        </TabsContent>

        <TabsContent value="intelligence" className="space-y-4">
          <IntelligenceTab
            intelligence={intelligence}
            selectedIds={selectedIntelligenceIds}
            toggleAll={toggleSelectAllIntelligence}
            toggleOne={toggleIntelligenceItem}
            onEdit={setEditingIntelligence}
            onApprove={handleApproveIntelligence}
            onBulkDelete={handleBulkDeleteIntelligence}
            onBulkApprove={handleBulkApproveIntelligence}
            onBulkReprocess={handleBulkReprocessIntelligence}
            loading={loading}
            visCols={visCols}
            renderColumnToggle={renderColumnToggle}
            onLoad={loadInsights}
            processingBulk={processingBulk}
          />
        </TabsContent>

        <TabsContent value="knowledge" className="space-y-4">
          <KnowledgeTab
            knowledge={knowledge}
            selectedIds={selectedKnowledgeIds}
            toggleAll={toggleSelectAllKnowledge}
            toggleOne={toggleKnowledgeItem}
            onEdit={setEditingLesson}
            onApprove={handleApproveLesson}
            onDelete={handleDeleteLesson}
            onBulkDelete={handleBulkDeleteKnowledge}
            lessonStatusFilter={lessonStatusFilter}
            setLessonStatusFilter={setLessonStatusFilter}
            onShowNewDialog={() => setShowNewLessonDialog(true)}
            lessonTypes={lessonTypes}
            getLessonTypeColor={getLessonTypeColor}
            loading={loading}
            visCols={visCols}
            renderColumnToggle={renderColumnToggle}
          />
        </TabsContent>
      </Tabs>

      {/* Inspector Dialogs */}
      <InteractionInspector
        editingInteraction={editingInteraction}
        setEditingInteraction={setEditingInteraction}
        entityTypes={entityTypes}
        onUpdate={handleUpdateInteraction}
        onDelete={handleDeleteInteraction}
      />
      <MemoryInspector
        editingMemory={editingMemory}
        setEditingMemory={setEditingMemory}
        onUpdate={handleUpdateMemory}
        onDelete={handleDeleteMemory}
      />
      <IntelligenceInspector
        editingIntelligence={editingIntelligence}
        setEditingIntelligence={setEditingIntelligence}
        onUpdate={handleUpdateIntelligence}
        onApprove={handleApproveIntelligence}
        onDelete={handleDeleteIntelligence}
      />
      <NewKnowledgeDialog
        open={showNewLessonDialog}
        onOpenChange={setShowNewLessonDialog}
        newLesson={newLesson}
        setNewLesson={setNewLesson}
        lessonTypes={lessonTypes}
        onCreate={handleCreateLesson}
      />
      <EditKnowledgeDialog
        editingLesson={editingLesson}
        setEditingLesson={setEditingLesson}
        lessonTypes={lessonTypes}
        onUpdate={handleUpdateLesson}
      />
    </div>
  );
}
