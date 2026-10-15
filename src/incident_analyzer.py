"""Incident analyzer: turns k8s evidence into a root-cause hypothesis.

Two backends:
  1. OllamaBackend  — real LLM-based analysis (local model, no paid API).
  2. RuleEngine     — deterministic fallback that works fully offline.

Both produce a common `IncidentAnalysis` structure consumed by `report.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .k8s_collector import PodEvidence

# Models we prefer, in order. Prefer genuinely-local (non-cloud) models.
PREFERRED_MODELS = [
    "qwen3.5:9b",
    "qwen3.5:4b",
    "qwen3:1.7b",
    "gemma3:4b-it-qat",
]

OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


class FailureClass(str, Enum):
    CRASHLOOP = "CrashLoopBackOff"
    OOMKILLED = "OOMKilled"
    PENDING = "Pending"
    UNKNOWN = "Unknown"


@dataclass
class IncidentAnalysis:
    failure_class: FailureClass
    root_cause: str
    evidence: list[str] = field(default_factory=list)
    remediation: list[str] = field(default_factory=list)
    confidence: str = "medium"
    source: str = "rule-engine"


def _available_ollama_models() -> list[str]:
    """Return local (non-cloud) Ollama model names, if Ollama is reachable."""
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "3", f"{OLLAMA_BASE}/api/tags"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    models = []
    for m in data.get("models", []):
        name = m.get("name", "")
        # Skip cloud-hosted models (":cloud" suffix) — we want purely local.
        if name.endswith(":cloud"):
            continue
        models.append(name)
    return models


def _is_ollama_reachable() -> bool:
    try:
        proc = subprocess.run(
            ["curl", "-s", "--max-time", "2", f"{OLLAMA_BASE}/api/tags"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _chat_completion(model: str, prompt: str) -> str:
    """Call Ollama's /api/chat with thinking disabled to get a clean answer.

    Some models (e.g. qwen3.5) are 'thinking' models that emit reasoning into
    a separate field and leave `message.content` empty. Setting `think: false`
    forces them to emit a direct answer in `message.content`.
    """
    import urllib.request

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 800},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode())
    msg = data.get("message", {})
    return msg.get("content", "")


class OllamaBackend:
    """Real LLM analysis via a local Ollama model."""

    def __init__(self, model: str | None = None):
        self.model = model or self._resolve_model()

    @staticmethod
    def _resolve_model() -> str | None:
        explicit = os.environ.get("AI_DEVOPS_OLLAMA_MODEL")
        if explicit:
            return explicit
        installed = _available_ollama_models()
        for pref in PREFERRED_MODELS:
            if pref in installed:
                return pref
        if installed:
            return installed[0]
        return None

    def analyze(self, evidence: PodEvidence) -> IncidentAnalysis:
        if not self.model or not _is_ollama_reachable():
            raise RuntimeError("Ollama unavailable")
        prompt = _build_prompt(evidence)
        raw = _chat_completion(self.model, prompt)
        if not raw.strip():
            raise RuntimeError("empty LLM response")
        return _parse_llm_output(raw, self.model)


def _build_prompt(ev: PodEvidence) -> str:
    status = json.dumps(ev.status, indent=2)
    events = json.dumps(ev.events, indent=2)
    nodes = json.dumps(ev.node_info, indent=2)
    return f"""You are a senior Kubernetes SRE diagnosing a failing pod.

Pod: {ev.namespace}/{ev.pod_name}

=== POD STATUS (json) ===
{status}

=== EVENTS ===
{events}

=== NODE INFO ===
{nodes}

Classify the failure as exactly one of: CrashLoopBackOff, OOMKilled, Pending, or Unknown.
Explain the suspected root cause and list the key evidence.
Recommend remediation steps.

