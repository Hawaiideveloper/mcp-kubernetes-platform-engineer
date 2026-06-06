"""
Unit tests for US-005: DPO Pair Schema (PRD §05).
"""

from __future__ import annotations

import json
import pytest

from auto_remediate.dpo_pair import (
    DpoPair,
    DpoPairContext,
    DpoPairMeta,
    DpoEmitSkipped,
    RemediationAction,
    build_issue_title,
    build_labels,
    check_emit_allowed,
    redact,
    redact_pair,
    render_issue_body,
    resolve_dpo_repo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_action(
    action_type: str = "pod_restart",
    command: str = "kubectl rollout restart deploy/nginx",
    outcome: str = "crashloop_recurred",
    duration: float = 5.0,
) -> RemediationAction:
    return RemediationAction(
        action_type=action_type,
        command=command,
        outcome=outcome,
        duration_seconds=duration,
    )


def _make_pair(
    namespace: str = "payments",
    kind: str = "Deployment",
    rejected: list[RemediationAction] | None = None,
) -> DpoPair:
    if rejected is None:
        rejected = [_make_action()]
    return DpoPair(
        prompt="nginx pod CrashLoopBackOff in payments namespace",
        chosen=_make_action(
            action_type="image_patch",
            command="kubectl set image deploy/nginx nginx=nginx:1.25",
            outcome="healed",
            duration=12.0,
        ),
        rejected=rejected,
        context=DpoPairContext(
            events=["Warning BackOff pod/nginx Back-off restarting failed container"],
            logs=["Error: image pull failed", "OOMKilled"],
            probe_state={
                "liveness": "Failing",
                "readiness": "Failing",
                "last_probe_time": "2026-06-05T03:00:00Z",
            },
            namespace=namespace,
            kind=kind,
        ),
        verification="NAME   READY  STATUS   RESTARTS  AGE\nnginx  1/1    Running  0         2m",
        meta=DpoPairMeta(
            sandbox_verified=True,
            prod_applied=True,
            time_to_fix_seconds=60.0,
            session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            remediator_version="0.5.0",
        ),
    )


# ---------------------------------------------------------------------------
# Redaction tests
# ---------------------------------------------------------------------------

def test_redact_token():
    assert redact("token=abc123secretval") == "token=[REDACTED]"


def test_redact_password():
    assert redact("password=hunter2") == "password=[REDACTED]"


def test_redact_multiple_on_line():
    line = "key=abc123 and secret=xyz789"
    result = redact(line)
    assert "abc123" not in result
    assert "xyz789" not in result
    assert "[REDACTED]" in result


def test_redact_no_match():
    line = "plain log line with no secrets"
    assert redact(line) == line


def test_redact_pair_redacts_command():
    pair = _make_pair()
    pair = pair.model_copy(
        update={
            "chosen": pair.chosen.model_copy(
                update={"command": "kubectl set image deploy/app app=repo:tag token=mysecret"}
            )
        }
    )
    safe = redact_pair(pair)
    assert "mysecret" not in safe.chosen.command
    assert "[REDACTED]" in safe.chosen.command


def test_redact_pair_redacts_logs():
    pair = _make_pair()
    pair = pair.model_copy(
        update={
            "context": pair.context.model_copy(
                update={"logs": ["normal line", "password=letmein"]}
            )
        }
    )
    safe = redact_pair(pair)
    assert "letmein" not in "\n".join(safe.context.logs)


# ---------------------------------------------------------------------------
# check_emit_allowed tests
# ---------------------------------------------------------------------------

def test_emit_allowed_normal():
    pair = _make_pair()
    check_emit_allowed(pair)  # should not raise


def test_emit_blocked_trading_namespace():
    for ns in ["brightflow-live", "ibkr-real-money-gateway", "daxxon-trading"]:
        pair = _make_pair(namespace=ns)
        with pytest.raises(DpoEmitSkipped, match="trading hard-skip"):
            check_emit_allowed(pair)


def test_emit_blocked_no_rejected():
    pair = _make_pair(rejected=[])
    with pytest.raises(DpoEmitSkipped, match="no rejected actions"):
        check_emit_allowed(pair)


def test_emit_blocked_session_not_done():
    pair = _make_pair()
    with pytest.raises(DpoEmitSkipped, match="not in DONE state"):
        check_emit_allowed(pair, session_done=False)


def test_emit_blocked_dry_run():
    pair = _make_pair()
    with pytest.raises(DpoEmitSkipped, match="dry_run"):
        check_emit_allowed(pair, dry_run=True)


# ---------------------------------------------------------------------------
# Issue rendering tests
# ---------------------------------------------------------------------------

def test_render_issue_body_contains_schema_version():
    pair = _make_pair()
    body = render_issue_body(pair)
    assert "<!-- dpo-pair-schema-version: 1 -->" in body


def test_render_issue_body_contains_chosen_type():
    pair = _make_pair()
    body = render_issue_body(pair)
    assert "image_patch" in body


def test_render_issue_body_contains_rejected_attempt():
    pair = _make_pair()
    body = render_issue_body(pair)
    assert "Attempt 1" in body


def test_render_issue_body_contains_namespace():
    pair = _make_pair()
    body = render_issue_body(pair)
    assert "payments" in body


def test_render_issue_body_contains_verification():
    pair = _make_pair()
    body = render_issue_body(pair)
    assert "Running" in body


def test_render_issue_body_meta_json():
    pair = _make_pair()
    body = render_issue_body(pair)
    meta = json.loads(
        body.split("```json")[1].split("```")[0].strip()
    )
    assert meta["session_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert meta["sandbox_verified"] is True


# ---------------------------------------------------------------------------
# Issue title tests
# ---------------------------------------------------------------------------

def test_build_issue_title_format():
    pair = _make_pair()
    title = build_issue_title(pair)
    assert title.startswith("[DPO]")
    assert "payments" in title
    assert "image_patch" in title


# ---------------------------------------------------------------------------
# Label tests
# ---------------------------------------------------------------------------

def test_build_labels_base():
    pair = _make_pair()
    labels = build_labels(pair)
    assert "dpo-pair" in labels
    assert "auto-remediation" in labels
    assert "corey-coder-ingest" in labels


def test_build_labels_ns_and_kind():
    pair = _make_pair(namespace="monitoring", kind="StatefulSet")
    labels = build_labels(pair)
    assert "ns/monitoring" in labels
    assert "kind/StatefulSet" in labels


# ---------------------------------------------------------------------------
# resolve_dpo_repo tests
# ---------------------------------------------------------------------------

def test_resolve_dpo_repo_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    repo, enabled = resolve_dpo_repo(config_path=str(tmp_path / "nonexistent.yaml"))
    assert repo == "AlbrightLaboratories/mcp-kubernetes-platform-engineer"
    assert enabled is True


def test_resolve_dpo_repo_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "AlbrightLaboratories/corey-coders")
    repo, enabled = resolve_dpo_repo(config_path=str(tmp_path / "nonexistent.yaml"))
    assert repo == "AlbrightLaboratories/corey-coders"


def test_resolve_dpo_repo_from_yaml(tmp_path):
    cfg = tmp_path / "dpo.yaml"
    cfg.write_text("dpo_issue_repo: AlbrightLaboratories/custom-repo\ndpo_enabled: true\n")
    repo, enabled = resolve_dpo_repo(config_path=str(cfg))
    assert repo == "AlbrightLaboratories/custom-repo"
    assert enabled is True


def test_resolve_dpo_repo_disabled_yaml(tmp_path):
    cfg = tmp_path / "dpo.yaml"
    cfg.write_text("dpo_issue_repo: ''\ndpo_enabled: false\n")
    _, enabled = resolve_dpo_repo(config_path=str(cfg))
    assert enabled is False
