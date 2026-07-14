"""Bounded, read-only production observability tools backed by easypanel-api."""

from typing import Any, Literal, Optional
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from src.client import EasyPanelClient


def register_tools(mcp: FastMCP, client: EasyPanelClient) -> None:
    readonly = ToolAnnotations(readOnlyHint=True)

    @mcp.tool(name="observability_health", annotations=readonly)
    async def observability_health() -> dict[str, Any]:
        """Check whether the Docker-level observability bridge and socket are available."""
        return {"success": True, "data": await client.observability_availability()}

    @mcp.tool(name="get_observability_alerts", annotations=readonly)
    async def get_observability_alerts(
        memory_percent: float = 85, growth_mb_per_hour: float = 100, minutes: int = 60,
    ) -> dict[str, Any]:
        """List current memory-limit, sustained-growth, process-count, and stats-availability alerts."""
        memory_percent = max(1, min(100, memory_percent))
        growth_mb_per_hour = max(1, min(10240, growth_mb_per_hour))
        minutes = max(5, min(1440, minutes))
        return {"success": True, "data": await client.get_observability_alerts(
            memory_percent, growth_mb_per_hour, minutes,
        )}

    @mcp.tool(name="list_runtime_services", annotations=readonly)
    async def list_runtime_services(include_stopped: bool = True, name: Optional[str] = None) -> dict[str, Any]:
        """List Docker containers with EasyPanel project/service labels and runtime state."""
        return {"success": True, "data": await client.list_runtime_services(include_stopped, name)}

    @mcp.tool(name="get_host_runtime_stats", annotations=readonly)
    async def get_host_runtime_stats() -> dict[str, Any]:
        """Get bounded Docker-host capacity and container counts."""
        return {"success": True, "data": await client.get_host_runtime_stats()}

    @mcp.tool(name="get_service_runtime_stats", annotations=readonly)
    async def get_service_runtime_stats(container_id: str) -> dict[str, Any]:
        """Get working set, file cache, CPU, PIDs, network, and block I/O for one container."""
        return {"success": True, "data": await client.get_service_runtime_stats(container_id)}

    @mcp.tool(name="get_service_processes", annotations=readonly)
    async def get_service_processes(container_id: str) -> dict[str, Any]:
        """List at most 100 processes in a container, ordered by resident memory."""
        return {"success": True, "data": await client.get_service_processes(container_id)}

    @mcp.tool(name="get_service_health_details", annotations=readonly)
    async def get_service_health_details(container_id: str) -> dict[str, Any]:
        """Get state, health checks, restarts, OOM status, and configured resource limits."""
        return {"success": True, "data": await client.get_service_health_details(container_id)}

    @mcp.tool(name="get_service_logs_bounded", annotations=readonly)
    async def get_service_logs_bounded(
        container_id: str, tail: int = 300, since_seconds: int = 1800,
        severity: Literal["all", "error", "warning", "info"] = "all",
    ) -> dict[str, Any]:
        """Get secret-redacted logs, limited to 2,000 lines and a seven-day window."""
        tail = max(1, min(2000, tail)); since_seconds = max(0, min(604800, since_seconds))
        return {"success": True, "data": await client.get_service_logs_bounded(container_id, tail, since_seconds, severity)}

    @mcp.tool(name="get_memory_trend", annotations=readonly)
    async def get_memory_trend(container_id: str, minutes: int = 60) -> dict[str, Any]:
        """Get sampled working-set history and memory growth per minute/hour."""
        return {"success": True, "data": await client.get_memory_trend(container_id, max(1, min(1440, minutes)))}

    @mcp.tool(name="diagnose_memory_bloat", annotations=readonly)
    async def diagnose_memory_bloat(container_id: str, minutes: int = 60) -> dict[str, Any]:
        """Classify process working set versus file cache and flag sustained growth or limit pressure."""
        return {"success": True, "data": await client.diagnose_memory_bloat(container_id, max(1, min(1440, minutes)))}

    @mcp.tool(name="get_postgres_diagnostics", annotations=readonly)
    async def get_postgres_diagnostics(container_id: str, database: str = "memory", user: str = "postgres") -> dict[str, Any]:
        """Get PostgreSQL size, connections, active-query, cache-hit, table-size, and vacuum statistics."""
        return {"success": True, "data": await client.get_postgres_diagnostics(container_id, database, user)}

    @mcp.tool(name="get_redis_diagnostics", annotations=readonly)
    async def get_redis_diagnostics(container_id: str) -> dict[str, Any]:
        """Get Redis memory allocator, limits, fragmentation, persistence, and keyspace information."""
        return {"success": True, "data": await client.get_redis_diagnostics(container_id)}

    @mcp.tool(name="get_queue_diagnostics", annotations=readonly)
    async def get_queue_diagnostics(container_id: str, queue_names: list[str]) -> dict[str, Any]:
        """Get bounded BullMQ state counts for up to 20 explicitly named queues without scanning Redis."""
        if not queue_names or len(queue_names) > 20:
            raise ValueError("Provide between 1 and 20 queue names")
        return {"success": True, "data": await client.get_redis_diagnostics(container_id, queue_names)}
