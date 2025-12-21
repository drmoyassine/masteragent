import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { 
    Github, 
    FileText, 
    ArrowLeft,
    Mail,
    Lock,
    User,
    Eye,
    EyeOff,
    AlertCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/context/AuthContext";
import { signup, login, getGitHubLoginUrl } from "@/lib/api";
import { toast } from "sonner";

export default function AuthPage() {
    const navigate = useNavigate();
    const { login: authLogin } = useAuth();
    const [mode, setMode] = useState("login"); // "login" or "signup"
    const [loading, setLoading] = useState(false);
    const [githubLoading, setGithubLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState(null);
    
    const [formData, setFormData] = useState({
        email: "",
        password: "",
        username: "",
    });

    const handleChange = (field) => (e) => {
        setFormData((prev) => ({ ...prev, [field]: e.target.value }));
        setError(null);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            let response;
            if (mode === "signup") {
                if (!formData.username.trim()) {
                    setError("Username is required");
                    setLoading(false);
                    return;
                }
                response = await signup(formData);
            } else {
                response = await login({ email: formData.email, password: formData.password });
            }
            
            authLogin(response.data.token);
            toast.success(mode === "signup" ? "Account created successfully!" : "Welcome back!");
            navigate("/app");
        } catch (err) {
            const message = err.response?.data?.detail || "Authentication failed";
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    const handleGitHubLogin = async () => {
        setGithubLoading(true);
        try {
            const response = await getGitHubLoginUrl();
            window.location.href = response.data.auth_url;
        } catch (err) {
            const message = err.response?.data?.detail || "GitHub login unavailable";
            toast.error(message);
            setGithubLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-background grid-texture" data-testid="auth-page">
            <div className="max-w-md mx-auto px-4 py-12">
                {/* Back to Home */}
                <Button
                    variant="ghost"
                    onClick={() => navigate("/")}
                    className="mb-8 font-mono text-muted-foreground"
                    data-testid="back-to-home-btn"
                >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back to home
                </Button>

                {/* Header */}
                <div className="text-center mb-8">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-sm bg-primary mb-4">
                        <FileText className="w-6 h-6 text-primary-foreground" />
                    </div>
                    <h1 className="text-2xl font-mono font-bold tracking-tight mb-2">
                        {mode === "signup" ? "Create your account" : "Welcome back"}
                    </h1>
                    <p className="text-muted-foreground text-sm">
                        {mode === "signup" 
                            ? "Start managing your prompts like code" 
                            : "Sign in to continue to PromptSRC"
                        }
                    </p>
                </div>

                {/* Auth Card */}
                <div className="border border-border rounded-sm p-6 bg-card">
                    {/* GitHub OAuth */}
                    <Button
                        variant="outline"
                        onClick={handleGitHubLogin}
                        disabled={githubLoading}
                        className="w-full font-mono mb-6"
                        data-testid="github-auth-btn"
                    >
                        <Github className="w-4 h-4 mr-2" />
                        {githubLoading ? "Connecting..." : "Continue with GitHub"}
                    </Button>

                    <div className="relative mb-6">
                        <Separator />
                        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-3 text-xs text-muted-foreground font-mono uppercase">
                            or
                        </span>
                    </div>

                    {/* Email/Password Form */}
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {error && (
                            <Alert variant="destructive" className="bg-destructive/10 border-destructive/20">
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription>{error}</AlertDescription>
                            </Alert>
                        )}

                        {mode === "signup" && (
                            <div className="space-y-2">
                                <Label htmlFor="username" className="font-mono text-sm">
                                    USERNAME
                                </Label>
                                <div className="relative">
                                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                    <Input
                                        id="username"
                                        type="text"
                                        placeholder="johndoe"
                                        value={formData.username}
                                        onChange={handleChange("username")}
                                        className="pl-10 font-mono"
                                        data-testid="username-input"
                                        required={mode === "signup"}
                                    />
                                </div>
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="email" className="font-mono text-sm">
                                EMAIL
                            </Label>
                            <div className="relative">
                                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input
                                    id="email"
                                    type="email"
                                    placeholder="you@example.com"
                                    value={formData.email}
                                    onChange={handleChange("email")}
                                    className="pl-10 font-mono"
                                    data-testid="email-input"
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="password" className="font-mono text-sm">
                                PASSWORD
                            </Label>
                            <div className="relative">
                                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                                <Input
                                    id="password"
                                    type={showPassword ? "text" : "password"}
                                    placeholder="••••••••"
                                    value={formData.password}
                                    onChange={handleChange("password")}
                                    className="pl-10 pr-10 font-mono"
                                    data-testid="password-input"
                                    required
                                    minLength={6}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                                >
                                    {showPassword ? (
                                        <EyeOff className="w-4 h-4" />
                                    ) : (
                                        <Eye className="w-4 h-4" />
                                    )}
                                </button>
                            </div>
                        </div>

                        <Button
                            type="submit"
                            disabled={loading}
                            className="w-full font-mono uppercase tracking-wider"
                            data-testid="submit-auth-btn"
                        >
                            {loading 
                                ? (mode === "signup" ? "Creating account..." : "Signing in...") 
                                : (mode === "signup" ? "Create Account" : "Sign In")
                            }
                        </Button>
                    </form>

                    {/* Toggle Mode */}
                    <div className="mt-6 text-center text-sm">
                        {mode === "login" ? (
                            <p className="text-muted-foreground">
                                Don't have an account?{" "}
                                <button
                                    onClick={() => { setMode("signup"); setError(null); }}
                                    className="text-primary hover:underline font-mono"
                                    data-testid="switch-to-signup"
                                >
                                    Sign up
                                </button>
                            </p>
                        ) : (
                            <p className="text-muted-foreground">
                                Already have an account?{" "}
                                <button
                                    onClick={() => { setMode("login"); setError(null); }}
                                    className="text-primary hover:underline font-mono"
                                    data-testid="switch-to-login"
                                >
                                    Sign in
                                </button>
                            </p>
                        )}
                    </div>
                </div>

                {/* Terms */}
                <p className="mt-6 text-center text-xs text-muted-foreground">
                    By continuing, you agree to our Terms of Service and Privacy Policy.
                </p>
            </div>
        </div>
    );
}
