import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  Github,
  Key,
  HardDrive,
  Cpu,
  ShieldCheck,
  Database,
  Brain,
  ChevronRight
} from "lucide-react";
import { toast } from "sonner";

// API Helpers
import {
  getSettings,
  saveSettings,
  deleteSettings,
  setStorageMode as setStorageModeApi,
  getLLMProviders,
  createLLMProvider,
  updateLLMProvider,
  deleteLLMProvider,
  getLLMConfigs,
  updateLLMConfig,
  reorderPipelineNodes,
  getApiKeys,
  createApiKey,
  deleteApiKey,
  getAgents,
  createAgent,
  updateAgent,
  deleteAgent,
  getEntityTypes,
  createEntityType,
  deleteEntityType,
  getLessonTypes,
  createLessonType,
  deleteLessonType,
  getChannelTypes,
  createChannelType,
  deleteChannelType,
  getMemorySettings,
  updateMemorySettings
} from "@/lib/api";

// Sub-components
import { StorageSettings } from "@/components/settings/StorageSettings";
import { LLMProviderSettings } from "@/components/settings/LLMProviderSettings";
import { AccessSettings } from "@/components/settings/AccessSettings";
import { KnowledgeModelSettings } from "@/components/settings/KnowledgeModelSettings";
import { MemorySettings } from "@/components/settings/MemorySettings";

import { useConfig } from "@/context/ConfigContext";

const TABS = [
  { id: "storage", label: "Storage", icon: HardDrive, description: "GitHub & Local persistence" },
  { id: "llm", label: "LLM Providers", icon: Cpu, description: "API keys for AI tasks" },
  { id: "access", label: "API Access", icon: ShieldCheck, description: "Keys & Documentation" },
  { id: "model", label: "Knowledge Model", icon: Database, description: "Entity & Lesson definitions" },
  { id: "memory", label: "Memory Settings", icon: Brain, description: "Pipeline configuration" },
];

