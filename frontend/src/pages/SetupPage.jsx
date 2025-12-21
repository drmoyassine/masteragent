import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Github, ArrowRight, AlertCircle, CheckCircle2, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { saveSettings } from "@/lib/api";
import { toast } from "sonner";

export default function SetupPage({ onConfigured }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [formData, setFormData] = useState({
    github_token: "",
    github_owner: "",
    github_repo: "",
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await saveSettings(formData);
      toast.success("GitHub connected successfully!");
      onConfigured();
      navigate("/");
    } catch (err) {
      const message = err.response?.data?.detail || "Failed to connect to GitHub";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field) => (e) => {
    setFormData((prev) => ({ ...prev, [field]: e.target.value }));
  };

  return (
    <div className="min-h-screen bg-background grid-texture" data-testid="setup-page">
      <div className="setup-container animate-fade-in">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-sm bg-primary/10 border border-primary/20 mb-6">
            <Github className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-3xl font-mono font-bold tracking-tight mb-3">
            CONNECT GITHUB
          </h1>
          <p className="text-muted-foreground max-w-md mx-auto">
            Prompt Manager uses GitHub as the source of truth for your prompts. 
            Connect your repository to get started.
          </p>
        </div>

        {/* Setup Card */}
        <div className="setup-card">
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <Alert variant="destructive" className="bg-destructive/10 border-destructive/20">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="token" className="font-mono text-sm">
                  PERSONAL ACCESS TOKEN
                </Label>
                <Input
                  id="token"
                  type="password"
                  placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  value={formData.github_token}
                  onChange={handleChange("github_token")}
                  className="font-mono"
                  data-testid="github-token-input"
                  required
                />
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <ExternalLink className="w-3 h-3" />
                  <a 
                    href="https://github.com/settings/tokens/new?scopes=repo" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-primary hover:underline"
                  >
                    Generate a token
                  </a>
                  {" "}with repo scope
                </p>
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
                    data-testid="github-owner-input"
                    required
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
                    data-testid="github-repo-input"
                    required
                  />
                </div>
              </div>
            </div>

            <div className="pt-4">
              <Button
                type="submit"
                className="w-full font-mono uppercase tracking-wider"
                disabled={loading}
                data-testid="connect-github-btn"
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    CONNECTING...
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    CONNECT REPOSITORY
                    <ArrowRight className="w-4 h-4" />
                  </span>
                )}
              </Button>
            </div>
          </form>
        </div>

        {/* Info */}
        <div className="mt-8 p-4 border border-border rounded-sm bg-card/50">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-primary mt-0.5 flex-shrink-0" />
            <div className="text-sm text-muted-foreground space-y-2">
              <p className="font-medium text-foreground">What happens next?</p>
              <ul className="list-disc list-inside space-y-1 text-xs">
                <li>Your prompts will be stored in the connected repository</li>
                <li>Each prompt version maps to a GitHub branch</li>
                <li>Changes are committed automatically</li>
                <li>You maintain full Git history and control</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
