import { useState, useEffect } from "react";
import {
  Plus,
  Trash2,
  Building,
  FileText,
  Pencil,
  X,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  getPromptVariables,
  createPromptVariable,
  updatePromptVariable,
  deletePromptVariable,
  getAccountVariables,
  createAccountVariable,
} from "@/lib/api";
import { toast } from "sonner";

/**
 * VariablesPanel Component
 * 
 * Displays and manages variables for a prompt:
 * - Prompt Variables: Editable, specific to this prompt/version
 * - Account Variables: Read-only in this context, inherited from account level
 */
export default function VariablesPanel({ promptId, version, onVariablesChange }) {
  const [promptVariables, setPromptVariables] = useState([]);
  const [accountVariables, setAccountVariables] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Dialog states
  const [editDialog, setEditDialog] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState(false);
  const [selectedVariable, setSelectedVariable] = useState(null);
  
  // Form state
  const [formData, setFormData] = useState({
    name: "",
    value: "",
    description: "",
    required: false,
    scope: "prompt", // "prompt" or "account"
  });

  useEffect(() => {
    if (promptId && version) {
      loadVariables();
    }
  }, [promptId, version]);

  const loadVariables = async () => {
    setLoading(true);
    try {
      const [promptRes, accountRes] = await Promise.all([
        getPromptVariables(promptId, version),
        getAccountVariables(),
      ]);
      setPromptVariables(promptRes.data || []);
      setAccountVariables(accountRes.data || []);
    } catch (error) {
      console.error("Failed to load variables:", error);
      toast.error("Failed to load variables");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateVariable = async () => {
    if (!formData.name.trim()) {
      toast.error("Variable name is required");
      return;
    }

    // Validate variable name format
    const namePattern = /^[a-zA-Z_][a-zA-Z0-9_]*$/;
    if (!namePattern.test(formData.name)) {
      toast.error("Variable name must start with a letter or underscore and contain only alphanumeric characters");
      return;
    }

    try {
      if (formData.scope === "account") {
        // Create account-level variable
        await createAccountVariable({
          name: formData.name,
          value: formData.value,
          description: formData.description,
          required: formData.required,
        });
        toast.success("Account variable created");
      } else {
        // Create prompt-level variable
        await createPromptVariable(promptId, formData, version);
        toast.success("Prompt variable created");
      }
      setEditDialog(false);
      resetForm();
      loadVariables();
      onVariablesChange?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create variable");
    }
  };

  const handleUpdateVariable = async () => {
    if (!selectedVariable) return;

    try {
      await updatePromptVariable(promptId, selectedVariable.name, formData, version);
      toast.success("Variable updated");
      setEditDialog(false);
      resetForm();
      loadVariables();
      onVariablesChange?.();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to update variable");
    }
  };

  const handleDeleteVariable = async () => {
    if (!selectedVariable) return;

    try {
      await deletePromptVariable(promptId, selectedVariable.name, version);
      toast.success("Variable deleted");
      setDeleteDialog(false);
      resetForm();
      loadVariables();
      onVariablesChange?.();
    } catch (error) {
      toast.error("Failed to delete variable");
    }
  };

  const openCreateDialog = () => {
    resetForm();
    setSelectedVariable(null);
    setEditDialog(true);
  };

  const openEditDialog = (variable) => {
    setSelectedVariable(variable);
    setFormData({
      name: variable.name,
      value: variable.value || "",
      description: variable.description || "",
      required: variable.required || false,
    });
    setEditDialog(true);
  };

  const openDeleteDialog = (variable) => {
    setSelectedVariable(variable);
    setDeleteDialog(true);
  };

  const resetForm = () => {
    setFormData({
      name: "",
      value: "",
      description: "",
      required: false,
      scope: "prompt",
    });
    setSelectedVariable(null);
  };

  if (loading) {
    return (
      <div className="p-4 space-y-4">
        <div className="skeleton h-8 w-32" />
        <div className="skeleton h-24 w-full" />
        <div className="skeleton h-8 w-32 mt-4" />
        <div className="skeleton h-24 w-full" />
      </div>
    );
  }

  return (
    <div className="variables-panel h-full flex flex-col" data-testid="variables-panel">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between">
        <span className="font-mono text-sm text-muted-foreground uppercase tracking-wider">
          Variables
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={openCreateDialog}
          data-testid="add-variable-btn"
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {/* Prompt Variables Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">Prompt Variables</span>
              <Badge variant="outline" className="text-xs">
                {promptVariables.length}
              </Badge>
            </div>

            {promptVariables.length === 0 ? (
              <p className="text-sm text-muted-foreground pl-6">
                No prompt variables. Add one to get started.
              </p>
            ) : (
              <div className="space-y-2 pl-6">
                {promptVariables.map((variable) => (
                  <div
                    key={variable.id}
                    className="variable-item flex items-center justify-between p-2 rounded-md border border-border hover:bg-accent/5 group"
                    data-testid={`prompt-variable-${variable.name}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-sm font-mono text-primary">
                          {`{{${variable.name}}}`}
                        </code>
                        {variable.required && (
                          <Badge variant="destructive" className="text-xs">
                            Required
                          </Badge>
                        )}
                      </div>
                      {variable.description && (
                        <p className="text-xs text-muted-foreground truncate">
                          {variable.description}
                        </p>
                      )}
                      {variable.value && (
                        <p className="text-xs text-muted-foreground truncate font-mono">
                          Default: {variable.value}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditDialog(variable)}
                        className="h-7 w-7 p-0"
                        data-testid={`edit-variable-${variable.name}`}
                      >
                        <Pencil className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openDeleteDialog(variable)}
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        data-testid={`delete-variable-${variable.name}`}
                      >
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Account Variables Section */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Building className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">Account Variables</span>
              <Badge variant="secondary" className="text-xs">
                Inherited
              </Badge>
            </div>

            {accountVariables.length === 0 ? (
              <p className="text-sm text-muted-foreground pl-6">
                No account variables defined.
              </p>
            ) : (
              <div className="space-y-2 pl-6">
                {accountVariables.map((variable) => (
                  <div
                    key={variable.id}
                    className="variable-item flex items-center justify-between p-2 rounded-md border border-border bg-muted/30"
                    data-testid={`account-variable-${variable.name}`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-sm font-mono text-secondary-foreground">
                          {`{{${variable.name}}}`}
                        </code>
                        <Badge variant="outline" className="text-xs">
                          Account
                        </Badge>
                      </div>
                      {variable.description && (
                        <p className="text-xs text-muted-foreground truncate">
                          {variable.description}
                        </p>
                      )}
                      {variable.value && (
                        <p className="text-xs text-muted-foreground truncate font-mono">
                          {variable.value}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </ScrollArea>

      {/* Create/Edit Variable Dialog */}
      <Dialog open={editDialog} onOpenChange={setEditDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {selectedVariable ? "Edit Variable" : "Add Variable"}
            </DialogTitle>
            <DialogDescription>
              {selectedVariable
                ? "Update the variable properties."
                : "Create a new variable for this prompt."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Scope Selection - only show when creating new variable */}
            {!selectedVariable && (
              <div className="space-y-2">
                <Label>Variable Scope</Label>
                <RadioGroup
                  value={formData.scope}
                  onValueChange={(value) => setFormData({ ...formData, scope: value })}
                  className="flex flex-col space-y-1"
                >
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="prompt" id="scope-prompt" data-testid="scope-prompt" />
                    <Label htmlFor="scope-prompt" className="font-normal cursor-pointer">
                      <span className="flex items-center gap-1">
                        <FileText className="w-3 h-3" />
                        Prompt Level
                      </span>
                      <span className="text-xs text-muted-foreground block">Only available in this prompt</span>
                    </Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="account" id="scope-account" data-testid="scope-account" />
                    <Label htmlFor="scope-account" className="font-normal cursor-pointer">
                      <span className="flex items-center gap-1">
                        <Building className="w-3 h-3" />
                        Account Level
                      </span>
                      <span className="text-xs text-muted-foreground block">Available in all prompts</span>
                    </Label>
                  </div>
                </RadioGroup>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="e.g., agent_name"
                disabled={!!selectedVariable}
                className="font-mono"
                data-testid="variable-name-input"
              />
              <p className="text-xs text-muted-foreground">
                Use letters, numbers, and underscores. Must start with a letter or underscore.
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="value">Default Value (optional)</Label>
              <Input
                id="value"
                value={formData.value}
                onChange={(e) =>
                  setFormData({ ...formData, value: e.target.value })
                }
                placeholder="e.g., Support Agent"
                className="font-mono"
                data-testid="variable-value-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description (optional)</Label>
              <Input
                id="description"
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="e.g., The name of the AI agent"
                data-testid="variable-description-input"
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="required">Required</Label>
                <p className="text-xs text-muted-foreground">
                  Prompt rendering will fail if this variable is not provided
                </p>
              </div>
              <Switch
                id="required"
                checked={formData.required}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, required: checked })
                }
                data-testid="variable-required-switch"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setEditDialog(false)}
              data-testid="cancel-variable-btn"
            >
              Cancel
            </Button>
            <Button
              onClick={selectedVariable ? handleUpdateVariable : handleCreateVariable}
              data-testid="save-variable-btn"
            >
              {selectedVariable ? "Update" : "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialog} onOpenChange={setDeleteDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete Variable</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the variable{" "}
              <code className="font-mono text-primary">
                {`{{${selectedVariable?.name}}}`}
              </code>
              ? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialog(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteVariable}
              data-testid="confirm-delete-variable-btn"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
