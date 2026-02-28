import { useState, useEffect } from "react";
import { Key, Plus, Copy, Check, Trash2, Clock, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
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
import { Alert, AlertDescription } from "@/components/ui/alert";
import { getApiKeys, createApiKey, deleteApiKey } from "@/lib/api";
import { toast } from "sonner";

export default function ApiKeysPage() {
  const [keys, setKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createDialog, setCreateDialog] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadKeys();
  }, []);

  const loadKeys = async () => {
    try {
      const response = await getApiKeys();
      setKeys(response.data);
    } catch (error) {
      toast.error("Failed to load API keys");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKey = async () => {
    if (!newKeyName.trim()) {
      toast.error("Please enter a key name");
      return;
    }

    setCreating(true);
    try {
      const response = await createApiKey(newKeyName);
      setCreatedKey(response.data);
      setNewKeyName("");
      loadKeys();
    } catch (error) {
      toast.error("Failed to create API key");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteKey = async () => {
    if (!selectedKey) return;

    try {
      await deleteApiKey(selectedKey.id);
      toast.success("API key deleted");
      setDeleteDialog(false);
      setSelectedKey(null);
      loadKeys();
    } catch (error) {
      toast.error("Failed to delete API key");
    }
  };

  const handleCopyKey = () => {
    if (createdKey?.key) {
      navigator.clipboard.writeText(createdKey.key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleCloseCreateDialog = () => {
    setCreateDialog(false);
    setCreatedKey(null);
    setNewKeyName("");
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "Never";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  if (loading) {
    return (
      <div className="p-8" data-testid="api-keys-loading">
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-20 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="api-keys-page">
      {/* Header */}
      <div className="content-header">
        <div>
          <h1 className="text-2xl font-mono font-bold tracking-tight">Developer API Keys</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage API keys to let external applications fetch and render your prompts dynamically
          </p>
        </div>
        <Button
          onClick={() => setCreateDialog(true)}
          className="font-mono uppercase tracking-wider"
          data-testid="create-api-key-btn"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Key
        </Button>
      </div>

      {/* Content */}
      <div className="content-body">
        {/* Info */}
        <div className="mb-6 p-4 border border-border rounded-sm bg-card/50">
          <div className="flex items-start gap-3">
            <Key className="w-5 h-5 text-primary mt-0.5 flex-shrink-0" />
            <div className="text-sm text-muted-foreground">
              <p className="font-medium text-foreground mb-1">Using API Keys</p>
              <p>
                API Keys allow your external services or applications to authenticate with PromptSRC and execute prompts programmatically.
                Include your API key in the <code className="font-mono text-primary">X-API-Key</code> header
                when calling the render endpoint:
              </p>
              <pre className="mt-2 p-3 bg-secondary/50 rounded-sm font-mono text-xs overflow-x-auto">
                {`curl -X POST "/api/prompts/{prompt_id}/{version}/render" \\
  -H "X-API-Key: your_api_key" \\
  -H "Content-Type: application/json" \\
  -d '{"variables": {"company_name": "Acme"}}'`}
              </pre>
            </div>
          </div>
        </div>

        {/* Keys List */}
        {keys.length === 0 ? (
          <div className="empty-state" data-testid="empty-api-keys">
            <Key className="empty-state-icon" />
            <h3 className="font-mono text-lg font-semibold mb-2">No API keys</h3>
            <p className="text-muted-foreground text-sm mb-6 max-w-sm">
              Create an API key to use the render endpoint in your applications
            </p>
            <Button
              onClick={() => setCreateDialog(true)}
              className="font-mono uppercase tracking-wider"
            >
              <Plus className="w-4 h-4 mr-2" />
              Create First Key
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((key) => (
              <div
                key={key.id}
                className="flex items-center justify-between p-4 border border-border rounded-sm hover:border-primary/30 transition-colors"
                data-testid={`api-key-${key.id}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center">
                    <Key className="w-5 h-5 text-primary" />
                  </div>
                  <div>
                    <div className="font-mono font-semibold">{key.name}</div>
                    <div className="text-sm text-muted-foreground font-mono">
                      {key.key_preview}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-6">
                  <div className="text-right text-sm">
                    <div className="text-muted-foreground flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Created: {formatDate(key.created_at)}
                    </div>
                    <div className="text-muted-foreground flex items-center gap-1">
                      Last used: {key.last_used ? formatDate(key.last_used) : "Never"}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedKey(key);
                      setDeleteDialog(true);
                    }}
                    className="text-destructive hover:text-destructive"
                    data-testid={`delete-key-${key.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={createDialog} onOpenChange={handleCloseCreateDialog}>
        <DialogContent data-testid="create-api-key-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">
              {createdKey ? "API Key Created" : "Create API Key"}
            </DialogTitle>
            <DialogDescription>
              {createdKey
                ? "Copy your API key now. You won't be able to see it again."
                : "Give your API key a name to help you identify it later."}
            </DialogDescription>
          </DialogHeader>

          {createdKey ? (
            <div className="space-y-4 py-4">
              <Alert className="bg-accent/10 border-accent/20">
                <AlertCircle className="h-4 w-4 text-accent" />
                <AlertDescription className="text-accent">
                  Make sure to copy your API key now. You won't be able to see it again!
                </AlertDescription>
              </Alert>

              <div className="space-y-2">
                <Label className="font-mono text-sm">YOUR API KEY</Label>
                <div className="flex gap-2">
                  <Input
                    value={createdKey.key}
                    readOnly
                    className="font-mono"
                    data-testid="created-api-key-value"
                  />
                  <Button
                    variant="outline"
                    onClick={handleCopyKey}
                    className="font-mono"
                    data-testid="copy-api-key-btn"
                  >
                    {copied ? (
                      <Check className="w-4 h-4" />
                    ) : (
                      <Copy className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="keyName" className="font-mono text-sm">
                  KEY NAME
                </Label>
                <Input
                  id="keyName"
                  placeholder="e.g., Production API Key"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  className="font-mono"
                  data-testid="api-key-name-input"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            {createdKey ? (
              <Button
                onClick={handleCloseCreateDialog}
                className="font-mono uppercase tracking-wider"
              >
                Done
              </Button>
            ) : (
              <>
                <Button
                  variant="outline"
                  onClick={handleCloseCreateDialog}
                  className="font-mono"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateKey}
                  disabled={creating || !newKeyName.trim()}
                  className="font-mono uppercase tracking-wider"
                  data-testid="confirm-create-api-key-btn"
                >
                  {creating ? "Creating..." : "Create Key"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <AlertDialog open={deleteDialog} onOpenChange={setDeleteDialog}>
        <AlertDialogContent data-testid="delete-api-key-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-mono">Delete API Key</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{selectedKey?.name}"? Any applications
              using this key will no longer be able to access the API.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="font-mono">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteKey}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono uppercase tracking-wider"
              data-testid="confirm-delete-api-key-btn"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
