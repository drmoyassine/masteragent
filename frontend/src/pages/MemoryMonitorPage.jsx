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
  Users,
  FileText,
  GraduationCap,
  Clock,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

export default function MemoryMonitorPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [agentStats, setAgentStats] = useState([]);

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
                      <Badge variant="outline">{(agent.id || agent.agent_id || '').slice(0, 8)}...</Badge>
                      <span className="text-sm text-muted-foreground">
                        {agent.interaction_count} total interactions
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