export default function SettingsPage({ onDisconnect }) {
  const navigate = useNavigate();
  const { storageMode, checkConfiguration } = useConfig();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Deep linking: initialize tab from URL, validate against available tabs
  const validTabs = ["storage", "llm", "access", "model", "memory"];
  const urlTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(validTabs.includes(urlTab) ? urlTab : "storage");
  const [loading, setLoading] = useState(true);

  // --- Shared State ---
  const [settings, setSettings] = useState(null);
  const [memorySettings, setMemorySettings] = useState({});
  const [llmProviders, setLLMProviders] = useState([]);
  const [llmConfigs, setLLMConfigs] = useState([]);
  const [promptsKeys, setPromptsKeys] = useState([]);
  const [memoryKeys, setMemoryKeys] = useState([]);
  const [entityTypes, setEntityTypes] = useState([]);
  const [lessonTypes, setLessonTypes] = useState([]);
  const [channelTypes, setChannelTypes] = useState([]);

  // --- UI State ---
  const [updating, setUpdating] = useState(false);
  const [creating, setCreating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showApiKey, setShowApiKey] = useState({});
  const [editingConfig, setEditingConfig] = useState(null);
  const [selectedKey, setSelectedKey] = useState(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState(null);

  // Dialogs
  const [updateStorageDialog, setUpdateStorageDialog] = useState(false);
  const [disconnectGithubDialog, setDisconnectGithubDialog] = useState(false);
  const [createPromptKeyDialog, setCreatePromptKeyDialog] = useState(false);
  const [createMemoryKeyDialog, setCreateMemoryKeyDialog] = useState(false);
  const [deletePromptKeyDialog, setDeletePromptKeyDialog] = useState(false);
  const [deleteMemoryKeyDialog, setDeleteMemoryKeyDialog] = useState(false);
  const [addTypeDialogOpen, setAddTypeDialogOpen] = useState(false);

  // Forms
  const [githubFormData, setGithubFormData] = useState({
    github_token: "",
    github_owner: "",
    github_repo: "",
  });
  const [newMemoryKey, setNewMemoryKey] = useState({ name: "", description: "", access_level: "private" });
  const [newType, setNewType] = useState({ name: "", description: "", type: "entity" });

  const loadAllData = useCallback(async () => {
    setLoading(true);
    try {
      const [
        promptSettingsRes,
        memorySettingsRes,
        llmProvidersRes,
        llmRes,
        pKeysRes,
        mKeysRes,
        entityRes,
        lessonRes,
        channelRes
      ] = await Promise.all([
        getSettings(),
        getMemorySettings(),
        getLLMProviders(),
        getLLMConfigs(),
        getApiKeys(),
        getAgents(),
        getEntityTypes(),
        getLessonTypes(),
        getChannelTypes()
      ]);

      setSettings(promptSettingsRes.data);
      setGithubFormData({
        github_token: "",
        github_owner: promptSettingsRes.data.github_owner || "",
        github_repo: promptSettingsRes.data.github_repo || "",
      });
      setMemorySettings(memorySettingsRes.data);
      setLLMProviders(llmProvidersRes.data);
      setLLMConfigs(llmRes.data);
      setPromptsKeys(pKeysRes.data);
      setMemoryKeys(mKeysRes.data);
      setEntityTypes(entityRes.data);
      setLessonTypes(lessonRes.data);
      setChannelTypes(channelRes.data);
    } catch (error) {
      toast.error("Failed to load settings data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // --- Handlers ---

  // Storage
  const handleModeChange = async (newMode) => {
    try {
      await setStorageModeApi(newMode);
      toast.success(`Storage mode switched to ${newMode}`);
      await checkConfiguration();
      loadAllData();
    } catch (error) {
      toast.error("Failed to switch storage mode");
    }
  };

  const handleUpdateGithub = async () => {
    setUpdating(true);
    try {
      await saveSettings(githubFormData);
      toast.success("GitHub settings updated");
      setUpdateStorageDialog(false);
      loadAllData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to update settings");
    } finally {
      setUpdating(false);
    }
  };

  const handleDisconnectGithub = async () => {
    try {
      await deleteSettings();
      toast.success("GitHub disconnected");
      if (onDisconnect) onDisconnect();
      navigate("/setup");
    } catch (error) {
      toast.error("Failed to disconnect");
    }
  };

  // LLM Providers & Configs
  const handleSaveLLMConfig = async (configId, data) => {
    try {
      await updateLLMConfig(configId, data);
      toast.success("LLM configuration saved");
      setEditingConfig(null);
      loadAllData();
    } catch (error) {
      toast.error("Failed to save configuration");
    }
  };

  const handleDeleteLLMConfig = async (configId) => {
    if (!window.confirm("Are you sure you want to delete this pipeline step?")) return;
    try {
      await deleteLLMConfig(configId);
      toast.success("Pipeline step deleted");
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete pipeline step");
    }
  };

  const handleReorderPipeline = async (pipelineStage, newArray) => {
    // Optimistic UI update
    setLLMConfigs((prev) => {
      const otherNodes = prev.filter(c => c.pipeline_stage !== pipelineStage);
      const orderedNodes = newArray.map((c, i) => ({ ...c, execution_order: i }));
      return [...otherNodes, ...orderedNodes];
    });

    const payload = {
      pipeline_stage: pipelineStage,
      ordered_ids: newArray.map(c => c.id)
    };

    try {
      await reorderPipelineNodes(payload);
    } catch (error) {
      toast.error("Failed to save pipeline order");
      loadAllData(); // Revert on failure
    }
  };

  const handleSaveLLMProvider = async (data) => {
    try {
      if (data.id) {
        await updateLLMProvider(data.id, data);
      } else {
        await createLLMProvider(data);
      }
      toast.success("Provider account saved");
      loadAllData();
      return true;
    } catch (error) {
      toast.error("Failed to save provider account");
      return false;
    }
  };

  const handleDeleteLLMProvider = async (providerId) => {
    if (!window.confirm("Are you sure you want to delete this provider account? Tasks relying on it might stop working.")) return;
    try {
      await deleteLLMProvider(providerId);
      toast.success("Provider account deleted");
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete provider account");
    }
  };

  // Access (Prompts Keys)
  const handleCreatePromptKey = async () => {
    setCreating(true);
    try {
      const res = await createApiKey(newKeyName);
      setCreatedKey(res.data);
      setNewKeyName("");
      loadAllData();
    } catch (error) {
      toast.error("Failed to create key");
    } finally {
      setCreating(false);
    }
  };

  const handleDeletePromptKey = async () => {
    try {
      await deleteApiKey(selectedKey.id);
      toast.success("Prompt key deleted");
      setDeletePromptKeyDialog(false);
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete key");
    }
  };

  // Access (Memory Keys)
  const handleCreateMemoryKey = async () => {
    setCreating(true);
    try {
      const res = await createAgent(newMemoryKey);
      setCreatedKey(res.data);
      setNewMemoryKey({ name: "", description: "", access_level: "private" });
      loadAllData();
    } catch (error) {
      toast.error("Failed to create memory key");
    } finally {
      setCreating(false);
    }
  };

  const handleToggleMemoryKey = async (agent) => {
    try {
      await updateAgent(agent.id, { is_active: !agent.is_active });
      toast.success(agent.is_active ? "Key deactivated" : "Key activated");
      loadAllData();
    } catch (error) {
      toast.error("Failed to update status");
    }
  };

  const handleDeleteMemoryKey = async () => {
    try {
      await deleteAgent(selectedKey.id);
      toast.success("Memory key deleted");
      setDeleteMemoryKeyDialog(false);
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete key");
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("Copied to clipboard");
  };

  // Knowledge Model
  const handleAddType = async () => {
    try {
      if (newType.type === "entity") await createEntityType(newType);
      else if (newType.type === "lesson") await createLessonType(newType);
      else if (newType.type === "channel") await createChannelType(newType);

      toast.success(`${newType.type} type added`);
      setAddTypeDialogOpen(false);
      loadAllData();
    } catch (error) {
      toast.error("Failed to add type");
    }
  };

  const handleDeleteType = async (type, id) => {
    if (!window.confirm(`Are you sure you want to delete this ${type} type?`)) return;
    try {
      if (type === "entity") await deleteEntityType(id);
      else if (type === "lesson") await deleteLessonType(id);
      else if (type === "channel") await deleteChannelType(id);

      toast.success(`${type} type deleted`);
      loadAllData();
    } catch (error) {
      toast.error("Failed to delete type");
    }
  };

  // General Memory Settings
  const handleUpdateGeneralSettings = async (key, value) => {
    try {
      await updateMemorySettings({ [key]: value });
      setMemorySettings(prev => ({ ...prev, [key]: value }));
      toast.success("Setting updated");
    } catch (error) {
      toast.error("Failed to update setting");
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "Never";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm tracking-widest">LOADING SETTINGS...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" data-testid="settings-page">
      <div className="content-header border-b pb-6 mb-6">
        <div>
          <h1 className="text-2xl font-mono font-bold tracking-tight">System Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure storage, AI providers, and system behavior
          </p>
        </div>
      </div>

      <div className="flex flex-1 gap-12">
        {/* Sidebar Navigation */}
        <aside className="w-64 space-y-1">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => {
                  setActiveTab(tab.id);
                  setSearchParams({ tab: tab.id }, { replace: true });
                }}
                className={`w-full flex items-start gap-3 p-3 rounded-lg transition-all text-left group ${isActive
                    ? "bg-primary/10 border-l-2 border-primary"
                    : "hover:bg-secondary/50 border-l-2 border-transparent"
                  }`}
              >
                <Icon className={`w-5 h-5 mt-0.5 ${isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground"}`} />
                <div className="min-w-0">
                  <div className={`text-sm font-semibold truncate ${isActive ? "text-primary font-bold" : "text-foreground"}`}>
                    {tab.label}
                  </div>
                  <div className="text-[10px] text-muted-foreground truncate font-mono">
                    {tab.description}
                  </div>
                </div>
                {isActive && <ChevronRight className="w-4 h-4 ml-auto text-primary self-center" />}
              </button>
            );
          })}
        </aside>

        {/* Content Area */}
        <main className="flex-1 pb-20">
          {activeTab === "storage" && (
            <StorageSettings
              settings={settings}
              storageMode={storageMode}
              formData={githubFormData}
              updating={updating}
              updateDialog={updateStorageDialog}
              setUpdateDialog={setUpdateStorageDialog}
              disconnectDialog={disconnectGithubDialog}
              setDisconnectDialog={setDisconnectGithubDialog}
              onModeChange={handleModeChange}
              onUpdateSettings={handleUpdateGithub}
              onDisconnect={handleDisconnectGithub}
              onFormDataChange={(field, value) => setGithubFormData(prev => ({ ...prev, [field]: value }))}
            />
          )}

          {activeTab === "llm" && (
            <LLMProviderSettings
              llmProviders={llmProviders}
              onSaveProvider={handleSaveLLMProvider}
              onDeleteProvider={handleDeleteLLMProvider}
            />
          )}

          {activeTab === "access" && (
            <AccessSettings
              promptsKeys={promptsKeys}
              memoryKeys={memoryKeys}
              createPromptKeyDialog={createPromptKeyDialog}
              setCreatePromptKeyDialog={setCreatePromptKeyDialog}
              createMemoryKeyDialog={createMemoryKeyDialog}
              setCreateMemoryKeyDialog={setCreateMemoryKeyDialog}
              deletePromptKeyDialog={deletePromptKeyDialog}
              setDeletePromptKeyDialog={setDeletePromptKeyDialog}
              deleteMemoryKeyDialog={deleteMemoryKeyDialog}
              setDeleteMemoryKeyDialog={setDeleteMemoryKeyDialog}
              selectedKey={selectedKey}
              setSelectedKey={setSelectedKey}
              newKeyName={newKeyName}
              setNewKeyName={setNewKeyName}
              newMemoryKey={newMemoryKey}
              setNewMemoryKey={setNewMemoryKey}
              createdKey={createdKey}
              setCreatedKey={setCreatedKey}
              copied={copied}
              onCopyKey={handleCopy}
              onCreatePromptKey={handleCreatePromptKey}
              onDeletePromptKey={handleDeletePromptKey}
              onCreateMemoryKey={handleCreateMemoryKey}
              onDeleteMemoryKey={handleDeleteMemoryKey}
              onToggleMemoryKey={handleToggleMemoryKey}
              creating={creating}
              formatDate={formatDate}
            />
          )}

          {activeTab === "model" && (
            <KnowledgeModelSettings
              entityTypes={entityTypes}
              lessonTypes={lessonTypes}
              channelTypes={channelTypes}
              newType={newType}
              setNewType={setNewType}
              addTypeDialogOpen={addTypeDialogOpen}
              setAddTypeDialogOpen={setAddTypeDialogOpen}
              onAddType={handleAddType}
              onDeleteType={handleDeleteType}
              loading={loading}
            />
          )}

          {activeTab === "memory" && (
            <MemorySettings
              settings={memorySettings}
              llmConfigs={llmConfigs}
              llmProviders={llmProviders}
              onUpdateSettings={handleUpdateGeneralSettings}
              onSaveConfig={handleSaveLLMConfig}
              onDeleteConfig={handleDeleteLLMConfig}
              onReorderPipeline={handleReorderPipeline}
              onUpdateMemorySettings={handleUpdateGeneralSettings}
              activeTab={searchParams.get("memoryTab") || "raw_interactions"}
              onTabChange={(tab) => setSearchParams({ tab: "memory", memoryTab: tab }, { replace: true })}
            />
          )}
        </main>
      </div>
    </div>
  );
}
