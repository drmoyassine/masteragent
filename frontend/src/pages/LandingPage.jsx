import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { 
    Github, 
    FileText, 
    GitBranch, 
    Zap, 
    Code, 
    Check,
    ArrowRight,
    Terminal,
    Layers,
    Shield,
    Brain,
    Search,
    Database,
    Users,
    Activity,
    Lock,
    MessageSquare,
    GraduationCap,
    Cpu
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";

export default function LandingPage() {
    const navigate = useNavigate();
    const { isAuthenticated } = useAuth();

    const promptFeatures = [
        {
            icon: FileText,
            title: "Multi-file Markdown",
            description: "Structure complex prompts as ordered Markdown sections"
        },
        {
            icon: GitBranch,
            title: "Git-backed Versioning",
            description: "Every version maps to a GitHub branch for full history"
        },
        {
            icon: Zap,
            title: "Variable Injection",
            description: "Mustache-style placeholders with runtime injection"
        },
        {
            icon: Terminal,
            title: "Clean Render API",
            description: "Consume compiled prompts via simple HTTP endpoints"
        },
        {
            icon: Layers,
            title: "Starter Templates",
            description: "Agent Persona, Task Executor, Knowledge Expert & more"
        },
        {
            icon: Shield,
            title: "API Key Auth",
            description: "Secure access to render endpoints for your agents"
        }
    ];

    const memoryFeatures = [
        {
            icon: Database,
            title: "Structured Memory Storage",
            description: "Store interactions with full metadata, entities, and documents"
        },
        {
            icon: Search,
            title: "Semantic Search",
            description: "Vector-powered search across all memories with filtering"
        },
        {
            icon: Users,
            title: "Entity Timelines",
            description: "Track interaction history for contacts, organizations, projects"
        },
        {
            icon: GraduationCap,
            title: "Curated Lessons",
            description: "Extract and organize knowledge from agent interactions"
        },
        {
            icon: Cpu,
            title: "GLiNER2 NER",
            description: "Automatic entity extraction using state-of-the-art NER"
        },
        {
            icon: Lock,
            title: "PII Scrubbing",
            description: "Separate private and shared memories with PII protection"
        }
    ];

    const pricingPlans = [
        {
            name: "Free",
            price: "$0",
            period: "forever",
            description: "Perfect for trying out",
            features: [
                "1 prompt",
                "Memory System access",
                "1 agent API key",
                "500 memories/month",
                "Community support"
            ],
            cta: "Get Started",
            popular: false
        },
        {
            name: "Pro",
            price: "$19",
            period: "/month",
            description: "For production AI agents",
            features: [
                "Unlimited prompts",
                "Unlimited memories",
                "10 agent API keys",
                "Full LLM integration",
                "OpenClaw sync",
                "Priority support",
                "Team collaboration (soon)"
            ],
            cta: "Upgrade to Pro",
            popular: true
        }
    ];

    return (
        <div className="min-h-screen bg-background" data-testid="landing-page">
            {/* Navigation */}
            <nav className="border-b border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-sm bg-primary flex items-center justify-center">
                                <Brain className="w-4 h-4 text-primary-foreground" />
                            </div>
                            <span className="font-mono font-bold text-lg tracking-tight">
                                PROMPTSRC
                            </span>
                        </div>
                        <div className="flex items-center gap-4">
                            {isAuthenticated ? (
                                <Button
                                    onClick={() => navigate('/app')}
                                    className="font-mono uppercase tracking-wider"
                                    data-testid="go-to-app-btn"
                                >
                                    Go to App
                                    <ArrowRight className="w-4 h-4 ml-2" />
                                </Button>
                            ) : (
                                <>
                                    <Button
                                        variant="ghost"
                                        onClick={() => navigate('/auth')}
                                        className="font-mono"
                                        data-testid="sign-in-btn"
                                    >
                                        Sign In
                                    </Button>
                                    <Button
                                        onClick={() => navigate('/auth')}
                                        className="font-mono uppercase tracking-wider"
                                        data-testid="get-started-btn"
                                    >
                                        Get Started
                                    </Button>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </nav>

            {/* Hero Section */}
            <section className="relative overflow-hidden">
                <div className="absolute inset-0 grid-texture opacity-50" />
                <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 lg:py-32">
                    <div className="max-w-3xl">
                        <Badge variant="outline" className="mb-6 font-mono text-xs uppercase tracking-widest border-primary/30 text-primary">
                            Prompt + Memory System for AI Agents
                        </Badge>
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-mono font-bold tracking-tight mb-6">
                            Give your AI agents
                            <span className="text-primary"> memory & prompts</span>
                        </h1>
                        <p className="text-lg text-muted-foreground mb-8 max-w-2xl leading-relaxed">
                            The complete infrastructure for AI agents: version-controlled prompts stored in GitHub, 
                            plus a powerful memory system with semantic search, entity tracking, and automated lesson extraction.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-4">
                            <Button
                                size="lg"
                                onClick={() => navigate('/auth')}
                                className="font-mono uppercase tracking-wider"
                                data-testid="hero-sign-up-btn"
                            >
                                Start Free
                                <ArrowRight className="w-5 h-5 ml-2" />
                            </Button>
                            <Button
                                size="lg"
                                variant="outline"
                                onClick={() => document.getElementById('memory')?.scrollIntoView({ behavior: 'smooth' })}
                                className="font-mono uppercase tracking-wider"
                            >
                                Explore Memory System
                            </Button>
                        </div>
                    </div>

                    {/* Code Preview */}
                    <div className="mt-16 lg:mt-20">
                        <div className="bg-card border border-border rounded-sm overflow-hidden shadow-xl">
                            <div className="flex items-center gap-2 px-4 py-3 bg-secondary/50 border-b border-border">
                                <div className="w-3 h-3 rounded-full bg-destructive/50" />
                                <div className="w-3 h-3 rounded-full bg-accent/50" />
                                <div className="w-3 h-3 rounded-full bg-primary/50" />
                                <span className="ml-2 font-mono text-xs text-muted-foreground">
                                    agent_integration.py
                                </span>
                            </div>
                            <pre className="p-6 text-sm font-mono overflow-x-auto">
<code className="text-muted-foreground">{`# 1. Get your prompt
`}<span className="text-primary">prompt</span>{` = requests.post(
    "/api/prompts/{id}/main/render",
    headers={"X-API-Key": "`}<span className="text-accent">pm_xxx</span>{`"},
    json={"variables": {"company": "Acme"}}
).json()

# 2. Store agent interactions
`}<span className="text-primary">memory</span>{` = requests.post(
    "/api/memory/interactions",
    headers={"X-API-Key": "`}<span className="text-accent">mem_xxx</span>{`"},
    data={
        "text": "Meeting with John from Acme Corp...",
        "channel": "meeting",
        "entities": '[{"type": "Contact", "name": "John"}]'
    }
)

# 3. Search past memories
`}<span className="text-primary">results</span>{` = requests.post(
    "/api/memory/search",
    json={"query": "Acme partnership discussions"}
)`}</code>
                            </pre>
                        </div>
                    </div>
                </div>
            </section>

            {/* Prompt Manager Features */}
            <section id="prompts" className="py-24 border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <Badge variant="outline" className="mb-4 font-mono text-xs uppercase tracking-widest">
                            Module 1
                        </Badge>
                        <h2 className="text-3xl font-mono font-bold tracking-tight mb-4">
                            Prompt Manager
                        </h2>
                        <p className="text-muted-foreground max-w-2xl mx-auto">
                            Version-controlled prompts as code. Build complex, multi-section prompts stored in GitHub,
                            consumable via clean HTTP API.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {promptFeatures.map((feature, index) => (
                            <div
                                key={index}
                                className="p-6 border border-border rounded-sm hover:border-primary/30 transition-colors group"
                            >
                                <div className="w-10 h-10 rounded-sm bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                                    <feature.icon className="w-5 h-5 text-primary" />
                                </div>
                                <h3 className="font-mono font-semibold mb-2">{feature.title}</h3>
                                <p className="text-sm text-muted-foreground">{feature.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Memory System Features */}
            <section id="memory" className="py-24 border-t border-border bg-secondary/20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <Badge variant="outline" className="mb-4 font-mono text-xs uppercase tracking-widest border-accent/50 text-accent">
                            Module 2
                        </Badge>
                        <h2 className="text-3xl font-mono font-bold tracking-tight mb-4">
                            Agent Memory System
                        </h2>
                        <p className="text-muted-foreground max-w-2xl mx-auto">
                            Give your AI agents persistent memory. Store interactions, extract entities, 
                            search semantically, and mine lessons automatically.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {memoryFeatures.map((feature, index) => (
                            <div
                                key={index}
                                className="p-6 border border-border rounded-sm bg-card hover:border-accent/30 transition-colors group"
                            >
                                <div className="w-10 h-10 rounded-sm bg-accent/10 flex items-center justify-center mb-4 group-hover:bg-accent/20 transition-colors">
                                    <feature.icon className="w-5 h-5 text-accent" />
                                </div>
                                <h3 className="font-mono font-semibold mb-2">{feature.title}</h3>
                                <p className="text-sm text-muted-foreground">{feature.description}</p>
                            </div>
                        ))}
                    </div>

                    {/* Memory System Architecture */}
                    <div className="mt-16 p-8 border border-border rounded-sm bg-card">
                        <h3 className="font-mono font-semibold text-lg mb-6 text-center">How It Works</h3>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 text-center">
                            <div className="space-y-2">
                                <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center mx-auto">
                                    <span className="font-mono font-bold text-primary">1</span>
                                </div>
                                <h4 className="font-mono font-medium">Ingest</h4>
                                <p className="text-xs text-muted-foreground">Agent pushes interactions via API</p>
                            </div>
                            <div className="space-y-2">
                                <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center mx-auto">
                                    <span className="font-mono font-bold text-primary">2</span>
                                </div>
                                <h4 className="font-mono font-medium">Process</h4>
                                <p className="text-xs text-muted-foreground">Extract entities, embed, summarize</p>
                            </div>
                            <div className="space-y-2">
                                <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center mx-auto">
                                    <span className="font-mono font-bold text-primary">3</span>
                                </div>
                                <h4 className="font-mono font-medium">Store</h4>
                                <p className="text-xs text-muted-foreground">Vector DB + relational metadata</p>
                            </div>
                            <div className="space-y-2">
                                <div className="w-12 h-12 rounded-full bg-primary/20 flex items-center justify-center mx-auto">
                                    <span className="font-mono font-bold text-primary">4</span>
                                </div>
                                <h4 className="font-mono font-medium">Retrieve</h4>
                                <p className="text-xs text-muted-foreground">Semantic search, timelines, lessons</p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Tech Stack */}
            <section className="py-16 border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-8">
                        <h3 className="font-mono font-semibold text-lg mb-2">Built With</h3>
                    </div>
                    <div className="flex flex-wrap justify-center gap-4 text-sm text-muted-foreground">
                        <Badge variant="outline" className="font-mono">FastAPI</Badge>
                        <Badge variant="outline" className="font-mono">React</Badge>
                        <Badge variant="outline" className="font-mono">Qdrant</Badge>
                        <Badge variant="outline" className="font-mono">GLiNER2</Badge>
                        <Badge variant="outline" className="font-mono">PostgreSQL</Badge>
                        <Badge variant="outline" className="font-mono">Docker</Badge>
                        <Badge variant="outline" className="font-mono">Tailwind CSS</Badge>
                    </div>
                </div>
            </section>

            {/* Pricing Section */}
            <section id="pricing" className="py-24 border-t border-border bg-secondary/20">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="text-center mb-16">
                        <h2 className="text-3xl font-mono font-bold tracking-tight mb-4">
                            Simple, transparent pricing
                        </h2>
                        <p className="text-muted-foreground max-w-2xl mx-auto">
                            Start free with both Prompt Manager and Memory System. Upgrade when you need more.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 max-w-4xl mx-auto">
                        {pricingPlans.map((plan, index) => (
                            <div
                                key={index}
                                className={`relative p-8 border rounded-sm ${
                                    plan.popular 
                                        ? 'border-primary bg-card' 
                                        : 'border-border bg-card'
                                }`}
                                data-testid={`pricing-${plan.name.toLowerCase()}`}
                            >
                                {plan.popular && (
                                    <Badge className="absolute -top-3 left-1/2 -translate-x-1/2 font-mono text-xs uppercase">
                                        Most Popular
                                    </Badge>
                                )}
                                <div className="mb-6">
                                    <h3 className="font-mono font-semibold text-xl mb-2">{plan.name}</h3>
                                    <div className="flex items-baseline gap-1">
                                        <span className="text-4xl font-mono font-bold">{plan.price}</span>
                                        <span className="text-muted-foreground">{plan.period}</span>
                                    </div>
                                    <p className="text-sm text-muted-foreground mt-2">{plan.description}</p>
                                </div>

                                <ul className="space-y-3 mb-8">
                                    {plan.features.map((feature, i) => (
                                        <li key={i} className="flex items-center gap-2 text-sm">
                                            <Check className="w-4 h-4 text-primary flex-shrink-0" />
                                            <span>{feature}</span>
                                        </li>
                                    ))}
                                </ul>

                                <Button
                                    onClick={() => navigate('/auth')}
                                    variant={plan.popular ? "default" : "outline"}
                                    className="w-full font-mono uppercase tracking-wider"
                                    data-testid={`pricing-${plan.name.toLowerCase()}-btn`}
                                >
                                    {plan.cta}
                                </Button>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-24 border-t border-border">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
                    <h2 className="text-3xl font-mono font-bold tracking-tight mb-4">
                        Ready to supercharge your AI agents?
                    </h2>
                    <p className="text-muted-foreground mb-8 max-w-2xl mx-auto">
                        Join teams using PromptSRC to manage prompts and give their agents persistent memory.
                    </p>
                    <Button
                        size="lg"
                        onClick={() => navigate('/auth')}
                        className="font-mono uppercase tracking-wider"
                        data-testid="cta-sign-up-btn"
                    >
                        Get Started Free
                        <ArrowRight className="w-5 h-5 ml-2" />
                    </Button>
                </div>
            </section>

            {/* Footer */}
            <footer className="border-t border-border py-12">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                        <div className="flex items-center gap-3">
                            <div className="w-6 h-6 rounded-sm bg-primary flex items-center justify-center">
                                <Brain className="w-3 h-3 text-primary-foreground" />
                            </div>
                            <span className="font-mono text-sm text-muted-foreground">
                                PROMPTSRC © 2026
                            </span>
                        </div>
                        <div className="flex items-center gap-6 text-sm text-muted-foreground">
                            <a href="#" className="hover:text-foreground transition-colors">Documentation</a>
                            <a href="#" className="hover:text-foreground transition-colors">GitHub</a>
                            <a href="#" className="hover:text-foreground transition-colors">API Reference</a>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}
