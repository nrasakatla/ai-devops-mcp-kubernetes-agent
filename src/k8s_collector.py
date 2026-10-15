"""Read-only Kubernetes evidence collector.

This module contains the *only* code path that talks to a Kubernetes cluster.
Every command issued here is strictly read-only (`get` / `list` / `describe` /
`logs`). Mutation verbs are rejected explicitly, and an isolated-kubeconfig
guard aborts execution if the active context is not the expected local cluster.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any

# Verbs we will NEVER issue. If a caller (or an LLM prompt) ever asks for one of
# these, the collector raises instead of running it.
_MUTATION_VERBS = {
    "apply", "patch", "delete", "scale", "exec", "create", "edit",
    "replace", "run", "attach", "port-forward", "cp", "set", "annotate",
    "label", "taint", "cordon", "uncordon", "drain", "rollout", "top",
}

# The only verbs allowed to reach kubectl.
_READ_ONLY_VERBS = {"get", "list", "describe", "logs"}


class UnsafeKubectlVerb(ValueError):
    """Raised when a mutation verb is attempted."""


class ContextGuardError(RuntimeError):
    """Raised when the active kubeconfig context is not the expected cluster."""


@dataclass
class PodEvidence:
    """Structured evidence collected for a single pod failure."""

    namespace: str
    pod_name: str
    status: dict[str, Any] = field(default_factory=dict)
    describe: str = ""
    events: list[dict[str, str]] = field(default_factory=list)
    container_logs: dict[str, str] = field(default_factory=dict)
    previous_logs: dict[str, str] = field(default_factory=dict)
    deployment: dict[str, Any] = field(default_factory=dict)
    node_info: dict[str, Any] = field(default_factory=dict)


def _kubectl(args: list[str]) -> str:
    """Run a kubectl command with a read-only verb guard.

    `args` must begin with a verb. The verb is validated against the read-only
    allowlist and the mutation denylist before subprocess runs.
    """
    if not args:
        raise ValueError("kubectl args must not be empty")
    verb = args[0].split(".")[0]  # handle e.g. "get.pods" style if ever passed
    if verb not in _READ_ONLY_VERBS or verb in _MUTATION_VERBS:
        raise UnsafeKubectlVerb(
            f"refusing to run kubectl verb {verb!r}; read-only verbs are {sorted(_READ_ONLY_VERBS)}"
        )
    cmd = ["kubectl", *args, "-o", "json"]
    # Strip the -o json for describe/logs which don't produce json
    if verb in ("describe", "logs"):
        cmd = ["kubectl", *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment specific
        raise RuntimeError("kubectl not found on PATH") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"kubectl {' '.join(args)} failed: {proc.stderr.strip()}"
        )
    return proc.stdout


def check_context(expected_context: str) -> None:
    """Abort unless the active kubeconfig context matches the expected cluster."""
    out = _kubectl(["config", "current-context"]) if False else subprocess.run(
        ["kubectl", "config", "current-context"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    current = (out.stdout or "").strip()
    if current != expected_context:
        raise ContextGuardError(
            f"SAFETY: active context {current!r} != expected local context "
            f"{expected_context!r}. Refusing to proceed."
        )


def _json(args: list[str]) -> Any:
    return json.loads(_kubectl(args))


def list_pod_names(namespace: str) -> list[str]:
    """List pod names in a namespace (read-only `get pods`)."""
    data = _json(["get", "pods", "-n", namespace])
    return [item["metadata"]["name"] for item in data.get("items", [])]


def get_pod_status(namespace: str, pod_name: str) -> dict[str, Any]:
    """Return the pod's status sub-resource (phase, conditions, containers)."""
    pod = _json(["get", "pod", pod_name, "-n", namespace])
    status = pod.get("status", {})
    return {
        "phase": status.get("phase"),
        "conditions": status.get("conditions", []),
        "container_statuses": status.get("containerStatuses", []),
        "pod_ip": status.get("podIP"),
        "host_ip": status.get("hostIP"),
        "node_name": pod.get("spec", {}).get("nodeName"),
        "reason": status.get("reason"),
        "message": status.get("message"),
    }


