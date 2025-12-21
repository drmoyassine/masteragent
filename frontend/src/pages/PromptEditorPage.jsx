import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Save,
  Plus,
  FileText,
  Trash2,
  GripVertical,
  GitBranch,
  Play,
  Copy,
  Check,
  ChevronDown,
  AlertCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  getPrompt,
  getPromptSections,
  getSectionContent,
  createSection,
  updateSection,
  deleteSection,
  getPromptVersions,
  createVersion,
  renderPrompt,
} from "@/lib/api";
import { toast } from "sonner";

export default function PromptEditorPage() {
  const { promptId } = useParams();
  const navigate = useNavigate();

  const [prompt, setPrompt] = useState(null);
  const [sections, setSections] = useState([]);
  const [versions, setVersions] = useState([]);
  const [currentVersion, setCurrentVersion] = useState("main");
  const [selectedSection, setSelectedSection] = useState(null);
  const [sectionContent, setSectionContent] = useState("");
  const [originalContent, setOriginalContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Dialogs
  const [newSectionDialog, setNewSectionDialog] = useState(false);
  const [newVersionDialog, setNewVersionDialog] = useState(false);
  const [renderDialog, setRenderDialog] = useState(false);
  const [deleteDialog, setDeleteDialog] = useState(false);

  // New section form
  const [newSection, setNewSection] = useState({ name: "", title: "", content: "" });

  // New version form
  const [newVersion, setNewVersion] = useState({ version_name: "" });

  // Render form
  const [renderVariables, setRenderVariables] = useState({});
  const [renderResult, setRenderResult] = useState(null);
  const [renderError, setRenderError] = useState(null);
  const [copied, setCopied] = useState(false);

  // Extracted variables
  const [variables, setVariables] = useState([]);

  useEffect(() => {
    loadPromptData();
  }, [promptId]);

  useEffect(() => {
    if (currentVersion) {
      loadSections();
    }
  }, [currentVersion]);

  useEffect(() => {
    setHasChanges(sectionContent !== originalContent);
  }, [sectionContent, originalContent]);

  const loadPromptData = async () => {
    try {
      const [promptRes, versionsRes] = await Promise.all([
        getPrompt(promptId),
        getPromptVersions(promptId),
      ]);
      setPrompt(promptRes.data);
      setVersions(versionsRes.data);
    } catch (error) {
      toast.error("Failed to load prompt");
      navigate("/");
    } finally {
      setLoading(false);
    }
  };

  const loadSections = async () => {
    try {
      const response = await getPromptSections(promptId, currentVersion);
      setSections(response.data);
      if (response.data.length > 0 && !selectedSection) {
        await loadSectionContent(response.data[0]);
      }
    } catch (error) {
      console.error("Failed to load sections:", error);
    }
  };

  const loadSectionContent = async (section) => {
    try {
      const response = await getSectionContent(
        promptId,
        section.filename,
        currentVersion
      );
      setSelectedSection(section);
      setSectionContent(response.data.content);
      setOriginalContent(response.data.content);
      setVariables(response.data.variables || []);
    } catch (error) {
      toast.error("Failed to load section content");
    }
  };

  const handleSaveSection = async () => {
    if (!selectedSection || !hasChanges) return;

    setSaving(true);
    try {
      await updateSection(
        promptId,
        selectedSection.filename,
        { content: sectionContent },
        currentVersion
      );
      setOriginalContent(sectionContent);
      toast.success("Section saved");
    } catch (error) {
      toast.error("Failed to save section");
    } finally {
      setSaving(false);
    }
  };

  const handleCreateSection = async () => {
    if (!newSection.name.trim()) {
      toast.error("Please enter a section name");
      return;
    }

    try {
      const content = newSection.content || `# ${newSection.title || newSection.name}\n\nYour content here...`;
      await createSection(
        promptId,
        {
          name: newSection.name,
          title: newSection.title || newSection.name,
          content,
        },
        currentVersion
      );
      toast.success("Section created");
      setNewSectionDialog(false);
      setNewSection({ name: "", title: "", content: "" });
      loadSections();
    } catch (error) {
      toast.error("Failed to create section");
    }
  };

  const handleDeleteSection = async () => {
    if (!selectedSection) return;

    try {
      await deleteSection(promptId, selectedSection.filename, currentVersion);
      toast.success("Section deleted");
      setDeleteDialog(false);
      setSelectedSection(null);
      setSectionContent("");
      setOriginalContent("");
      loadSections();
    } catch (error) {
      toast.error("Failed to delete section");
    }
  };

  const handleCreateVersion = async () => {
    if (!newVersion.version_name.trim()) {
      toast.error("Please enter a version name");
      return;
    }

    try {
      await createVersion(promptId, {
        version_name: newVersion.version_name,
        source_version: currentVersion,
      });
      toast.success("Version created");
      setNewVersionDialog(false);
      setNewVersion({ version_name: "" });
      const versionsRes = await getPromptVersions(promptId);
      setVersions(versionsRes.data);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to create version");
    }
  };

  const handleRenderPrompt = async () => {
    setRenderError(null);
    setRenderResult(null);

    try {
      const response = await renderPrompt(promptId, currentVersion, renderVariables);
      setRenderResult(response.data);
    } catch (error) {
      if (error.response?.data?.detail?.missing) {
        setRenderError({
          message: "Missing required variables",
          missing: error.response.data.detail.missing,
        });
      } else {
        setRenderError({
          message: error.response?.data?.detail || "Failed to render prompt",
        });
      }
    }
  };

  const handleCopyRendered = () => {
    if (renderResult?.compiled_prompt) {
      navigator.clipboard.writeText(renderResult.compiled_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const extractVariablesFromContent = useCallback((content) => {
    const pattern = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;
    const matches = [...content.matchAll(pattern)];
    return [...new Set(matches.map((m) => m[1]))];
  }, []);

  // Get all variables from all sections for render dialog
  const getAllVariables = useCallback(() => {
    const allVars = new Set();
    // Add variables from current section
    variables.forEach((v) => allVars.add(v));
    // Also check current content
    extractVariablesFromContent(sectionContent).forEach((v) => allVars.add(v));
    return [...allVars];
  }, [variables, sectionContent, extractVariablesFromContent]);

  if (loading) {
    return (
      <div className="p-8" data-testid="editor-loading">
        <div className="skeleton h-8 w-48 mb-4" />
        <div className="skeleton h-96 w-full" />
      </div>
    );
  }

  return (
    <div data-testid="prompt-editor-page">
      {/* Header */}
      <div className="content-header">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/")}
            className="font-mono"
            data-testid="back-btn"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <div>
            <h1 className="text-xl font-mono font-bold tracking-tight">
              {prompt?.name}
            </h1>
            <p className="text-sm text-muted-foreground">{prompt?.description}</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Version Selector */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" className="font-mono" data-testid="version-selector">
                <GitBranch className="w-4 h-4 mr-2" />
                {currentVersion}
                <ChevronDown className="w-4 h-4 ml-2" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {versions.map((v) => (
                <DropdownMenuItem
                  key={v.id}
                  onClick={() => setCurrentVersion(v.branch_name)}
                  data-testid={`version-${v.branch_name}`}
                >
                  <GitBranch className="w-4 h-4 mr-2" />
                  {v.version_name}
                  {v.is_default ? (
                    <Badge variant="outline" className="ml-2 text-xs">
                      default
                    </Badge>
                  ) : null}
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setNewVersionDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                New Version
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Render Button */}
          <Button
            variant="outline"
            onClick={() => setRenderDialog(true)}
            className="font-mono"
            data-testid="render-btn"
          >
            <Play className="w-4 h-4 mr-2" />
            Render
          </Button>

          {/* Save Button */}
          <Button
            onClick={handleSaveSection}
            disabled={!hasChanges || saving}
            className="font-mono uppercase tracking-wider"
            data-testid="save-btn"
          >
            <Save className="w-4 h-4 mr-2" />
            {saving ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>

      {/* Editor Layout */}
      <div className="editor-layout">
        {/* Sections Sidebar */}
        <div className="section-sidebar">
          <div className="p-4 border-b border-border flex items-center justify-between">
            <span className="font-mono text-sm text-muted-foreground uppercase tracking-wider">
              Sections
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setNewSectionDialog(true)}
              data-testid="add-section-btn"
            >
              <Plus className="w-4 h-4" />
            </Button>
          </div>

          <ScrollArea className="flex-1">
            <div className="p-2 space-y-1">
              {sections.length === 0 ? (
                <div className="p-4 text-center text-sm text-muted-foreground">
                  No sections yet. Add one to get started.
                </div>
              ) : (
                sections.map((section, index) => (
                  <div
                    key={section.filename}
                    className={`section-item flex items-center gap-2 p-3 rounded-sm cursor-pointer border-l-2 border-transparent ${
                      selectedSection?.filename === section.filename
                        ? "active"
                        : ""
                    }`}
                    onClick={() => loadSectionContent(section)}
                    data-testid={`section-${section.filename}`}
                  >
                    <GripVertical className="w-4 h-4 text-muted-foreground cursor-grab" />
                    <FileText className="w-4 h-4 text-muted-foreground" />
                    <span className="flex-1 font-mono text-sm truncate">
                      {section.name}
                    </span>
                    <Badge variant="outline" className="text-xs font-mono">
                      {String(section.order).padStart(2, "0")}
                    </Badge>
                  </div>
                ))
              )}
            </div>
          </ScrollArea>
        </div>

        {/* Editor Main */}
        <div className="editor-main">
          {selectedSection ? (
            <>
              <div className="editor-toolbar">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm">
                    {selectedSection.filename}
                  </span>
                  {hasChanges && (
                    <Badge variant="outline" className="text-xs bg-accent/10 text-accent border-accent/20">
                      Unsaved
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {variables.length > 0 && (
                    <div className="flex items-center gap-1 mr-2">
                      <span className="text-xs text-muted-foreground font-mono">
                        Variables:
                      </span>
                      {variables.slice(0, 3).map((v) => (
                        <Badge key={v} variant="secondary" className="text-xs font-mono">
                          {`{{${v}}}`}
                        </Badge>
                      ))}
                      {variables.length > 3 && (
                        <Badge variant="secondary" className="text-xs font-mono">
                          +{variables.length - 3}
                        </Badge>
                      )}
                    </div>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleteDialog(true)}
                    className="text-destructive hover:text-destructive"
                    data-testid="delete-section-btn"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              <div className="editor-content">
                <textarea
                  value={sectionContent}
                  onChange={(e) => {
                    setSectionContent(e.target.value);
                    setVariables(extractVariablesFromContent(e.target.value));
                  }}
                  className="code-editor"
                  placeholder="Write your prompt section content here..."
                  data-testid="section-editor"
                />
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <FileText className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
                <p className="text-muted-foreground font-mono">
                  Select a section to edit
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* New Section Dialog */}
      <Dialog open={newSectionDialog} onOpenChange={setNewSectionDialog}>
        <DialogContent data-testid="new-section-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">Add Section</DialogTitle>
            <DialogDescription>
              Create a new section for your prompt.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="sectionName" className="font-mono text-sm">
                SECTION NAME
              </Label>
              <Input
                id="sectionName"
                placeholder="e.g., instructions"
                value={newSection.name}
                onChange={(e) =>
                  setNewSection((prev) => ({ ...prev, name: e.target.value }))
                }
                className="font-mono"
                data-testid="section-name-input"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="sectionTitle" className="font-mono text-sm">
                TITLE (Optional)
              </Label>
              <Input
                id="sectionTitle"
                placeholder="e.g., Instructions"
                value={newSection.title}
                onChange={(e) =>
                  setNewSection((prev) => ({ ...prev, title: e.target.value }))
                }
                className="font-mono"
                data-testid="section-title-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setNewSectionDialog(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateSection}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-add-section-btn"
            >
              Add Section
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Version Dialog */}
      <Dialog open={newVersionDialog} onOpenChange={setNewVersionDialog}>
        <DialogContent data-testid="new-version-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">Create Version</DialogTitle>
            <DialogDescription>
              Create a new version based on "{currentVersion}".
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="versionName" className="font-mono text-sm">
                VERSION NAME
              </Label>
              <Input
                id="versionName"
                placeholder="e.g., v2"
                value={newVersion.version_name}
                onChange={(e) =>
                  setNewVersion((prev) => ({ ...prev, version_name: e.target.value }))
                }
                className="font-mono"
                data-testid="version-name-input"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setNewVersionDialog(false)}
              className="font-mono"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateVersion}
              className="font-mono uppercase tracking-wider"
              data-testid="confirm-create-version-btn"
            >
              Create Version
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Render Dialog */}
      <Dialog open={renderDialog} onOpenChange={setRenderDialog}>
        <DialogContent className="sm:max-w-2xl" data-testid="render-dialog">
          <DialogHeader>
            <DialogTitle className="font-mono">Render Prompt</DialogTitle>
            <DialogDescription>
              Provide variable values to compile your prompt.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            {/* Variables Input */}
            {getAllVariables().length > 0 && (
              <div className="space-y-3">
                <Label className="font-mono text-sm">VARIABLES</Label>
                <div className="grid gap-3">
                  {getAllVariables().map((varName) => (
                    <div key={varName} className="flex items-center gap-3">
                      <Label className="font-mono text-sm w-32 text-right text-muted-foreground">
                        {`{{${varName}}}`}
                      </Label>
                      <Input
                        placeholder={`Value for ${varName}`}
                        value={renderVariables[varName] || ""}
                        onChange={(e) =>
                          setRenderVariables((prev) => ({
                            ...prev,
                            [varName]: e.target.value,
                          }))
                        }
                        className="font-mono flex-1"
                        data-testid={`render-var-${varName}`}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <Button
              onClick={handleRenderPrompt}
              className="w-full font-mono uppercase tracking-wider"
              data-testid="execute-render-btn"
            >
              <Play className="w-4 h-4 mr-2" />
              Render Prompt
            </Button>

            {/* Error */}
            {renderError && (
              <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-sm">
                <div className="flex items-center gap-2 text-destructive mb-2">
                  <AlertCircle className="w-4 h-4" />
                  <span className="font-mono text-sm">{renderError.message}</span>
                </div>
                {renderError.missing && (
                  <div className="flex flex-wrap gap-2">
                    {renderError.missing.map((v) => (
                      <Badge key={v} variant="destructive" className="font-mono">
                        {`{{${v}}}`}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Result */}
            {renderResult && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label className="font-mono text-sm">COMPILED PROMPT</Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCopyRendered}
                    className="font-mono"
                    data-testid="copy-rendered-btn"
                  >
                    {copied ? (
                      <Check className="w-4 h-4 mr-1" />
                    ) : (
                      <Copy className="w-4 h-4 mr-1" />
                    )}
                    {copied ? "Copied!" : "Copy"}
                  </Button>
                </div>
                <ScrollArea className="h-64 rounded-sm border border-border">
                  <pre className="p-4 text-sm font-mono whitespace-pre-wrap">
                    {renderResult.compiled_prompt}
                  </pre>
                </ScrollArea>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>Sections used:</span>
                  {renderResult.sections_used?.map((s) => (
                    <Badge key={s} variant="outline" className="font-mono text-xs">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Section Dialog */}
      <AlertDialog open={deleteDialog} onOpenChange={setDeleteDialog}>
        <AlertDialogContent data-testid="delete-section-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-mono">Delete Section</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{selectedSection?.name}"? This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="font-mono">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteSection}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-mono uppercase tracking-wider"
              data-testid="confirm-delete-section-btn"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
