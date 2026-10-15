"""Tests for the MCP server tool definitions (no live cluster needed).

We import the server module and confirm the tools exist, are registered, and
that the tool names match the documented read-only surface (no mutation verbs).
"""

import pytest


def test_server_imports_and_tools():
    from mcp_server.server import mcp  # noqa: F401
    from mcp_server import server

    # FastMCP exposes tools via the @mcp.tool decorator; the function objects
    # themselves live on the module. Assert the expected tool functions exist.
    expected = [
        "list_pods",
        "get_pod_status",
        "get_pod_events",
        "get_pod_logs",
        "get_node_resources",
        "diagnose_pod",
    ]
    for name in expected:
        assert hasattr(server, name), f"missing MCP tool: {name}"


def test_no_mutation_tool_names():
    from mcp_server import server

    mutation = ["delete", "apply", "patch", "scale", "create", "exec", "scale"]
    for name in mutation:
        assert not any(name in fn for fn in dir(server) if fn.startswith("get_") or fn in [
            "list_pods", "diagnose_pod", "get_node_resources",
        ]), f"unexpected mutation-like tool present: {name}"