Respond as JSON only, with this exact schema:
{{"failure_class": "...", "root_cause": "...", "evidence": ["..."], "remediation": ["..."], "confidence": "low|medium|high"}}
"""


def _parse_llm_output(raw: str, model: str) -> IncidentAnalysis:
    """Parse LLM output; tolerant of prose, markdown fences, and JSON.

    Returns an IncidentAnalysis. If the JSON cannot be decoded or the failure
    class is invalid, raises ValueError so callers can fall back to the rule
    engine rather than silently report 'Unknown'.
    """
    import re

    text = raw.strip()
    # Prefer a fenced JSON block if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        # Otherwise, find the first balanced {...} object.
        start = text.find("{")
        if start != -1:
            text = text[start:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {str(exc)[:200]}") from exc

    fc = FailureClass.UNKNOWN
    raw_fc = str(data.get("failure_class", "")).lower()
    for candidate in FailureClass:
        if candidate.value.lower() in raw_fc:
            fc = candidate
            break
    if fc == FailureClass.UNKNOWN:
        raise ValueError(f"LLM returned unrecognized failure_class: {raw_fc!r}")
    return IncidentAnalysis(
        failure_class=fc,
        root_cause=str(data.get("root_cause", "unknown")),
        evidence=[str(e) for e in data.get("evidence", [])],
        remediation=[str(r) for r in data.get("remediation", [])],
        confidence=str(data.get("confidence", "medium")),
        source=f"ollama/{model}",
    )


class RuleEngine:
    """Deterministic, offline analysis based on pod state, events and resources.

    This is intentionally transparent and testable: it looks only at plain
    evidence fields and never invents facts.
    """

    def analyze(self, evidence: PodEvidence) -> IncidentAnalysis:
        return self.analyze_from_text("", source="rule-engine", evidence=evidence)

    def analyze_from_text(self, raw: str, source: str,
                          evidence: PodEvidence | None = None) -> IncidentAnalysis:
        if evidence is not None:
            return self._analyze(evidence, source)
        return IncidentAnalysis(
            failure_class=FailureClass.UNKNOWN,
            root_cause="Unable to classify failure from available evidence.",
            source=source,
        )

    def _analyze(self, ev: PodEvidence, source: str) -> IncidentAnalysis:
        cs = ev.status.get("container_statuses", [])
        events_blob = " ".join(e.get("reason", "") + " " + e.get("message", "")
                               for e in ev.events).lower()

        # 1. OOMKilled detection — most specific signal first.
        for c in cs:
            state = c.get("state", {})
            term = state.get("terminated", {})
            if term.get("reason") == "OOMKilled" or "oomkilled" in events_blob:
                return self._oom(c, ev, source)

        # 2. Pending detection — pod not scheduled.
        if ev.status.get("phase") == "Pending" or "podschedul" in events_blob or \
           "unschedulable" in events_blob:
            return self._pending(ev, source)

        # 3. CrashLoopBackOff detection — restarts with nonzero exit.
        for c in cs:
            state = c.get("state", {})
            waiting = state.get("waiting", {})
            if waiting.get("reason") == "CrashLoopBackOff" or \
               "crashloopbackoff" in events_blob:
                return self._crashloop(c, ev, source)
            # Non-zero exit code implies a crash.
            term = state.get("terminated", {})
            if term.get("exitCode", 0) not in (0, None):
                return self._crashloop(c, ev, source)
        if "back-off" in events_blob or "backoff" in events_blob:
            return self._crashloop(cs[0] if cs else None, ev, source)

        return IncidentAnalysis(
            failure_class=FailureClass.UNKNOWN,
            root_cause="No recognized failure signature in pod status or events.",
            evidence=["Pod phase: " + str(ev.status.get("phase"))],
            remediation=["Gather additional evidence: deployment YAML, node conditions."],
            source=source,
        )

    def _oom(self, c: dict, ev: PodEvidence, source: str) -> IncidentAnalysis:
        name = c.get("name", "container")
        return IncidentAnalysis(
            failure_class=FailureClass.OOMKILLED,
            root_cause=(
                f"Container {name} was killed by the kernel OOM killer after "
                "exceeding its memory limit."
            ),
            evidence=[
                f"Container {name} terminated with reason OOMKilled.",
                f"Pod events: {[e.get('message') for e in ev.events]}",
            ],
            remediation=[
                "Increase the container memory limit, or reduce application memory usage.",
                "Confirm the memory *request* is set so the scheduler reserves capacity.",
                "Check for memory leaks or unbounded caches in the application.",
            ],
            confidence="high",
            source=source,
        )

    def _pending(self, ev: PodEvidence, source: str) -> IncidentAnalysis:
        msgs = [e.get("message") for e in ev.events]
        return IncidentAnalysis(
            failure_class=FailureClass.PENDING,
            root_cause=(
                "Pod is stuck in Pending because the scheduler cannot place it — "
                "typically an unsatisfiable nodeSelector/affinity, insufficient "
                "resources, or no matching node."
            ),
            evidence=[f"Event: {m}" for m in msgs] or ["Pod phase is Pending."],
            remediation=[
                "Inspect scheduler events for the exact scheduling constraint that failed.",
                "Verify node selectors/affinity/tolerations match available nodes.",
                "Confirm CPU/memory requests fit within node allocatable capacity.",
            ],
            confidence="medium",
            source=source,
        )

    def _crashloop(self, c: dict | None, ev: PodEvidence, source: str) -> IncidentAnalysis:
        name = (c or {}).get("name", "container")
        term = (c or {}).get("state", {}).get("terminated", {})
        exit_code = term.get("exitCode")
        reason = term.get("reason")
        evidence_bits = [
            f"Container {name} terminated (exit code {exit_code}, reason {reason}).",
        ]
        logs = ev.container_logs.get(name, "")
        if logs.strip():
            evidence_bits.append(f"Recent logs (first 5 lines):\n{logs.strip().splitlines()[:5]}")
        return IncidentAnalysis(
            failure_class=FailureClass.CRASHLOOP,
            root_cause=(
                f"Container {name} keeps exiting with a non-zero status "
                f"(exit code {exit_code}), causing repeated restarts."
            ),
            evidence=evidence_bits,
            remediation=[
                "Inspect container logs (including --previous) to find the crash cause.",
                "Verify the container command/entrypoint and required env vars/config.",
                "Check readiness/liveness probe configuration.",
                "Ensure dependencies (services, secrets, configmaps) are available.",
            ],
            confidence="medium",
            source=source,
        )


def analyze(evidence: PodEvidence) -> IncidentAnalysis:
    """Top-level entrypoint: try Ollama, fall back to the deterministic engine."""
    ollama = OllamaBackend()
    if ollama.model and _is_ollama_reachable():
        try:
            result = ollama.analyze(evidence)
            # Only trust a result with a real classification.
            if result.failure_class != FailureClass.UNKNOWN:
                return result
        except (RuntimeError, ValueError):
            pass  # fall through to rule engine
    return RuleEngine().analyze(evidence)
