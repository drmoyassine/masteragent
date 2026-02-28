import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Github, Trash2, ExternalLink, AlertTriangle, Key, HardDrive } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ApiKeysPage from "./ApiKeysPage";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { getSettings, saveSettings, deleteSettings, setStorageMode as setStorageModeApi } from "@/lib/api";
import { useConfig } from "@/context/ConfigContext";
import { toast } from "sonner";

export default function SettingsPage({ onDisconnect }) {
  const navigate = useNavigate();
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updateDialog, setUpdateDialog] = useState(false);
  const [disconnectDialog, setDisconnectDialog] = useState(false);
  const [updating, setUpdating] = useState(false);
  const { storageMode, checkConfiguration } = useConfig();
  const [formData, setFormData] = useState({
    github_token: "",
    github_owner: "",
    github_repo: "",
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await getSettings();
      setSettings(response.data);
      setFormData({
        github_token: "",
        github_owner: response.data.github_owner || "",
        github_repo: response.data.github_repo || "",
      });
    } catch (error) {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateSettings = async () => {
    if (!formData.github_token || !formData.github_owner || !formData.github_repo) {
      toast.error("Please fill in all fields");
      return;
    }

    setUpdating(true);
    try {
      await saveSettings(formData);
      toast.success("Settings updated");
      setUpdateDialog(false);
      loadSettings();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to update settings");
    } finally {
      setUpdating(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await deleteSettings();
      toast.success("GitHub disconnected");
      onDisconnect();
      navigate("/setup");
    } catch (error) {
      toast.error("Failed to disconnect");
    }
  };

  const handleModeChange = async (newMode) => {
    try {
      await setStorageModeApi(newMode);
      toast.success(`Storage mode switched to ${newMode}`);
      await checkConfiguration();
      loadSettings();
    } catch (error) {
      toast.error("Failed to switch storage mode");
    }
  };

  const handleChange = (field) => (e) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
  };

  if (loading) {
    return (
      <div className="p-8" data-testid="settings-loading">
        <div className="skeleton h-48 w-full max-w-2xl" />
      </div>
    );
  }

  return (
    <div data-testid="settings-page">
      {/* Header */}
      <div className="content-header">
        <div>
          <h1 className="text-2xl font-mono font-bold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage your Prompt Manager configuration
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="content-body">
        <Tabs defaultValue="general" className="space-y-6">
          <TabsList className="mb-4">
            <TabsTrigger value="general" className="gap-2">
              <Github className="w-4 h-4" />
              GitHub Connection
            </TabsTrigger>
            <TabsTrigger value="api-keys" className="gap-2">
              <Key className="w-4 h-4" />
              Developer API Keys
            </TabsTrigger>
          </TabsList>

          <TabsContent value="general">
            <div className="max-w-2xl space-y-6">
              {/* Storage Mode Toggle */}
              <div className="border border-border rounded-sm p-6 bg-secondary/20">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-sm bg-blue-500/10 flex items-center justify-center">
                      <HardDrive className="w-5 h-5 text-blue-500" />
                    </div>
                    <div>
                      <h2 className="font-mono font-semibold">Active Storage Mode</h2>
                      <p className="text-sm text-muted-foreground">
                        Choose where your prompts are stored
                      </p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Button
                    variant={storageMode === 'local' ? 'default' : 'outline'}
                    className="h-auto py-4 flex-col gap-1 font-mono"
                    onClick={() => handleModeChange('local')}
                  >
                    <HardDrive className="w-5 h-5" />
                    <span className="text-xs">Local Filesystem</span>
                  </Button>
                  <Button
                    variant={storageMode === 'github' ? 'default' : 'outline'}
                    disabled={!settings?.has_github}
                    className="h-auto py-4 flex-col gap-1 font-mono"
                    onClick={() => handleModeChange('github')}
                  >
                    <Github className="w-5 h-5" />
                    <span className="text-xs">GitHub Cloud</span>
                  </Button>
                </div>
                {!settings?.has_github && (
                  <p className="text-[10px] text-muted-foreground mt-2 text-center">
                    Connect GitHub below to enable cloud storage
                  </p>
                )}
              </div>

              {/* GitHub Connection */}
              <div className="border border-border rounded-sm p-6">
                <div className="flex items-start justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center">
                      <Github className="w-5 h-5 text-primary" />
                    </div>
                    <div>
                      <h2 className="font-mono font-semibold">GitHub Connection</h2>
                      <p className="text-sm text-muted-foreground">
                        Your prompts are stored in this repository
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${settings?.has_github ? 'bg-primary animate-pulse-slow' : 'bg-muted'}`} />
                    <span className={`text-sm font-mono ${settings?.has_github ? 'text-primary' : 'text-muted-foreground'}`}>
                      {settings?.has_github ? 'Connected' : 'Not Connected'}
                    </span>
                  </div>
                </div>

                {!settings?.has_github && (
                  <div className="bg-primary/5 rounded-sm p-4 mb-6 border border-primary/10">
                    <p className="text-sm text-primary/80 mb-2">
                      Connect your GitHub account to enable cloud sync and version history for your prompts.
                    </p>
                    <div className="text-xs text-muted-foreground space-y-2">
                      <p>
                        Generate a <strong>Fine-grained Token</strong> (recommended) or <strong>Classic PAT</strong>:
                      </p>
                      <ul className="list-disc list-inside space-y-1 ml-1">
                        <li><strong>Fine-grained:</strong> Repository access -> Select Repository; Permissions -> <strong>Contents: Read and write</strong></li>
                        <li><strong>Classic:</strong> Enable the <code className="bg-muted px-1 rounded text-foreground">repo</code> scope</li>
                      </ul>
                      <a
                        href="https://github.com/settings/tokens?type=beta"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline inline-flex items-center"
                      >
                        Create Fine-grained Token <ExternalLink className="w-3 h-3 ml-1" />
                      </a>
                    </div>
                  </div>
                )}

                {settings?.has_github && (
                  <>
                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div className="space-y-1">
                        <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider">
                          Owner
                        </span>
                        <div className="font-mono">{settings?.github_owner}</div>
                      </div>
                      <div className="space-y-1">
                        <span className="text-xs text-muted-foreground font-mono uppercase tracking-wider">
                          Repository
                        </span>
                        <div className="font-mono">{settings?.github_repo}</div>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <Button
                        variant="outline"
                        onClick={() => setUpdateDialog(true)}
                        className="font-mono"
                        data-testid="update-settings-btn"
                      >
                        Update Connection
                      </Button>
                      <Button
                        variant="outline"
                        asChild
                        className="font-mono"
                      >
                        <a
                          href={`https://github.com/${settings?.github_owner}/${settings?.github_repo}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          data-testid="view-repo-link"
                        >
                          <ExternalLink className="w-4 h-4 mr-2" />
                          View Repository
                        </a>
                      </Button>
                    </div>
                  </>
                )}

                {!settings?.has_github && (
                  <Button
                    onClick={() => setUpdateDialog(true)}
                    className="font-mono uppercase tracking-wider"
                    data-testid="connect-github-btn"
                  >
                    Connect GitHub
                  </Button>
                )}
              </div>

              {/* Danger Zone */}
              <div className="border border-destructive/30 rounded-sm p-6">
                <div className="flex items-center gap-3 mb-4">
                  <AlertTriangle className="w-5 h-5 text-destructive" />
                  <h2 className="font-mono font-semibold text-destructive">Danger Zone</h2>
                </div>
                <p className="text-sm text-muted-foreground mb-4">
                  Disconnecting will remove your GitHub configuration. Your prompts will
                  remain in the repository but won't be accessible from this instance.
                </p>
                <Button
                  variant="outline"
                  onClick={() => setDisconnectDialog(true)}
                  className="font-mono text-destructive border-destructive/30 hover:bg-destructive/10"
                  data-testid="disconnect-github-btn"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Disconnect GitHub
                </Button>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="api-keys" className="m-0">
            <div className="border border-border rounded-sm shadow-sm bg-background">
              <ApiKeysPage />
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Update Dialog */}
      <Dialog open={updateDialog} onOpenChange={setUpdateDialog}>
        <DialogContent data-testid="update-settings-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono text-xl">Update GitHub Connection</DialogTitle>
            <DialogDescription className="space-y-2 pt-2">
              <p>For cloud sync to work, your token must have:</p>
              <ul className="text-xs list-disc list-inside opacity-80">
                <li><strong>Fine-grained:</strong> Repository Content (Read & Write)</li>
                <li><strong>Classic PAT:</strong> full 'repo' scope</li>
              </ul>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="token" className="font-mono text-sm">
                NEW TOKEN (Required)
              </Label>
              <Input
                id="token"
                type="password"
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                value={formData.github_token}
                onChange={handleChange("github_token")}
                className="font-mono"
                data-testid="update-github-token-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="owner" className="font-mono text-sm">
                  OWNER / ORG
                </Label>
                <Input
                  id="owner"
                  placeholder="username or org"
                  value={formData.github_owner}
                  onChange={handleChange("github_owner")}
                  className="font-mono"
                  data-testid="update-github-owner-input"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="repo" className="font-mono text-sm">
                  REPOSITORY
                </Label>
                <Input
                  id="repo"
                  placeholder="my-prompts"
                  value={formData.github_repo}
                  onChange={handleChange("github_repo")}
                  className="font-mono"
                  data-testid="update-github-repo-input"
                />
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setUpdateDialog(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              onClick={handleUpdateSettings}
              disabled={updating}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-update-settings-btn"
            >
              {updating ? "Updating..." : "Update"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Disconnect Dialog */}
      <AlertDialog open={disconnectDialog} onOpenChange={setDisconnectDialog}>
        <AlertDialogContent data-testid="disconnect-github-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-mono">Disconnect GitHub</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to disconnect from GitHub? You'll need to
              reconfigure your connection to continue using Prompt Manager.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="font-mono">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDisconnect}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono uppercase tracking-wider"
              data-testid="confirm-disconnect-btn"
            >
              Disconnect
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
