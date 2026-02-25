import { useState, useEffect } from "react";
import { toast } from "sonner";
import {
  getLLMConfigs,
  updateLLMConfig,
  getEntityTypes,
  createEntityType,
  deleteEntityType,
  getEntitySubtypes,
  createEntitySubtype,
  deleteEntitySubtype,
  getLessonTypes,
  createLessonType,
  deleteLessonType,
  getChannelTypes,
  createChannelType,
  deleteChannelType,
  getAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  getMemorySettings,
  updateMemorySettings,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  Brain,
  Settings2,
  Key,
  Users,
  Layers,
  MessageSquare,
  GraduationCap,
  Plus,
  Trash2,
  Eye,
  EyeOff,
  Copy,
  CheckCircle2,
  AlertCircle,
  Cpu,
} from "lucide-react";

const TASK_TYPE_LABELS = {
  summarization: { label: "Summarization", icon: Brain, color: "bg-blue-500" },
  embedding: { label: "Embeddings", icon: Layers, color: "bg-green-500" },
  vision: { label: "Vision/Doc Parsing", icon: Eye, color: "bg-purple-500" },
  entity_extraction: { label: "Entity Extraction (NER)", icon: Users, color: "bg-amber-500" },
  pii_scrubbing: { label: "PII Scrubbing", icon: EyeOff, color: "bg-red-500" },
};

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Google Gemini" },
  { value: "gliner", label: "GLiNER2 (NER)" },
  { value: "zendata", label: "Zendata (PII)" },
  { value: "custom", label: "Custom API" },
];

