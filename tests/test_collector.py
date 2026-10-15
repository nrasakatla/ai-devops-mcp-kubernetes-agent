"""Unit tests for the read-only kubectl guard in k8s_collector.

No cluster required — these validate the safety logic directly.
"""

import pytest

from src import k8s_collector as kc


def test_mutation_verbs_rejected(monkeypatch):
    for verb in ["apply", "delete", "patch", "scale", "exec", "create"]:
        with pytest.raises(kc.UnsafeKubectlVerb):
            kc._kubectl([verb, "pod", "x"])


def test_read_only_verbs_allowed(monkeypatch):
    # get / list run _kubectl -> subprocess; assert the guard lets them through
    # by checking the verb validation (we fake subprocess to avoid real kubectl).
    import subprocess

    def fake_run(*args, **kwargs):
        class R:
            returncode = 0
            stdout = "{}"
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    # get produces json path
    out = kc._kubectl(["get", "pods", "-n", "x"])
    assert out == "{}"


def test_empty_args_rejected():
    with pytest.raises(ValueError):
        kc._kubectl([])


def test_context_guard(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        class R:
            returncode = 0
            stdout = "some-other-cluster\n"
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(kc.ContextGuardError):
        kc.check_context("kind-ai-devops-demo")


def test_context_guard_passes(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        class R:
            returncode = 0
            stdout = "kind-ai-devops-demo\n"
            stderr = ""
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    kc.check_context("kind-ai-devops-demo")  # should not raise
