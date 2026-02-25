import { useState, useEffect } from "react";
import { toast } from "sonner";
import { format } from "date-fns";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Activity,
  Database,
  Brain,
  Users,
  FileText,
  GraduationCap,
  Clock,
  RefreshCw,
  Play,
  Zap,
  TrendingUp,
} from "lucide-react";

export default function MemoryMonitorPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [agentStats, setAgentStats] = useState([]);
  const [syncRunning, setSyncRunning] = useState(false);
  const [miningRunning, setMiningRunning] = useState(false);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setLoading(true);
    try {
      const [statsRes, agentsRes] = await Promise.all([
        api.get("/memory/admin/stats"),
        api.get("/memory/admin/stats/agents"),
      ]);
      setStats(statsRes.data);
      setAgentStats(agentsRes.data.agents || []);
    } catch (error) {
      toast.error("Failed to load stats");
    } finally {
      setLoading(false);
    }
  };

  const triggerSync = async () => {
    setSyncRunning(true);
    try {
      const res = await api.post("/memory/admin/sync/openclaw");
      if (res.data.status === "success") {
        toast.success(`Sync complete: ${res.data.memories_synced} days, ${res.data.lessons_synced} lessons`);
      } else if (res.data.status === "disabled") {
        toast.info("OpenClaw sync is disabled in settings");
      } else {
        toast.error(res.data.message || "Sync failed");
      }
    } catch (error) {
      toast.error("Sync failed");
    } finally {
      setSyncRunning(false);
    }
  };

  const triggerMining = async () => {
    setMiningRunning(true);
    try {
      const res = await api.post("/memory/admin/tasks/mine-lessons");
      if (res.data.status === "success") {
        toast.success(`Mining complete: ${res.data.lessons_created} lessons created`);
      } else if (res.data.status === "disabled") {
        toast.info("Auto lesson mining is disabled in settings");
      } else {
        toast.error(res.data.message || "Mining failed");
      }
    } catch (error) {
      toast.error("Mining failed");
    } finally {
      setMiningRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-muted-foreground font-mono text-sm">LOADING STATS...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="memory-monitor-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">System Monitor</h1>
          <p className="text-muted-foreground">Memory system stats and background tasks</p>
        </div>
        <Button variant="outline" onClick={loadStats}>
          <RefreshCw className="w-4 h-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Stats Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Memories</CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_memories || 0}</div>
            <p className="text-xs text-muted-foreground">
              +{stats?.memories_24h || 0} in last 24h
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Documents</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_documents || 0}</div>
            <p className="text-xs text-muted-foreground">Parsed attachments</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Lessons</CardTitle>
            <GraduationCap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_lessons || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.draft_lessons || 0} pending approval
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Agents</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.active_agents || 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.actions_24h || 0} actions today
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Background Tasks */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="w-5 h-5" />
              OpenClaw Sync
            </CardTitle>
            <CardDescription>Export memories and lessons to Markdown format</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Sync your memories and lessons to a local or Git repository in OpenClaw-compatible Markdown format.
            </p>
            <Button onClick={triggerSync} disabled={syncRunning}>
              {syncRunning ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Syncing...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Run Sync Now
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Brain className="w-5 h-5" />
              Lesson Mining
            </CardTitle>
            <CardDescription>Auto-extract lessons from recent interactions</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Analyze interaction patterns and automatically create draft lessons for review.
            </p>
            <Button onClick={triggerMining} disabled={miningRunning}>
              {miningRunning ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Mining...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Run Mining Now
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Agent Activity */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5" />
            Agent Activity (Last 7 Days)
          </CardTitle>
          <CardDescription>API usage by registered agents</CardDescription>
        </CardHeader>
        <CardContent>
          {agentStats.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No agent activity recorded yet
            </p>
          ) : (
            <div className="space-y-4">
              {agentStats.map((agent) => (
                <div key={agent.agent_id} className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{agent.agent_id.slice(0, 8)}...</Badge>
                      <span className="text-sm text-muted-foreground">
                        {agent.active_days} active days
                      </span>
                    </div>
                    <span className="font-medium">{agent.total_actions} actions</span>
                  </div>
                  <Progress 
                    value={Math.min(100, (agent.total_actions / Math.max(...agentStats.map(a => a.total_actions))) * 100)} 
                    className="h-2" 
                  />
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
