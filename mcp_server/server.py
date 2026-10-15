"""Read-only MCP server exposing Kubernetes diagnostic tools.

Tools (all read-only):
  - list_pods          : list pod names in a namespace
  - get_pod_status     : phase, conditions, container states
  - get_pod_events     : Kubernetes events for a pod
  - get_pod_logs       : recent logs (current or previous container)
  - get_node_resources : node allocatable/capacity/conditions
  - diagnose_pod       : collect full evidence and return a structured summary

The server is stdio-based (Model Context Protocol). It talks to Kubernetes only
through src.k8s_collector, which enforces read-only verbs and an expected-context
guard, so a client cannot make this server mutate a cluster.

Run:  python -m mcp_server.server
"""

from __future__ import annotations

import os

from mcp.server.mcpserver import MCPServer

from src import k8s_collector as collect

EXPECTED_CONTEXT = os.environ.get("AI_DEVOPS_KIND_CONTEXT", "kind-ai-devops-demo")

mcp = MCPServer("ai-devops-k8s-diagnostics")


@mcp.tool()
def list_pods(namespace: str) -> list[str]:
    """List pod names in a namespace (read-only)."""
    return collect.list_pod_names(namespace)


@mcp.tool()
def get_pod_status(namespace: str, pod_name: str) -> dict:
    """Return pod phase, conditions, and container states (read-only)."""
    return collect.get_pod_status(namespace, pod_name)


@mcp.tool()
def get_pod_events(namespace: str, pod_name: str) -> list[dict]:
    """Return Kubernetes events for a pod (read-only)."""
    return collect.get_pod_events(namespace, pod_name)


@mcp.tool()
def get_pod_logs(namespace: str, pod_name: str, container: str = "",
                 previous: bool = False) -> str:
    """Return recent logs for a container, current or previous (read-only)."""
    return collect.get_container_logs(namespace, pod_name, container, previous)


@mcp.tool()
def get_node_resources(node_name: str) -> dict:
    """Return node allocatable/capacity and conditions (read-only)."""
    return collect.get_node_resources(node_name)


@mcp.tool()
def diagnose_pod(namespace: str, pod_name: str) -> str:
    """Collect full read-only evidence for a pod and return a text summary."""
    try:
        ev = collect.collect_pod_evidence(namespace, pod_name, EXPECTED_CONTEXT)
    except collect.ContextGuardError as exc:
        return f"SAFETY GUARD: {exc}"
    lines = [
        f"Pod: {namespace}/{pod_name}",
        f"Phase: {ev.status.get('phase')}",
        f"Reason: {ev.status.get('reason')}",
        f"Events: {len(ev.events)}",
    ]
    return "\n".join(lines)


def main() -> None:
    import asyncio

    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
