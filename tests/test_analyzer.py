"""Unit tests for the incident analyzer's deterministic rule engine.

These run with no cluster and no LLM — they validate classification logic on
synthetic evidence.
"""

import pytest

from src.incident_analyzer import FailureClass, RuleEngine
from src.k8s_collector import PodEvidence


def _container(name, exit_code=None, reason=None, waiting_reason=None):
    state = {}
    if exit_code is not None or reason is not None:
        state["terminated"] = {"exitCode": exit_code, "reason": reason}
    if waiting_reason:
        state["waiting"] = {"reason": waiting_reason}
    return {"name": name, "state": state}


def _ev(status, container_statuses=None, events=None):
    return PodEvidence(
        namespace="ns", pod_name="p",
        status=dict(status),
        events=events or [],
        container_logs={},
        previous_logs={},
        deployment={},
        node_info={},
    )


def test_oomkilled_detection():
    ev = _ev(
        {"phase": "Running", "container_statuses": [_container("app", exit_code=137, reason="OOMKilled")]},
        events=[{"reason": "Killing", "message": "OOMKilled"}],
    )
    a = RuleEngine().analyze(ev)
    assert a.failure_class == FailureClass.OOMKILLED
    assert a.confidence == "high"


def test_pending_detection():
    ev = _ev(
        {"phase": "Pending", "container_statuses": []},
        events=[{"reason": "FailedScheduling", "message": "didn't match node selector"}],
    )
    a = RuleEngine().analyze(ev)
    assert a.failure_class == FailureClass.PENDING


def test_crashloop_detection():
    ev = _ev(
        {"phase": "Running", "container_statuses": [_container("app", waiting_reason="CrashLoopBackOff")]},
    )
    a = RuleEngine().analyze(ev)
    assert a.failure_class == FailureClass.CRASHLOOP


def test_crashloop_nonzero_exit():
    ev = _ev(
        {"phase": "Running", "container_statuses": [_container("app", exit_code=1)]},
        events=[{"reason": "BackOff", "message": "back-off restarting"}],
    )
    a = RuleEngine().analyze(ev)
    assert a.failure_class == FailureClass.CRASHLOOP


def test_unknown_when_healthy():
    ev = _ev(
        {"phase": "Running", "container_statuses": [_container("app", exit_code=0)]},
    )
    a = RuleEngine().analyze(ev)
    assert a.failure_class == FailureClass.UNKNOWN


def test_remediation_not_empty():
    ev = _ev(
        {"phase": "Running", "container_statuses": [_container("app", exit_code=1)]},
        events=[{"reason": "BackOff", "message": "back-off restarting"}],
    )
    a = RuleEngine().analyze(ev)
    assert a.remediation, "remediation steps must be present"


def test_each_failure_class_has_root_cause():
    cases = [
        _ev({"phase": "Running", "container_statuses": [_container("a", exit_code=137, reason="OOMKilled")]}),
        _ev({"phase": "Pending", "container_statuses": []}),
        _ev({"phase": "Running", "container_statuses": [_container("a", waiting_reason="CrashLoopBackOff")]}),
    ]
    for ev in cases:
        a = RuleEngine().analyze(ev)
        assert a.root_cause, "root cause must be non-empty"
        assert a.evidence, "evidence must be non-empty"
