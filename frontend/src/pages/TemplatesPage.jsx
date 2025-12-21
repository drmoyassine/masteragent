import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { 
  Sparkles, 
  FileText, 
  ArrowRight,
  Layers,
  Code
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getTemplates, createPrompt } from "@/lib/api";
import { toast } from "sonner";

export default function TemplatesPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewDialog, setPreviewDialog] = useState(false);
  const [createDialog, setCreateDialog] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newPrompt, setNewPrompt] = useState({
    name: "",
    description: "",
  });

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const response = await getTemplates();
      setTemplates(response.data);
    } catch (error) {
      toast.error("Failed to load templates");
    } finally {
      setLoading(false);
    }
  };

  const handlePreview = (template) => {
    setSelectedTemplate(template);
    setPreviewDialog(true);
  };

  const handleUseTemplate = (template) => {
    setSelectedTemplate(template);
    setNewPrompt({ name: "", description: template.description || "" });
    setCreateDialog(true);
  };

  const handleCreatePrompt = async () => {
    if (!newPrompt.name.trim()) {
      toast.error("Please enter a prompt name");
      return;
    }

    setCreating(true);
    try {
      const response = await createPrompt({
        ...newPrompt,
        template_id: selectedTemplate.id,
      });
      toast.success("Prompt created from template!");
      setCreateDialog(false);
      navigate(`/app/prompts/${response.data.id}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create prompt");
    } finally {
      setCreating(false);
    }
  };

  const getTemplateIcon = (name) => {
    if (name.toLowerCase().includes("agent")) return Sparkles;
    if (name.toLowerCase().includes("task")) return Code;
    if (name.toLowerCase().includes("knowledge")) return Layers;
    return FileText;
  };

  if (loading) {
    return (
      <div className="p-8" data-testid="templates-loading">
        <div className="template-grid">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-48 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="templates-page">
      {/* Header */}
      <div className="content-header">
        <div>
          <h1 className="text-2xl font-mono font-bold tracking-tight">Templates</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Start with pre-built prompt structures
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="content-body">
        <div className="template-grid">
          {templates.map((template) => {
            const Icon = getTemplateIcon(template.name);
            return (
              <div
                key={template.id}
                className="template-card group"
                data-testid={`template-card-${template.id}`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center">
                    <Icon className="w-5 h-5 text-primary" />
                  </div>
                  <Badge variant="outline" className="font-mono text-xs">
                    {template.sections?.length || 0} sections
                  </Badge>
                </div>

                <h3 className="font-mono font-semibold text-lg mb-2">
                  {template.name}
                </h3>
                <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
                  {template.description}
                </p>

                {/* Section Preview */}
                <div className="mb-4">
                  <div className="flex flex-wrap gap-1">
                    {template.sections?.slice(0, 4).map((section, index) => (
                      <Badge
                        key={index}
                        variant="secondary"
                        className="text-xs font-mono"
                      >
                        {section.title || section.name}
                      </Badge>
                    ))}
                    {template.sections?.length > 4 && (
                      <Badge variant="secondary" className="text-xs font-mono">
                        +{template.sections.length - 4}
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handlePreview(template)}
                    className="flex-1 font-mono"
                    data-testid={`preview-template-${template.id}`}
                  >
                    Preview
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleUseTemplate(template)}
                    className="flex-1 font-mono"
                    data-testid={`use-template-${template.id}`}
                  >
                    Use
                    <ArrowRight className="w-3 h-3 ml-1" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Preview Dialog */}
      <Dialog open={previewDialog} onOpenChange={setPreviewDialog}>
        <DialogContent className="sm:max-w-2xl" data-testid="preview-template-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">{selectedTemplate?.name}</DialogTitle>
            <DialogDescription>{selectedTemplate?.description}</DialogDescription>
          </DialogHeader>

          <ScrollArea className="h-96 mt-4">
            <div className="space-y-4">
              {selectedTemplate?.sections?.map((section, index) => (
                <div
                  key={index}
                  className="border border-border rounded-sm overflow-hidden"
                >
                  <div className="bg-secondary/50 px-4 py-2 flex items-center justify-between">
                    <span className="font-mono text-sm font-semibold">
                      {String(section.order).padStart(2, "0")}_{section.name}.md
                    </span>
                    <Badge variant="outline" className="text-xs">
                      {section.title}
                    </Badge>
                  </div>
                  <pre className="p-4 text-sm font-mono whitespace-pre-wrap text-muted-foreground">
                    {section.content}
                  </pre>
                </div>
              ))}
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setPreviewDialog(false)}
              className="font-mono"
            >
              Close
            </Button>
            <Button
              onClick={() => {
                setPreviewDialog(false);
                handleUseTemplate(selectedTemplate);
              }}
              className="font-mono uppercase tracking-wider"
            >
              Use This Template
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create from Template Dialog */}
      <Dialog open={createDialog} onOpenChange={setCreateDialog}>
        <DialogContent data-testid="create-from-template-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">
              Create from "{selectedTemplate?.name}"
            </DialogTitle>
            <DialogDescription>
              Give your new prompt a name and start customizing.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="promptName" className="font-mono text-sm">
                PROMPT NAME
              </Label>
              <Input
                id="promptName"
                placeholder="My Custom Agent"
                value={newPrompt.name}
                onChange={(e) =>
                  setNewPrompt((prev) => ({ ...prev, name: e.target.value }))
                }
                className="font-mono"
                data-testid="template-prompt-name-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="promptDesc" className="font-mono text-sm">
                DESCRIPTION
              </Label>
              <Textarea
                id="promptDesc"
                placeholder="What is this prompt for?"
                value={newPrompt.description}
                onChange={(e) =>
                  setNewPrompt((prev) => ({ ...prev, description: e.target.value }))
                }
                className="font-mono min-h-[80px]"
                data-testid="template-prompt-description-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setCreateDialog(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreatePrompt}
              disabled={creating || !newPrompt.name.trim()}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-create-from-template-btn"
            >
              {creating ? "Creating..." : "Create Prompt"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