export default function MemorySettingsPage() {
  const [activeTab, setActiveTab] = useState("llm");
  const [loading, setLoading] = useState(true);
  
  // LLM Configs
  const [llmConfigs, setLLMConfigs] = useState([]);
  const [editingConfig, setEditingConfig] = useState(null);
  const [showApiKey, setShowApiKey] = useState({});
  
  // Entity Types
  const [entityTypes, setEntityTypes] = useState([]);
  const [selectedEntityType, setSelectedEntityType] = useState(null);
  const [entitySubtypes, setEntitySubtypes] = useState([]);
  
  // Other configs
  const [lessonTypes, setLessonTypes] = useState([]);
  const [channelTypes, setChannelTypes] = useState([]);
  const [agents, setAgents] = useState([]);
  const [settings, setSettings] = useState({});
  
  // Dialog states
  const [newEntityType, setNewEntityType] = useState({ name: "", description: "", icon: "folder" });
  const [newSubtype, setNewSubtype] = useState({ name: "", description: "" });
  const [newLessonType, setNewLessonType] = useState({ name: "", description: "", color: "#22C55E" });
  const [newChannel, setNewChannel] = useState({ name: "", description: "", icon: "message-circle" });
  const [newAgent, setNewAgent] = useState({ name: "", description: "", access_level: "private" });
  const [createdAgentKey, setCreatedAgentKey] = useState(null);

  useEffect(() => {
    loadAllData();
  }, []);

  const loadAllData = async () => {
    setLoading(true);
    try {
      const [llmRes, entityRes, lessonRes, channelRes, agentRes, settingsRes] = await Promise.all([
        getLLMConfigs(),
        getEntityTypes(),
        getLessonTypes(),
        getChannelTypes(),
        getAgents(),
        getMemorySettings(),
      ]);
      setLLMConfigs(llmRes.data);
      setEntityTypes(entityRes.data);
      setLessonTypes(lessonRes.data);
      setChannelTypes(channelRes.data);
      setAgents(agentRes.data);
      setSettings(settingsRes.data);
    } catch (error) {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const loadEntitySubtypes = async (typeId) => {
    try {
      const res = await getEntitySubtypes(typeId);
      setEntitySubtypes(res.data);
    } catch (error) {
      toast.error("Failed to load subtypes");
    }
  };

  // LLM Config handlers
  const handleSaveLLMConfig = async (configId, data) => {
    try {
      await updateLLMConfig(configId, data);
      toast.success("LLM configuration saved");
      loadAllData();
      setEditingConfig(null);
    } catch (error) {
      toast.error("Failed to save configuration");
    }
  };

  // Entity Type handlers
  const handleCreateEntityType = async () => {
    try {
      await createEntityType(newEntityType);
      toast.success("Entity type created");
      setNewEntityType({ name: "", description: "", icon: "folder" });
      loadAllData();
    } catch (error) {
      toast.error("Failed to create entity type");
    }
  };

  const handleDeleteEntityType = async (id) => {
    if (!window.confirm("Delete this entity type? This will also delete all subtypes.")) return;
    try {
      await deleteEntityType(id);
      toast.success("Entity type deleted");
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete entity type");
    }
  };

  // Subtype handlers
  const handleCreateSubtype = async () => {
    if (!selectedEntityType) return;
    try {
      await createEntitySubtype({ ...newSubtype, entity_type_id: selectedEntityType.id });
      toast.success("Subtype created");
      setNewSubtype({ name: "", description: "" });
      loadEntitySubtypes(selectedEntityType.id);
    } catch (error) {
      toast.error("Failed to create subtype");
    }
  };

  const handleDeleteSubtype = async (id) => {
    try {
      await deleteEntitySubtype(id);
      toast.success("Subtype deleted");
      loadEntitySubtypes(selectedEntityType.id);
    } catch (error) {
      toast.error("Failed to delete subtype");
    }
  };

  // Lesson Type handlers
  const handleCreateLessonType = async () => {
    try {
      await createLessonType(newLessonType);
      toast.success("Lesson type created");
      setNewLessonType({ name: "", description: "", color: "#22C55E" });
      loadAllData();
    } catch (error) {
      toast.error("Failed to create lesson type");
    }
  };

  // Channel Type handlers
  const handleCreateChannel = async () => {
    try {
      await createChannelType(newChannel);
      toast.success("Channel type created");
      setNewChannel({ name: "", description: "", icon: "message-circle" });
      loadAllData();
    } catch (error) {
      toast.error("Failed to create channel type");
    }
  };

  // Agent handlers
  const handleCreateAgent = async () => {
    try {
      const res = await createAgent(newAgent);
      setCreatedAgentKey(res.data.api_key);
      toast.success("Agent created");
      setNewAgent({ name: "", description: "", access_level: "private" });
      loadAllData();
    } catch (error) {
      toast.error("Failed to create agent");
    }
  };

  const handleToggleAgent = async (agent) => {
    try {
      await updateAgent(agent.id, { is_active: !agent.is_active });
      toast.success(agent.is_active ? "Agent deactivated" : "Agent activated");
      loadAllData();
    } catch (error) {
      toast.error("Failed to update agent");
    }
  };

  // Settings handlers
  const handleUpdateSettings = async (key, value) => {
    try {
      await updateMemorySettings({ [key]: value });
      setSettings({ ...settings, [key]: value });
      toast.success("Setting updated");
    } catch (error) {
      toast.error("Failed to update setting");
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm">LOADING SETTINGS...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="memory-settings-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Memory System Settings</h1>
          <p className="text-muted-foreground">Configure LLM integrations, schemas, and agent access</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-6 lg:w-auto lg:inline-grid">
          <TabsTrigger value="llm" className="gap-2" data-testid="tab-llm">
            <Cpu className="w-4 h-4" /> LLM APIs
          </TabsTrigger>
          <TabsTrigger value="entities" className="gap-2" data-testid="tab-entities">
            <Users className="w-4 h-4" /> Entities
          </TabsTrigger>
          <TabsTrigger value="lessons" className="gap-2" data-testid="tab-lessons">
            <GraduationCap className="w-4 h-4" /> Lessons
          </TabsTrigger>
          <TabsTrigger value="channels" className="gap-2" data-testid="tab-channels">
            <MessageSquare className="w-4 h-4" /> Channels
          </TabsTrigger>
          <TabsTrigger value="agents" className="gap-2" data-testid="tab-agents">
            <Key className="w-4 h-4" /> Agents
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-2" data-testid="tab-settings">
            <Settings2 className="w-4 h-4" /> General
          </TabsTrigger>
        </TabsList>

        {/* LLM Configurations Tab */}
        <TabsContent value="llm" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>LLM API Configurations</CardTitle>
              <CardDescription>
                Configure API keys and endpoints for each task type. Add your API keys to enable each feature.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {llmConfigs.map((config) => {
                const taskInfo = TASK_TYPE_LABELS[config.task_type] || { label: config.task_type, icon: Brain, color: "bg-gray-500" };
                const TaskIcon = taskInfo.icon;
                const isEditing = editingConfig?.id === config.id;
                
                return (
                  <Card key={config.id} className={`border-l-4 ${taskInfo.color}`}>
                    <CardContent className="pt-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${taskInfo.color}`}>
                            <TaskIcon className="w-5 h-5 text-white" />
                          </div>
                          <div>
                            <h3 className="font-semibold">{taskInfo.label}</h3>
                            <p className="text-sm text-muted-foreground">{config.name}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {config.api_key_preview ? (
                            <Badge variant="default" className="bg-green-500">
                              <CheckCircle2 className="w-3 h-3 mr-1" /> Configured
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="border-amber-500 text-amber-500">
                              <AlertCircle className="w-3 h-3 mr-1" /> Needs API Key
                            </Badge>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setEditingConfig(isEditing ? null : config)}
                            data-testid={`edit-llm-${config.task_type}`}
                          >
                            {isEditing ? "Cancel" : "Edit"}
                          </Button>
                        </div>
                      </div>
                      
                      {isEditing && (
                        <div className="mt-4 pt-4 border-t space-y-4">
                          <div className="grid grid-cols-2 gap-4">
                            <div>
                              <Label>Provider</Label>
                              <Select
                                value={editingConfig.provider}
                                onValueChange={(v) => setEditingConfig({ ...editingConfig, provider: v })}
                              >
                                <SelectTrigger>
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {PROVIDER_OPTIONS.map((opt) => (
                                    <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                            <div>
                              <Label>Model Name</Label>
                              <Input
                                value={editingConfig.model_name || ""}
                                onChange={(e) => setEditingConfig({ ...editingConfig, model_name: e.target.value })}
                                placeholder="e.g., gpt-4o-mini"
                              />
                            </div>
                          </div>
                          <div>
                            <Label>API Base URL</Label>
                            <Input
                              value={editingConfig.api_base_url || ""}
                              onChange={(e) => setEditingConfig({ ...editingConfig, api_base_url: e.target.value })}
                              placeholder="https://api.openai.com/v1"
                            />
                          </div>
                          <div>
                            <Label>API Key</Label>
                            <div className="flex gap-2">
                              <Input
                                type={showApiKey[config.id] ? "text" : "password"}
                                value={editingConfig.api_key || ""}
                                onChange={(e) => setEditingConfig({ ...editingConfig, api_key: e.target.value })}
                                placeholder="Enter API key"
                              />
                              <Button
                                type="button"
                                variant="outline"
                                size="icon"
                                onClick={() => setShowApiKey({ ...showApiKey, [config.id]: !showApiKey[config.id] })}
                              >
                                {showApiKey[config.id] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                              </Button>
                            </div>
                            {config.api_key_preview && (
                              <p className="text-xs text-muted-foreground mt-1">Current: {config.api_key_preview}</p>
                            )}
                          </div>
                          <Button onClick={() => handleSaveLLMConfig(config.id, editingConfig)} data-testid={`save-llm-${config.task_type}`}>
                            Save Configuration
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Entity Types Tab */}
        <TabsContent value="entities" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Entity Types</CardTitle>
                  <CardDescription>Types of entities to track (Contact, Organization, etc.)</CardDescription>
                </div>
                <Dialog>
                  <DialogTrigger asChild>
                    <Button size="sm" data-testid="add-entity-type">
                      <Plus className="w-4 h-4 mr-1" /> Add
                    </Button>
                  </DialogTrigger>
                  <DialogContent>
                    <DialogHeader>
                      <DialogTitle>Add Entity Type</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div>
                        <Label>Name</Label>
                        <Input
                          value={newEntityType.name}
                          onChange={(e) => setNewEntityType({ ...newEntityType, name: e.target.value })}
                          placeholder="e.g., Contact"
                        />
                      </div>
                      <div>
                        <Label>Description</Label>
                        <Input
                          value={newEntityType.description}
                          onChange={(e) => setNewEntityType({ ...newEntityType, description: e.target.value })}
                          placeholder="People you interact with"
                        />
                      </div>
                      <div>
                        <Label>Icon</Label>
                        <Input
                          value={newEntityType.icon}
                          onChange={(e) => setNewEntityType({ ...newEntityType, icon: e.target.value })}
                          placeholder="user"
                        />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button onClick={handleCreateEntityType}>Create</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {entityTypes.map((type) => (
                    <div
                      key={type.id}
                      className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                        selectedEntityType?.id === type.id ? "bg-accent border-primary" : "hover:bg-accent/50"
                      }`}
                      onClick={() => {
                        setSelectedEntityType(type);
                        loadEntitySubtypes(type.id);
                      }}
                      data-testid={`entity-type-${type.name}`}
                    >
                      <div>
                        <p className="font-medium">{type.name}</p>
                        <p className="text-sm text-muted-foreground">{type.description}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteEntityType(type.id);
                        }}
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>
                    {selectedEntityType ? `${selectedEntityType.name} Subtypes` : "Subtypes"}
                  </CardTitle>
                  <CardDescription>
                    {selectedEntityType ? "Subcategories for this entity type" : "Select an entity type"}
                  </CardDescription>
                </div>
                {selectedEntityType && (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button size="sm" data-testid="add-subtype">
                        <Plus className="w-4 h-4 mr-1" /> Add
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Add Subtype for {selectedEntityType.name}</DialogTitle>
                      </DialogHeader>
                      <div className="space-y-4 py-4">
                        <div>
                          <Label>Name</Label>
                          <Input
                            value={newSubtype.name}
                            onChange={(e) => setNewSubtype({ ...newSubtype, name: e.target.value })}
                            placeholder="e.g., Lead"
                          />
                        </div>
                        <div>
                          <Label>Description</Label>
                          <Input
                            value={newSubtype.description}
                            onChange={(e) => setNewSubtype({ ...newSubtype, description: e.target.value })}
                          />
                        </div>
                      </div>
                      <DialogFooter>
                        <Button onClick={handleCreateSubtype}>Create</Button>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                )}
              </CardHeader>
              <CardContent>
                {selectedEntityType ? (
                  <div className="space-y-2">
                    {entitySubtypes.map((subtype) => (
                      <div key={subtype.id} className="flex items-center justify-between p-3 rounded-lg border">
                        <p className="font-medium">{subtype.name}</p>
                        <Button variant="ghost" size="icon" onClick={() => handleDeleteSubtype(subtype.id)}>
                          <Trash2 className="w-4 h-4 text-destructive" />
                        </Button>
                      </div>
                    ))}
                    {entitySubtypes.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">No subtypes defined</p>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    Select an entity type to view subtypes
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Lesson Types Tab */}
        <TabsContent value="lessons" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Lesson Types</CardTitle>
                <CardDescription>Categories for extracted lessons (Process, Risk, Sales, etc.)</CardDescription>
              </div>
              <Dialog>
                <DialogTrigger asChild>
                  <Button size="sm" data-testid="add-lesson-type">
                    <Plus className="w-4 h-4 mr-1" /> Add
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add Lesson Type</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div>
                      <Label>Name</Label>
                      <Input
                        value={newLessonType.name}
                        onChange={(e) => setNewLessonType({ ...newLessonType, name: e.target.value })}
                        placeholder="e.g., Process"
                      />
                    </div>
                    <div>
                      <Label>Description</Label>
                      <Input
                        value={newLessonType.description}
                        onChange={(e) => setNewLessonType({ ...newLessonType, description: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>Color</Label>
                      <Input
                        type="color"
                        value={newLessonType.color}
                        onChange={(e) => setNewLessonType({ ...newLessonType, color: e.target.value })}
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button onClick={handleCreateLessonType}>Create</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {lessonTypes.map((type) => (
                  <div key={type.id} className="flex items-center justify-between p-3 rounded-lg border">
                    <div className="flex items-center gap-2">
                      <div className="w-4 h-4 rounded" style={{ backgroundColor: type.color }} />
                      <div>
                        <p className="font-medium">{type.name}</p>
                        <p className="text-xs text-muted-foreground">{type.description}</p>
                      </div>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => deleteLessonType(type.id).then(loadAllData)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Channel Types Tab */}
        <TabsContent value="channels" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Channel Types</CardTitle>
                <CardDescription>Communication channels for interactions (email, call, meeting, etc.)</CardDescription>
              </div>
              <Dialog>
                <DialogTrigger asChild>
                  <Button size="sm" data-testid="add-channel-type">
                    <Plus className="w-4 h-4 mr-1" /> Add
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add Channel Type</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div>
                      <Label>Name</Label>
                      <Input
                        value={newChannel.name}
                        onChange={(e) => setNewChannel({ ...newChannel, name: e.target.value })}
                        placeholder="e.g., email"
                      />
                    </div>
                    <div>
                      <Label>Description</Label>
                      <Input
                        value={newChannel.description}
                        onChange={(e) => setNewChannel({ ...newChannel, description: e.target.value })}
                      />
                    </div>
                    <div>
                      <Label>Icon</Label>
                      <Input
                        value={newChannel.icon}
                        onChange={(e) => setNewChannel({ ...newChannel, icon: e.target.value })}
                        placeholder="mail"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button onClick={handleCreateChannel}>Create</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                {channelTypes.map((channel) => (
                  <div key={channel.id} className="flex items-center justify-between p-3 rounded-lg border">
                    <div>
                      <p className="font-medium">{channel.name}</p>
                      <p className="text-xs text-muted-foreground">{channel.description}</p>
                    </div>
                    <Button variant="ghost" size="icon" onClick={() => deleteChannelType(channel.id).then(loadAllData)}>
                      <Trash2 className="w-4 h-4 text-destructive" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Agents Tab */}
        <TabsContent value="agents" className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Registered Agents</CardTitle>
                <CardDescription>API keys for agents to access the memory system</CardDescription>
              </div>
              <Dialog>
                <DialogTrigger asChild>
                  <Button size="sm" data-testid="add-agent">
                    <Plus className="w-4 h-4 mr-1" /> Add Agent
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Create Agent</DialogTitle>
                    <DialogDescription>Create a new agent with an API key for memory access</DialogDescription>
                  </DialogHeader>
                  {createdAgentKey ? (
                    <div className="space-y-4 py-4">
                      <div className="p-4 bg-green-500/10 border border-green-500 rounded-lg">
                        <p className="font-medium text-green-500 mb-2">Agent Created Successfully!</p>
                        <p className="text-sm text-muted-foreground mb-2">Copy this API key now. It won't be shown again.</p>
                        <div className="flex gap-2">
                          <code className="flex-1 p-2 bg-background rounded text-sm break-all">{createdAgentKey}</code>
                          <Button
                            size="icon"
                            variant="outline"
                            onClick={() => {
                              navigator.clipboard.writeText(createdAgentKey);
                              toast.success("Copied to clipboard");
                            }}
                          >
                            <Copy className="w-4 h-4" />
                          </Button>
                        </div>
                      </div>
                      <DialogFooter>
                        <Button onClick={() => setCreatedAgentKey(null)}>Done</Button>
                      </DialogFooter>
                    </div>
                  ) : (
                    <>
                      <div className="space-y-4 py-4">
                        <div>
                          <Label>Name</Label>
                          <Input
                            value={newAgent.name}
                            onChange={(e) => setNewAgent({ ...newAgent, name: e.target.value })}
                            placeholder="e.g., Email Sync Agent"
                          />
                        </div>
                        <div>
                          <Label>Description</Label>
                          <Input
                            value={newAgent.description}
                            onChange={(e) => setNewAgent({ ...newAgent, description: e.target.value })}
                          />
                        </div>
                        <div>
                          <Label>Access Level</Label>
                          <Select
                            value={newAgent.access_level}
                            onValueChange={(v) => setNewAgent({ ...newAgent, access_level: v })}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="private">Private (read/write own data)</SelectItem>
                              <SelectItem value="shared">Shared (read/write shared data)</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <DialogFooter>
                        <Button onClick={handleCreateAgent}>Create Agent</Button>
                      </DialogFooter>
                    </>
                  )}
                </DialogContent>
              </Dialog>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {agents.map((agent) => (
                  <div key={agent.id} className="flex items-center justify-between p-4 rounded-lg border">
                    <div className="flex items-center gap-3">
                      <div className={`p-2 rounded-lg ${agent.is_active ? "bg-green-500/10" : "bg-muted"}`}>
                        <Key className={`w-5 h-5 ${agent.is_active ? "text-green-500" : "text-muted-foreground"}`} />
                      </div>
                      <div>
                        <p className="font-medium">{agent.name}</p>
                        <p className="text-sm text-muted-foreground">{agent.description}</p>
                        <div className="flex items-center gap-2 mt-1">
                          <code className="text-xs bg-muted px-2 py-0.5 rounded">{agent.api_key_preview}</code>
                          <Badge variant="outline">{agent.access_level}</Badge>
                          {agent.last_used && (
                            <span className="text-xs text-muted-foreground">
                              Last used: {new Date(agent.last_used).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch
                        checked={agent.is_active}
                        onCheckedChange={() => handleToggleAgent(agent)}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => deleteAgent(agent.id).then(loadAllData)}
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
                {agents.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">
                    No agents registered. Create one to enable API access.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* General Settings Tab */}
        <TabsContent value="settings" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Chunking Settings</CardTitle>
                <CardDescription>Configure text chunking for vector storage</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Chunk Size (tokens)</Label>
                  <Input
                    type="number"
                    value={settings.chunk_size || 400}
                    onChange={(e) => handleUpdateSettings("chunk_size", parseInt(e.target.value))}
                  />
                </div>
                <div>
                  <Label>Chunk Overlap (tokens)</Label>
                  <Input
                    type="number"
                    value={settings.chunk_overlap || 80}
                    onChange={(e) => handleUpdateSettings("chunk_overlap", parseInt(e.target.value))}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Lesson Settings</CardTitle>
                <CardDescription>Configure automated lesson extraction</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Auto-extract Lessons</Label>
                    <p className="text-sm text-muted-foreground">Automatically mine lessons from interactions</p>
                  </div>
                  <Switch
                    checked={settings.auto_lesson_enabled}
                    onCheckedChange={(v) => handleUpdateSettings("auto_lesson_enabled", v)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Require Approval</Label>
                    <p className="text-sm text-muted-foreground">New lessons start as drafts</p>
                  </div>
                  <Switch
                    checked={settings.lesson_approval_required}
                    onCheckedChange={(v) => handleUpdateSettings("lesson_approval_required", v)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>PII Settings</CardTitle>
                <CardDescription>Configure PII scrubbing and data sharing</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Enable PII Scrubbing</Label>
                    <p className="text-sm text-muted-foreground">Automatically strip PII from shared data</p>
                  </div>
                  <Switch
                    checked={settings.pii_scrubbing_enabled}
                    onCheckedChange={(v) => handleUpdateSettings("pii_scrubbing_enabled", v)}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Auto-share Scrubbed</Label>
                    <p className="text-sm text-muted-foreground">Automatically share PII-stripped memories</p>
                  </div>
                  <Switch
                    checked={settings.auto_share_scrubbed}
                    onCheckedChange={(v) => handleUpdateSettings("auto_share_scrubbed", v)}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Rate Limiting</CardTitle>
                <CardDescription>Control API usage by agents</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Enable Rate Limiting</Label>
                    <p className="text-sm text-muted-foreground">Limit requests per agent</p>
                  </div>
                  <Switch
                    checked={settings.rate_limit_enabled}
                    onCheckedChange={(v) => handleUpdateSettings("rate_limit_enabled", v)}
                  />
                </div>
                <div>
                  <Label>Requests per Minute</Label>
                  <Input
                    type="number"
                    value={settings.rate_limit_per_minute || 60}
                    onChange={(e) => handleUpdateSettings("rate_limit_per_minute", parseInt(e.target.value))}
                    disabled={!settings.rate_limit_enabled}
                  />
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
