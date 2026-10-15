#!/usr/bin/env python
"""Drive the MCP server with a local client and exercise the read-only tools.

This script starts `mcp_server/server.py` as a stdio subprocess, sends
MCP `tools/list` and a `tools/call` request, and prints the JSON-RPC responses.
It demonstrates that the MCP server works — not just that the file exists.

Requires a running kind cluster (see scripts/cluster_up.sh) and KUBECONFIG set.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SERVER_MODULE = "mcp_server.server"


def rpc(method: str, params: dict | None = None, id_: int = 1) -> dict:
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def main() -> int:
    env = dict(os.environ)
    env.setdefault("AI_DEVOPS_KIND_CONTEXT", "kind-ai-devops-demo")

    proc = subprocess.Popen(
        [sys.executable, "-m", SERVER_MODULE],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, env=env,
    )

    def send(obj: dict) -> dict:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    next_id = 1

    def send_rpc(method: str, params: dict | None = None) -> dict:
        nonlocal next_id
        msg = rpc(method, params, next_id)
        next_id += 1
        return send(msg)

    # 1. initialize
    init = send_rpc("initialize", {"protocolVersion": "2024-11-05",
                                   "capabilities": {}, "clientInfo": {"name": "demo", "version": "0"}})
    print(json.dumps(init, indent=2)[:600])

    # 2. list tools
    listed = send_rpc("tools/list")
    tools = listed.get("result", {}).get("tools", [])
    print("\n=== tools/list ===")
    for t in tools:
        print(f"  - {t.get('name')}")

    # 3. call one tool (list_pods) if cluster + kubeconfig available
    if "KUBECONFIG" in env:
        call = send_rpc("tools/call", {
            "name": "list_pods",
            "arguments": {"namespace": "ai-devops-ns"},
        })
        print("\n=== tools/call list_pods(ai-devops-ns) ===")
        print(json.dumps(call, indent=2)[:800])
    else:
        print("\n[skip] KUBECONFIG not set — skipping live tools/call")

    proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
