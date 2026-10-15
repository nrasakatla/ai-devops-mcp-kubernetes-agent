"""CLI entrypoint: collect evidence for a failing pod and write an incident report.

Usage:
    python -m agents.diagnose_pod <namespace> <pod_name> [--context NAME] [--out DIR] [--force-rule-engine]
"""

from __future__ import annotations

import argparse
import os
import sys

from src.incident_analyzer import RuleEngine, analyze
from src.k8s_collector import collect_pod_evidence
from src.report import write_report

DEFAULT_CONTEXT = os.environ.get("AI_DEVOPS_KIND_CONTEXT", "kind-ai-devops-demo")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a failing Kubernetes pod.")
    parser.add_argument("namespace")
    parser.add_argument("pod_name")
    parser.add_argument("--context", default=DEFAULT_CONTEXT,
                        help="Expected local kubeconfig context (safety guard).")
    parser.add_argument("--out", default="examples/incident-reports",
                        help="Output directory for the report.")
    parser.add_argument("--force-rule-engine", action="store_true",
                        help="Skip Ollama and use the deterministic rule engine.")
    args = parser.parse_args(argv)

    print(f"[*] Collecting read-only evidence for {args.namespace}/{args.pod_name} ...")
    evidence = collect_pod_evidence(args.namespace, args.pod_name, args.context)

    if args.force_rule_engine:
        analysis = RuleEngine().analyze(evidence)
    else:
        analysis = analyze(evidence)

    path = write_report(evidence, analysis, args.out)
    print(f"[*] Failure class: {analysis.failure_class.value}")
    print(f"[*] Analysis source: {analysis.source}")
    print(f"[*] Report written: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
