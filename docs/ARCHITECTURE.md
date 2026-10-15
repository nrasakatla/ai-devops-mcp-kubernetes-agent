# Architecture & Safety Model

## Overview

`ai-devops-mcp-kubernetes-agent` is a demonstration of an **Agentic DevOps**
troubleshooting loop. It has three cooperating components, all read-only with
respect to the Kubernetes cluster:

1. **Evidence collector** (`src/k8s_collector.py`) — the only code that calls
   `kubectl`. Wraps `get`/`list`/`describe`/`logs` behind a hard verb allowlist
   and a mutation denylist.
2. **Incident analyzer** (`src/incident_analyzer.py`) — turns raw evidence into
   a classification + hypothesis. Two backends: a local Ollama LLM and a
   deterministic rule engine.
3. **MCP server** (`mcp_server/server.py`) — exposes read-only diagnostic tools
   over the Model Context Protocol (stdio), so any MCP client (Claude Desktop,
   Cursor, a custom agent) can interrogate the cluster without write access.

## Data flow

```
                       ┌─────────────────────────────────────────────┐
                       │                  kind cluster                │
                       │        (ai-devops-demo, synthetic workloads) │
                       └──────────────────────┬──────────────────────┘
                                              │ kubectl (read-only)
                       ┌──────────────────────▼──────────────────────┐
                       │           src/k8s_collector.py              │
                       │  get/list/describe/logs  (+ verb guard,     │
                       │  context guard, mutation denylist)          │
                       └──────────────┬──────────────────┬───────────┘
                                      │ PodEvidence       │ tools
                          ┌───────────▼──────────┐   ┌────▼───────────────────┐
                          │ incident_analyzer.py │   │  mcp_server/server.py  │
                          │  Ollama | rule engine│   │  FastMCP (stdio)       │
                          └───────────┬──────────┘   └────┬───────────────────┘
                                      │ analysis          │ tools/list, tools/call
                          ┌───────────▼──────────┐        │
                          │       report.py      │        │  (MCP clients:
                          │  Markdown incident   │        │   Claude Desktop,
                          │  report (advisory)   │        │   Cursor, agents)
                          └──────────────────────┘        └─────────────────────┘
```

## Safety model

The project is **advisory by design**. Concrete controls:

| Control | Where | Effect |
|---|---|---|
| Verb allowlist | `k8s_collector._READ_ONLY_VERBS` | Only `get`/`list`/`describe`/`logs` may run |
| Mutation denylist | `k8s_collector._MUTATION_VERBS` | `apply`/`patch`/`delete`/`scale`/`exec`/etc. raise |
| Context guard | `k8s_collector.check_context` | Aborts unless active context == expected kind context |
| Isolated kubeconfig | `scripts/cluster_up.sh` | Writes its own kubeconfig, never touches `~/.kube/config` |
| No AWS / prod config | (absence) | No credentials, account IDs, private IPs, or internal names |

The LLM is only ever *given* evidence and asked to *explain* it. Its output is
written to a Markdown report as suggested remediation — it is never parsed back
into kubectl commands and executed. There is no code path from analysis output
to a cluster mutation.

## Why the context guard matters

A common failure in k8s tooling is accidentally running against the wrong
cluster. The guard compares `kubectl config current-context` to the expected
value and **refuses to proceed** on mismatch. Even if a user points `KUBECONFIG`
at a real cluster, the guard aborts with a loud `SAFETY` error rather than
running read-only diagnostics against infrastructure that wasn't intended.

## Design notes

- **Deterministic fallback**: the rule engine makes zero network calls and is
  fully unit-tested. This is the reliability floor — if Ollama is down, the
  report still gets produced with the same structure.
- **LLM classification map**: the Ollama backend returns JSON matching the same
  `IncidentAnalysis` schema as the rule engine, so callers are agnostic to which
  backend produced the result.
- **Read-only MCP surface**: the server exposes six tools, none of which map to
  a mutation verb. A client cannot express a write through this interface.