def get_pod_describe(namespace: str, pod_name: str) -> str:
    """Return the `kubectl describe pod` output (events, state, etc.)."""
    return _kubectl(["describe", "pod", pod_name, "-n", namespace])


def get_node_resources(node_name: str) -> dict[str, Any]:
    """Return node allocatable/capacity and active conditions (read-only)."""
    node = _json(["get", "node", node_name])
    return {
        "name": node_name,
        "allocatable": node.get("status", {}).get("allocatable", {}),
        "capacity": node.get("status", {}).get("capacity", {}),
        "conditions": [
            c.get("type") for c in node.get("status", {}).get("conditions", [])
            if c.get("status") == "True"
        ],
    }


def get_pod_events(namespace: str, pod_name: str) -> list[dict[str, str]]:
    """Return Kubernetes events for a pod (sorted oldest-first)."""
    data = _json(["get", "events", "-n", namespace, "--field-selector",
                  f"involvedObject.name={pod_name}"])
    events = []
    for item in data.get("items", []):
        events.append({
            "type": item.get("type", ""),
            "reason": item.get("reason", ""),
            "message": item.get("message", ""),
            "count": str(item.get("count", "")),
            "last_seen": str(item.get("lastTimestamp", "")),
        })
    return events


def get_container_logs(namespace: str, pod_name: str, container: str = "",
                       previous: bool = False) -> str:
    """Return recent log lines for a container (current or previous instance)."""
    args = ["logs", pod_name, "-n", namespace, "--tail=200"]
    if container:
        args += ["-c", container]
    if previous:
        args += ["--previous"]
    try:
        return _kubectl(args)
    except RuntimeError:
        # Previous container may not exist (e.g. first crash), or pod pending.
        return ""


def collect_pod_evidence(namespace: str, pod_name: str,
                         expected_context: str) -> PodEvidence:
    """Collect all read-only evidence for a pod.

    Raises ContextGuardError if the active context is not the expected local
    cluster, ensuring we can never run this against a real/production cluster
    accidentally.
    """
    check_context(expected_context)
    ev = PodEvidence(namespace=namespace, pod_name=pod_name)
    ev.status = get_pod_status(namespace, pod_name)
    ev.describe = get_pod_describe(namespace, pod_name)
    ev.events = get_pod_events(namespace, pod_name)

    # Collect logs for every container/init-container known to the pod spec.
    conts: list[str] = []
    for cs in ev.status.get("container_statuses", []):
        conts.append(cs.get("name", ""))
    for name in {c for c in conts if c}:
        ev.container_logs[name] = get_container_logs(namespace, pod_name, name)
        ev.previous_logs[name] = get_container_logs(
            namespace, pod_name, name, previous=True
        )

    # Deployment config (limits, requests, replicas, image).
    dep_name = _owner_kind_name(namespace, pod_name)
    if dep_name:
        try:
            ev.deployment = _json(["get", "deployment", dep_name, "-n", namespace])
        except RuntimeError:
            ev.deployment = {}

    # Node resource info (allocatable / capacity).
    node_name = ev.status.get("node_name")
    if node_name:
        try:
            node = _json(["get", "node", node_name])
            ev.node_info = {
                "name": node_name,
                "allocatable": node.get("status", {}).get("allocatable", {}),
                "capacity": node.get("status", {}).get("capacity", {}),
                "conditions": [
                    c.get("type") for c in node.get("status", {}).get("conditions", [])
                    if c.get("status") == "True"
                ],
            }
        except RuntimeError:
            ev.node_info = {}
    return ev


def _owner_kind_name(namespace: str, pod_name: str) -> str | None:
    """Resolve the owning Deployment name from a pod's ownerReferences."""
    try:
        pod = _json(["get", "pod", pod_name, "-n", namespace])
    except RuntimeError:
        return None
    for owner in pod.get("metadata", {}).get("ownerReferences", []):
        if owner.get("kind") == "ReplicaSet":
            rs = _json(["get", "replicaset", owner["name"], "-n", namespace])
            for rs_owner in rs.get("metadata", {}).get("ownerReferences", []):
                if rs_owner.get("kind") == "Deployment":
                    return rs_owner["name"]
    return None
