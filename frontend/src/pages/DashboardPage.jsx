import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Plus, 
  FileText, 
  GitBranch, 
  Clock, 
  Search,
  MoreVertical,
  Trash2,
  Edit
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { getPrompts, createPrompt, deletePrompt, getTemplates } from "@/lib/api";
import { toast } from "sonner";

export default function DashboardPage() {
  const navigate = useNavigate();
  const [prompts, setPrompts] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [selectedPrompt, setSelectedPrompt] = useState(null);
  const [creating, setCreating] = useState(false);
  const [limitError, setLimitError] = useState(null);
  const [newPrompt, setNewPrompt] = useState({
    name: "",
    description: "",
    template_id: null,
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [promptsRes, templatesRes] = await Promise.all([
        getPrompts(),
        getTemplates(),
      ]);
      setPrompts(promptsRes.data);
      setTemplates(templatesRes.data);
    } catch (error) {
      toast.error("Failed to load prompts");
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePrompt = async () => {
    if (!newPrompt.name.trim()) {
      toast.error("Please enter a prompt name");
      return;
    }

    setCreating(true);
    setLimitError(null);
    try {
      const response = await createPrompt(newPrompt);
      toast.success("Prompt created successfully!");
      setCreateDialogOpen(false);
      setNewPrompt({ name: "", description: "", template_id: null });
      navigate(`/app/prompts/${response.data.id}`);
    } catch (error) {
      if (error.response?.status === 403) {
        setLimitError(error.response.data.detail);
      } else {
        toast.error(error.response?.data?.detail || "Failed to create prompt");
      }
    } finally {
      setCreating(false);
    }
  };

  const handleDeletePrompt = async () => {
    if (!selectedPrompt) return;

    try {
      await deletePrompt(selectedPrompt.id);
      toast.success("Prompt deleted");
      setDeleteDialogOpen(false);
      setSelectedPrompt(null);
      loadData();
    } catch (error) {
      toast.error("Failed to delete prompt");
    }
  };

  const filteredPrompts = prompts.filter(
    (p) =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="p-8" data-testid="dashboard-loading">
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-24 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="dashboard-page">
      {/* Header */}
      <div className="content-header">
        <div>
          <h1 className="text-2xl font-mono font-bold tracking-tight">Prompts</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {prompts.length} prompt{prompts.length !== 1 ? "s" : ""} in your workspace
          </p>
        </div>
        <Button
          onClick={() => setCreateDialogOpen(true)}
          className="font-mono uppercase tracking-wider"
          data-testid="create-prompt-btn"
        >
          <Plus className="w-4 h-4 mr-2" />
          New Prompt
        </Button>
      </div>

      {/* Content */}
      <div className="content-body">
        {/* Search */}
        <div className="mb-6">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search prompts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 font-mono"
              data-testid="search-prompts-input"
            />
          </div>
        </div>

        {/* Prompts Grid */}
        {filteredPrompts.length === 0 ? (
          <div className="empty-state" data-testid="empty-prompts">
            <FileText className="empty-state-icon" />
            <h3 className="font-mono text-lg font-semibold mb-2">
              {searchQuery ? "No prompts found" : "No prompts yet"}
            </h3>
            <p className="text-muted-foreground text-sm mb-6 max-w-sm">
              {searchQuery
                ? "Try adjusting your search query"
                : "Create your first prompt to get started with prompt management"}
            </p>
            {!searchQuery && (
              <Button
                onClick={() => setCreateDialogOpen(true)}
                className="font-mono uppercase tracking-wider"
              >
                <Plus className="w-4 h-4 mr-2" />
                Create First Prompt
              </Button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredPrompts.map((prompt) => (
              <div
                key={prompt.id}
                className="prompt-card group"
                onClick={() => navigate(`/app/prompts/${prompt.id}`)}
                data-testid={`prompt-card-${prompt.id}`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-sm bg-primary/10 flex items-center justify-center">
                      <FileText className="w-4 h-4 text-primary" />
                    </div>
                    <h3 className="font-mono font-semibold truncate">
                      {prompt.name}
                    </h3>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="opacity-0 group-hover:opacity-100 transition-opacity"
                        data-testid={`prompt-menu-${prompt.id}`}
                      >
                        <MoreVertical className="w-4 h-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/app/prompts/${prompt.id}`);
                        }}
                      >
                        <Edit className="w-4 h-4 mr-2" />
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedPrompt(prompt);
                          setDeleteDialogOpen(true);
                        }}
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>

                {prompt.description && (
                  <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                    {prompt.description}
                  </p>
                )}

                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <GitBranch className="w-3 h-3" />
                    {prompt.versions?.length || 1} version{(prompt.versions?.length || 1) !== 1 ? "s" : ""}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatDate(prompt.updated_at)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="sm:max-w-lg" data-testid="create-prompt-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">Create New Prompt</DialogTitle>
            <DialogDescription>
              Start from scratch or use a template to create your prompt.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {limitError && (
              <Alert variant="destructive" className="bg-destructive/10 border-destructive/20">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{limitError}</AlertDescription>
              </Alert>
            )}
            <div className="space-y-2">
              <Label htmlFor="name" className="font-mono text-sm">
                NAME
              </Label>
              <Input
                id="name"
                placeholder="My Agent Prompt"
                value={newPrompt.name}
                onChange={(e) =>
                  setNewPrompt((prev) => ({ ...prev, name: e.target.value }))
                }
                className="font-mono"
                data-testid="prompt-name-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description" className="font-mono text-sm">
                DESCRIPTION
              </Label>
              <Textarea
                id="description"
                placeholder="What is this prompt for?"
                value={newPrompt.description}
                onChange={(e) =>
                  setNewPrompt((prev) => ({ ...prev, description: e.target.value }))
                }
                className="font-mono min-h-[80px]"
                data-testid="prompt-description-input"
              />
            </div>

            <div className="space-y-2">
              <Label className="font-mono text-sm">TEMPLATE (Optional)</Label>
              <div className="grid grid-cols-2 gap-2">
                <div
                  className={`template-card p-3 ${
                    newPrompt.template_id === null ? "selected" : ""
                  }`}
                  onClick={() =>
                    setNewPrompt((prev) => ({ ...prev, template_id: null }))
                  }
                  data-testid="template-blank"
                >
                  <div className="font-mono text-sm font-semibold">Blank</div>
                  <div className="text-xs text-muted-foreground">
                    Start from scratch
                  </div>
                </div>
                {templates.slice(0, 3).map((template) => (
                  <div
                    key={template.id}
                    className={`template-card p-3 ${
                      newPrompt.template_id === template.id ? "selected" : ""
                    }`}
                    onClick={() =>
                      setNewPrompt((prev) => ({ ...prev, template_id: template.id }))
                    }
                    data-testid={`template-${template.id}`}
                  >
                    <div className="font-mono text-sm font-semibold truncate">
                      {template.name}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {template.sections?.length || 0} sections
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialogOpen(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreatePrompt}
              disabled={creating || !newPrompt.name.trim()}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-create-prompt-btn"
            >
              {creating ? "Creating..." : "Create Prompt"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent data-testid="delete-prompt-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">Delete Prompt</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{selectedPrompt?.name}"? This action
              cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeletePrompt}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-delete-prompt-btn"
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
