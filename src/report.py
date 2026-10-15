"""Plain-English incident report generation (Markdown)."""

from __future__ import annotations

import datetime
from pathlib import Path

from .incident_analyzer import IncidentAnalysis
from .k8s_collector import PodEvidence


def render_report(ev: PodEvidence, analysis: IncidentAnalysis) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines.append(f"# Incident Report: {ev.namespace}/{ev.pod_name}")
    lines.append("")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Pod:** `{ev.pod_name}` (namespace `{ev.namespace}`)")
    lines.append(f"- **Failure class:** `{analysis.failure_class.value}`")
    lines.append(f"- **Analysis source:** `{analysis.source}`")
    lines.append(f"- **Confidence:** {analysis.confidence}")
    lines.append("")

    lines.append("## Suspected root cause")
    lines.append("")
    lines.append(analysis.root_cause)
    lines.append("")

    lines.append("## Supporting evidence")
    lines.append("")
    if analysis.evidence:
        for e in analysis.evidence:
            lines.append(f"- {e}")
    else:
        lines.append("- _(none captured)_")
    lines.append("")

    lines.append("## Pod status")
    lines.append("")
    lines.append("```")
    lines.append(f"Phase:     {ev.status.get('phase')}")
    lines.append(f"Reason:    {ev.status.get('reason')}")
    lines.append(f"Message:   {ev.status.get('message')}")
    lines.append(f"Node:      {ev.status.get('node_name')}")
    lines.append("```")
    lines.append("")

    if ev.events:
        lines.append("## Kubernetes events")
        lines.append("")
        lines.append("| Type | Reason | Message | Count |")
        lines.append("|------|--------|---------|-------|")
        for e in ev.events:
            msg = (e.get("message") or "").replace("|", "\\|")[:120]
            lines.append(
                f"| {e.get('type')} | {e.get('reason')} | {msg} | {e.get('count')} |"
            )
        lines.append("")

    if ev.node_info:
        lines.append("## Node resources")
        lines.append("")
        lines.append(f"- Node: `{ev.node_info.get('name')}`")
        alloc = ev.node_info.get("allocatable", {})
        cap = ev.node_info.get("capacity", {})
        lines.append(f"- Allocatable: cpu={alloc.get('cpu')}, memory={alloc.get('memory')}")
        lines.append(f"- Capacity:    cpu={cap.get('cpu')}, memory={cap.get('memory')}")
        lines.append("")

    if ev.container_logs:
        lines.append("## Recent container logs (excerpt)")
        lines.append("")
        for name, logs in ev.container_logs.items():
            if logs.strip():
                lines.append(f"### {name}")
                lines.append("")
                lines.append("```")
                lines.append(logs.strip().splitlines()[-20:] and "\n".join(logs.strip().splitlines()[-20:]))
                lines.append("```")
                lines.append("")

    if ev.previous_logs and any(v.strip() for v in ev.previous_logs.values()):
        lines.append("## Previous container logs (excerpt)")
        lines.append("")
        for name, logs in ev.previous_logs.items():
            if logs.strip():
                lines.append(f"### {name} (previous)")
                lines.append("")
                lines.append("```")
                lines.append("\n".join(logs.strip().splitlines()[-20:]))
                lines.append("```")
                lines.append("")

    lines.append("## Recommended remediation")
    lines.append("")
    for r in analysis.remediation:
        lines.append(f"- {r}")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Advisory report only. No remediation was applied automatically._")
    lines.append("")
    return "\n".join(lines)


def write_report(ev: PodEvidence, analysis: IncidentAnalysis,
                 out_dir: str = "examples/incident-reports") -> Path:
    """Write the report to a timestamped file and return its path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fname = f"{ev.pod_name}-{analysis.failure_class.value}-{ts}.md"
    path = out / fname
    path.write_text(render_report(ev, analysis))
    return path
