import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { format } from "date-fns";
import api from "@/lib/api";
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
import {
  Search,
  Calendar,
  User,
  Building2,
  FolderKanban,
  MessageSquare,
  Mail,
  Phone,
  FileText,
  Video,
  StickyNote,
  GraduationCap,
  Clock,
  ChevronRight,
  Filter,
  X,
  Check,
  Edit,
  Trash2,
  Plus,
  RefreshCw,
} from "lucide-react";

const CHANNEL_ICONS = {
  email: Mail,
  call: Phone,
  meeting: Video,
  chat: MessageSquare,
  document: FileText,
  note: StickyNote,
};

const ENTITY_ICONS = {
  Contact: User,
  Organization: Building2,
  Program: FolderKanban,
};

export default function MemoryExplorerPage() {
  const [activeTab, setActiveTab] = useState("search");
  const [loading, setLoading] = useState(false);
  
  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchFilters, setSearchFilters] = useState({
    channel: "",
    entity_type: "",
    date_from: "",
    date_to: "",
  });
  
  // Timeline state
  const [entityTypes, setEntityTypes] = useState([]);
  const [selectedEntityType, setSelectedEntityType] = useState("");
  const [entityId, setEntityId] = useState("");
  const [timeline, setTimeline] = useState([]);
  
  // Daily log state
  const [selectedDate, setSelectedDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [dailyMemories, setDailyMemories] = useState([]);
  
  // Lessons state
  const [lessons, setLessons] = useState([]);
  const [lessonTypes, setLessonTypes] = useState([]);
  const [lessonFilter, setLessonFilter] = useState("all");
  const [editingLesson, setEditingLesson] = useState(null);
  const [newLesson, setNewLesson] = useState({ name: "", type: "", body: "", status: "draft" });
  const [showNewLessonDialog, setShowNewLessonDialog] = useState(false);
  
  // Memory detail state
  const [selectedMemory, setSelectedMemory] = useState(null);
  
  // Channel types
  const [channelTypes, setChannelTypes] = useState([]);

  useEffect(() => {
    loadInitialData();
  }, []);

  const loadInitialData = async () => {
    try {
      const [entityRes, lessonTypeRes, channelRes] = await Promise.all([
        api.get("/memory/config/entity-types"),
        api.get("/memory/config/lesson-types"),
        api.get("/memory/config/channel-types"),
      ]);
      setEntityTypes(entityRes.data);
      setLessonTypes(lessonTypeRes.data);
      setChannelTypes(channelRes.data);
    } catch (error) {
      console.error("Failed to load config data:", error);
    }
  };

  // Search memories
  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    
    setLoading(true);
    try {
      const filters = {};
      if (searchFilters.channel) filters.channel = searchFilters.channel;
      if (searchFilters.entity_type) filters.entity_type = searchFilters.entity_type;
      if (searchFilters.date_from) filters.date_from = searchFilters.date_from;
      if (searchFilters.date_to) filters.date_to = searchFilters.date_to;
      
      const res = await api.post("/memory/search", {
        query: searchQuery,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
        limit: 50,
      });
      setSearchResults(res.data.results || []);
    } catch (error) {
      toast.error("Search failed");
    } finally {
      setLoading(false);
    }
  };

  // Load timeline for entity
  const loadTimeline = async () => {
    if (!selectedEntityType || !entityId) return;
    
    setLoading(true);
    try {
      const res = await api.get(`/memory/timeline/${selectedEntityType}/${entityId}`);
      setTimeline(res.data || []);
    } catch (error) {
      toast.error("Failed to load timeline");
      setTimeline([]);
    } finally {
      setLoading(false);
    }
  };

  // Load daily memories
  const loadDailyMemories = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/memory/daily/${selectedDate}`);
      setDailyMemories(res.data || []);
    } catch (error) {
      console.error("Failed to load daily memories:", error);
      setDailyMemories([]);
    } finally {
      setLoading(false);
    }
  }, [selectedDate]);

  useEffect(() => {
    if (activeTab === "daily") {
      loadDailyMemories();
    }
  }, [activeTab, selectedDate, loadDailyMemories]);

  // Load lessons
  const loadLessons = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (lessonFilter !== "all") params.status = lessonFilter;
      const res = await api.get("/memory/lessons", { params });
      setLessons(res.data || []);
    } catch (error) {
      console.error("Failed to load lessons:", error);
      setLessons([]);
    } finally {
      setLoading(false);
    }
  }, [lessonFilter]);

  useEffect(() => {
    if (activeTab === "lessons") {
      loadLessons();
    }
  }, [activeTab, lessonFilter, loadLessons]);

  // Create lesson
  const handleCreateLesson = async () => {
    if (!newLesson.name || !newLesson.type || !newLesson.body) {
      toast.error("Please fill all fields");
      return;
    }
    
    try {
      await api.post("/memory/lessons", newLesson);
      toast.success("Lesson created");
      setShowNewLessonDialog(false);
      setNewLesson({ name: "", type: "", body: "", status: "draft" });
      loadLessons();
    } catch (error) {
      toast.error("Failed to create lesson");
    }
  };

  // Update lesson
  const handleUpdateLesson = async () => {
    if (!editingLesson) return;
    
    try {
      await api.put(`/memory/lessons/${editingLesson.id}`, {
        name: editingLesson.name,
        type: editingLesson.type,
        body: editingLesson.body,
        status: editingLesson.status,
      });
      toast.success("Lesson updated");
      setEditingLesson(null);
      loadLessons();
    } catch (error) {
      toast.error("Failed to update lesson");
    }
  };

  // Approve lesson
  const handleApproveLesson = async (lessonId) => {
    try {
      await api.put(`/memory/lessons/${lessonId}`, { status: "approved" });
      toast.success("Lesson approved");
      loadLessons();
    } catch (error) {
      toast.error("Failed to approve lesson");
    }
  };

  // Delete lesson
  const handleDeleteLesson = async (lessonId) => {
    if (!window.confirm("Delete this lesson?")) return;
    
    try {
      await api.delete(`/memory/lessons/${lessonId}`);
      toast.success("Lesson deleted");
      loadLessons();
    } catch (error) {
      toast.error("Failed to delete lesson");
    }
  };

  // Load memory detail
  const loadMemoryDetail = async (memoryId) => {
    try {
      const res = await api.get(`/memory/memories/${memoryId}`);
      setSelectedMemory(res.data);
    } catch (error) {
      toast.error("Failed to load memory details");
    }
  };

  const clearFilters = () => {
    setSearchFilters({ channel: "", entity_type: "", date_from: "", date_to: "" });
  };

  const getLessonTypeColor = (typeName) => {
    const type = lessonTypes.find(t => t.name === typeName);
    return type?.color || "#6B7280";
  };

  return (
    <div className="space-y-6" data-testid="memory-explorer-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory Explorer</h1>
          <p className="text-muted-foreground">Search, browse, and curate your agent memories</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-grid">
          <TabsTrigger value="search" className="gap-2" data-testid="tab-search">
            <Search className="w-4 h-4" /> Search
          </TabsTrigger>
          <TabsTrigger value="timeline" className="gap-2" data-testid="tab-timeline">
            <User className="w-4 h-4" /> Timeline
          </TabsTrigger>
          <TabsTrigger value="daily" className="gap-2" data-testid="tab-daily">
            <Calendar className="w-4 h-4" /> Daily Log
          </TabsTrigger>
          <TabsTrigger value="lessons" className="gap-2" data-testid="tab-lessons">
            <GraduationCap className="w-4 h-4" /> Lessons
          </TabsTrigger>
        </TabsList>

        {/* Search Tab */}
        <TabsContent value="search" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Semantic Search</CardTitle>
              <CardDescription>Search through all memories using natural language</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="Search memories..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="flex-1"
                  data-testid="search-input"
                />
                <Button onClick={handleSearch} disabled={loading} data-testid="search-button">
                  <Search className="w-4 h-4 mr-2" />
                  Search
                </Button>
              </div>
              
              {/* Filters */}
              <div className="flex flex-wrap gap-3 items-end">
                <div className="space-y-1">
                  <Label className="text-xs">Channel</Label>
                  <Select value={searchFilters.channel || "all"} onValueChange={(v) => setSearchFilters({...searchFilters, channel: v === "all" ? "" : v})}>
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="Any" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any</SelectItem>
                      {channelTypes.map(c => (
                        <SelectItem key={c.id} value={c.name}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Entity Type</Label>
                  <Select value={searchFilters.entity_type || "all"} onValueChange={(v) => setSearchFilters({...searchFilters, entity_type: v === "all" ? "" : v})}>
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="Any" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any</SelectItem>
                      {entityTypes.map(e => (
                        <SelectItem key={e.id} value={e.name}>{e.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">From</Label>
                  <Input type="date" value={searchFilters.date_from} onChange={(e) => setSearchFilters({...searchFilters, date_from: e.target.value})} className="w-36" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">To</Label>
                  <Input type="date" value={searchFilters.date_to} onChange={(e) => setSearchFilters({...searchFilters, date_to: e.target.value})} className="w-36" />
                </div>
                {(searchFilters.channel || searchFilters.entity_type || searchFilters.date_from || searchFilters.date_to) && (
                  <Button variant="ghost" size="sm" onClick={clearFilters}>
                    <X className="w-4 h-4 mr-1" /> Clear
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Search Results */}
          {searchResults.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Results ({searchResults.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[500px]">
                  <div className="space-y-3">
                    {searchResults.map((result) => {
                      const ChannelIcon = CHANNEL_ICONS[result.channel] || MessageSquare;
                      return (
                        <div
                          key={result.id}
                          className="p-4 border rounded-lg hover:bg-accent/50 cursor-pointer transition-colors"
                          onClick={() => loadMemoryDetail(result.memory_id)}
                          data-testid={`search-result-${result.id}`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2">
                              <ChannelIcon className="w-4 h-4 text-muted-foreground" />
                              <Badge variant="outline">{result.channel}</Badge>
                              <span className="text-sm text-muted-foreground">
                                {format(new Date(result.timestamp), "MMM d, yyyy h:mm a")}
                              </span>
                            </div>
                            <Badge variant="secondary">{(result.score * 100).toFixed(0)}% match</Badge>
                          </div>
                          <p className="mt-2 text-sm line-clamp-3">{result.text}</p>
                          {result.entities?.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {result.entities.map((entity, i) => {
                                const EntityIcon = ENTITY_ICONS[entity.type] || User;
                                return (
                                  <Badge key={i} variant="outline" className="text-xs">
                                    <EntityIcon className="w-3 h-3 mr-1" />
                                    {entity.name}
                                  </Badge>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Timeline Tab */}
        <TabsContent value="timeline" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Entity Timeline</CardTitle>
              <CardDescription>View interaction history for a specific entity</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-3">
                <div className="space-y-1 flex-1">
                  <Label>Entity Type</Label>
                  <Select value={selectedEntityType} onValueChange={setSelectedEntityType}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select type" />
                    </SelectTrigger>
                    <SelectContent>
                      {entityTypes.map(e => (
                        <SelectItem key={e.id} value={e.name}>{e.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 flex-1">
                  <Label>Entity ID / Name</Label>
                  <Input
                    placeholder="Enter entity ID or name"
                    value={entityId}
                    onChange={(e) => setEntityId(e.target.value)}
                  />
                </div>
                <div className="flex items-end">
                  <Button onClick={loadTimeline} disabled={loading || !selectedEntityType || !entityId}>
                    Load Timeline
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {timeline.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Timeline ({timeline.length} interactions)</CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[500px]">
                  <div className="relative border-l-2 border-muted ml-4 space-y-6">
                    {timeline.map((entry, i) => {
                      const ChannelIcon = CHANNEL_ICONS[entry.channel] || MessageSquare;
                      return (
                        <div key={entry.id} className="relative pl-6">
                          <div className="absolute -left-2 top-1 w-4 h-4 rounded-full bg-primary" />
                          <div className="p-4 border rounded-lg">
                            <div className="flex items-center gap-2 mb-2">
                              <ChannelIcon className="w-4 h-4" />
                              <Badge variant="outline">{entry.channel}</Badge>
                              <span className="text-sm text-muted-foreground">
                                {format(new Date(entry.timestamp), "MMM d, yyyy h:mm a")}
                              </span>
                            </div>
                            <p className="text-sm">{entry.summary_text || entry.raw_text?.slice(0, 200)}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Daily Log Tab */}
        <TabsContent value="daily" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Daily Log</CardTitle>
                <CardDescription>Browse memories by date</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  type="date"
                  value={selectedDate}
                  onChange={(e) => setSelectedDate(e.target.value)}
                  className="w-40"
                />
                <Button variant="outline" size="icon" onClick={loadDailyMemories}>
                  <RefreshCw className="w-4 h-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {dailyMemories.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Calendar className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No memories for {format(new Date(selectedDate), "MMMM d, yyyy")}</p>
                </div>
              ) : (
                <ScrollArea className="h-[500px]">
                  <div className="space-y-3">
                    {dailyMemories.map((memory) => {
                      const ChannelIcon = CHANNEL_ICONS[memory.channel] || MessageSquare;
                      return (
                        <div
                          key={memory.id}
                          className="p-4 border rounded-lg hover:bg-accent/50 cursor-pointer"
                          onClick={() => loadMemoryDetail(memory.id)}
                        >
                          <div className="flex items-center gap-2 mb-2">
                            <ChannelIcon className="w-4 h-4" />
                            <Badge variant="outline">{memory.channel}</Badge>
                            <span className="text-sm text-muted-foreground">
                              {format(new Date(memory.timestamp), "h:mm a")}
                            </span>
                            {memory.has_documents && (
                              <Badge variant="secondary">
                                <FileText className="w-3 h-3 mr-1" />
                                Attachments
                              </Badge>
                            )}
                          </div>
                          <p className="text-sm line-clamp-2">{memory.summary_text || memory.raw_text?.slice(0, 150)}</p>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Lessons Tab */}
        <TabsContent value="lessons" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Curated Lessons</CardTitle>
                <CardDescription>Knowledge extracted from interactions</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Select value={lessonFilter} onValueChange={setLessonFilter}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="draft">Drafts</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                  </SelectContent>
                </Select>
                <Button onClick={() => setShowNewLessonDialog(true)} data-testid="new-lesson-button">
                  <Plus className="w-4 h-4 mr-2" />
                  New Lesson
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {lessons.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <GraduationCap className="w-12 h-12 mx-auto mb-4 opacity-50" />
                  <p>No lessons yet. Create one or let the system extract them automatically.</p>
                </div>
              ) : (
                <ScrollArea className="h-[500px]">
                  <div className="space-y-3">
                    {lessons.map((lesson) => (
                      <div key={lesson.id} className="p-4 border rounded-lg">
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-3 h-3 rounded-full"
                              style={{ backgroundColor: getLessonTypeColor(lesson.type) }}
                            />
                            <Badge variant="outline">{lesson.type}</Badge>
                            <Badge variant={lesson.status === "approved" ? "default" : "secondary"}>
                              {lesson.status}
                            </Badge>
                          </div>
                          <div className="flex gap-1">
                            {lesson.status === "draft" && (
                              <Button variant="ghost" size="icon" onClick={() => handleApproveLesson(lesson.id)}>
                                <Check className="w-4 h-4 text-green-500" />
                              </Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => setEditingLesson(lesson)}>
                              <Edit className="w-4 h-4" />
                            </Button>
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteLesson(lesson.id)}>
                              <Trash2 className="w-4 h-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                        <h3 className="font-semibold mt-2">{lesson.name}</h3>
                        <p className="text-sm text-muted-foreground mt-1 line-clamp-3">{lesson.body}</p>
                        <p className="text-xs text-muted-foreground mt-2">
                          Created {format(new Date(lesson.created_at), "MMM d, yyyy")}
                        </p>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Memory Detail Dialog */}
      <Dialog open={!!selectedMemory} onOpenChange={() => setSelectedMemory(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Memory Details</DialogTitle>
          </DialogHeader>
          {selectedMemory && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{selectedMemory.channel}</Badge>
                <span className="text-sm text-muted-foreground">
                  {format(new Date(selectedMemory.timestamp), "MMMM d, yyyy h:mm a")}
                </span>
              </div>
              
              {selectedMemory.summary_text && (
                <div>
                  <Label className="text-xs text-muted-foreground">Summary</Label>
                  <p className="mt-1 p-3 bg-muted rounded-lg text-sm">{selectedMemory.summary_text}</p>
                </div>
              )}
              
              <div>
                <Label className="text-xs text-muted-foreground">Full Text</Label>
                <ScrollArea className="h-48 mt-1 p-3 bg-muted rounded-lg">
                  <p className="text-sm whitespace-pre-wrap">{selectedMemory.raw_text}</p>
                </ScrollArea>
              </div>
              
              {selectedMemory.entities?.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Related Entities</Label>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {selectedMemory.entities.map((entity, i) => {
                      const EntityIcon = ENTITY_ICONS[entity.type] || User;
                      return (
                        <Badge key={i} variant="secondary">
                          <EntityIcon className="w-3 h-3 mr-1" />
                          {entity.name}
                          <span className="ml-1 text-xs opacity-70">({entity.role})</span>
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              )}
              
              {selectedMemory.documents?.length > 0 && (
                <div>
                  <Label className="text-xs text-muted-foreground">Attachments</Label>
                  <div className="space-y-2 mt-1">
                    {selectedMemory.documents.map((doc) => (
                      <div key={doc.id} className="flex items-center gap-2 p-2 bg-muted rounded">
                        <FileText className="w-4 h-4" />
                        <span className="text-sm">{doc.filename}</span>
                        <span className="text-xs text-muted-foreground">({(doc.file_size / 1024).toFixed(1)} KB)</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* New Lesson Dialog */}
      <Dialog open={showNewLessonDialog} onOpenChange={setShowNewLessonDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create New Lesson</DialogTitle>
            <DialogDescription>Add a curated lesson to your knowledge base</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label>Name</Label>
              <Input
                value={newLesson.name}
                onChange={(e) => setNewLesson({...newLesson, name: e.target.value})}
                placeholder="Lesson title"
              />
            </div>
            <div>
              <Label>Type</Label>
              <Select value={newLesson.type} onValueChange={(v) => setNewLesson({...newLesson, type: v})}>
                <SelectTrigger>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {lessonTypes.map(t => (
                    <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Body</Label>
              <Textarea
                value={newLesson.body}
                onChange={(e) => setNewLesson({...newLesson, body: e.target.value})}
                placeholder="Lesson content (Markdown supported)"
                rows={6}
              />
            </div>
            <div>
              <Label>Status</Label>
              <Select value={newLesson.status} onValueChange={(v) => setNewLesson({...newLesson, status: v})}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowNewLessonDialog(false)}>Cancel</Button>
            <Button onClick={handleCreateLesson}>Create Lesson</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Lesson Dialog */}
      <Dialog open={!!editingLesson} onOpenChange={() => setEditingLesson(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Lesson</DialogTitle>
          </DialogHeader>
          {editingLesson && (
            <div className="space-y-4 py-4">
              <div>
                <Label>Name</Label>
                <Input
                  value={editingLesson.name}
                  onChange={(e) => setEditingLesson({...editingLesson, name: e.target.value})}
                />
              </div>
              <div>
                <Label>Type</Label>
                <Select value={editingLesson.type} onValueChange={(v) => setEditingLesson({...editingLesson, type: v})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {lessonTypes.map(t => (
                      <SelectItem key={t.id} value={t.name}>{t.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Body</Label>
                <Textarea
                  value={editingLesson.body}
                  onChange={(e) => setEditingLesson({...editingLesson, body: e.target.value})}
                  rows={6}
                />
              </div>
              <div>
                <Label>Status</Label>
                <Select value={editingLesson.status} onValueChange={(v) => setEditingLesson({...editingLesson, status: v})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
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
            <Button onClick={handleUpdateLesson}>Save Changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
