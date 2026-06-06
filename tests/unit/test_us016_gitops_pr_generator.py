# ruff: noqa: S101
"""tests/unit/test_us016_gitops_pr_generator.py — US-016 GitOps Auto-PR."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from gitops.pr_generator import (
    Finding,
    SandboxResult,
    _build_title,
    _is_auto_merge_eligible,
    create_remediation_pr,
)


def _finding(
    namespace: str = "staging",
    kind: str = "Deployment",
    name: str = "api-server",
    fix_class: str = "probe-fix",
    severity: str = "high",
) -> Finding:
    return Finding(
        finding_id="BEH-016",
        severity=severity,
        namespace=namespace,
        kind=kind,
        name=name,
        fix_class=fix_class,
        events_block="event line 1",
        logs_block="log line 1",
        manifest_diff="-old\n+new",
    )


def _sandbox(verdict: str = "healed") -> SandboxResult:
    return SandboxResult(
        verdict=verdict,
        sandbox_log_url="https://example.com/logs/123",
        smoke_test_output="OK: pod running",
    )


def _mock_ok() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    m.stdout = ""
    return m


def _gh_pr_list_empty() -> MagicMock:
    m = MagicMock()
    m.stdout = "[]"
    m.returncode = 0
    return m


def _gh_pr_list_existing(number: int = 7) -> MagicMock:
    m = MagicMock()
    m.stdout = json.dumps(
        [{"number": number, "url": f"https://github.com/ALx/k8s/pull/{number}"}]
    )
    m.returncode = 0
    return m


def _gh_pr_create_result(number: int = 42) -> MagicMock:
    m = MagicMock()
    m.stdout = f"https://github.com/AlbrightLaboratories/k8s-manifests/pull/{number}\n"
    m.returncode = 0
    return m


class TestTitleFormat:
    def test_title_format(self) -> None:
        f = _finding()
        title = _build_title(f)
        assert title == "[auto-remediate] ns/staging deployment/api-server: probe-fix"
        assert len(title) <= 120

    def test_title_truncation(self) -> None:
        long_name = "a" * 100
        f = _finding(name=long_name)
        title = _build_title(f)
        assert len(title) <= 120
        assert "..." in title


class TestDryRun:
    def test_dry_run_emits_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            result = asyncio.get_event_loop().run_until_complete(
                create_remediation_pr(_finding(), "fix-001", _sandbox(), dry_run=True)
            )
        mock_run.assert_not_called()
        assert result.pr_url == "dry-run://not-created"
        assert result.pr_number == 0
        captured = capsys.readouterr()
        assert "[auto-remediate]" in captured.out
        assert "BEH-016" in captured.out

    def test_dry_run_env_var(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            with patch.dict(os.environ, {"GITOPS_DRY_RUN": "true"}):
                result = asyncio.get_event_loop().run_until_complete(
                    create_remediation_pr(_finding(), "fix-002", _sandbox())
                )
        mock_run.assert_not_called()
        assert result.pr_url == "dry-run://not-created"


class TestLabels:
    def test_labels_include_severity_and_fix_class(self) -> None:
        side_effects = (
            [_gh_pr_list_empty()]
            + [_mock_ok()] * 5
            + [_gh_pr_create_result()]
        )
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            mock_run.side_effect = side_effects
            with patch.dict(os.environ, {"ALLOWED_AUTO_MERGE_NAMESPACES": "staging"}):
                asyncio.get_event_loop().run_until_complete(
                    create_remediation_pr(_finding(), "fix-003", _sandbox("healed"))
                )

        combined = " ".join(str(c) for c in mock_run.call_args_list)
        assert "severity/high" in combined
        assert "fix-class/probe-fix" in combined
        assert "sandbox-verified/true" in combined
        assert "human-review-required" not in combined


class TestTradingNamespace:
    def test_trading_namespace_never_auto_merged(self) -> None:
        side_effects = (
            [_gh_pr_list_empty()]
            + [_mock_ok()] * 5
            + [_gh_pr_create_result(99)]
            + [_mock_ok()]
        )
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            mock_run.side_effect = side_effects
            with patch.dict(os.environ, {"ALLOWED_AUTO_MERGE_NAMESPACES": "ibkr-live-trader"}):
                result = asyncio.get_event_loop().run_until_complete(
                    create_remediation_pr(
                        _finding(namespace="ibkr-live-trader"), "fix-004", _sandbox("healed")
                    )
                )

        assert result.auto_merge_eligible is False
        combined = " ".join(str(c) for c in mock_run.call_args_list)
        assert "'gh', 'pr', 'merge'" not in combined
        assert "human-review-required" in combined


class TestIdempotency:
    def test_idempotency_comments_on_existing_pr(self) -> None:
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            mock_run.side_effect = [_gh_pr_list_existing(7), _mock_ok()]
            result = asyncio.get_event_loop().run_until_complete(
                create_remediation_pr(_finding(), "fix-005", _sandbox("healed"))
            )

        assert result.was_existing is True
        assert result.pr_number == 7
        combined = " ".join(str(c) for c in mock_run.call_args_list)
        assert "'gh', 'pr', 'create'" not in combined
        assert "'gh', 'pr', 'comment'" in combined


class TestAutoMerge:
    def test_sandbox_red_blocks_auto_merge(self) -> None:
        f = _finding(namespace="staging", fix_class="probe-fix")
        s = _sandbox("failed")
        assert _is_auto_merge_eligible(f, s, "auto-merge") is False

    def test_nondeterministic_fix_class_blocks_merge(self) -> None:
        f = _finding(namespace="staging", fix_class="rewrite")
        s = _sandbox("healed")
        with patch.dict(os.environ, {"ALLOWED_AUTO_MERGE_NAMESPACES": "staging"}):
            assert _is_auto_merge_eligible(f, s, "auto-merge") is False

    def test_sandbox_red_no_auto_merge_call(self) -> None:
        side_effects = (
            [_gh_pr_list_empty()]
            + [_mock_ok()] * 5
            + [_gh_pr_create_result(11)]
        )
        with patch("gitops.pr_generator.subprocess.run") as mock_run:
            mock_run.side_effect = side_effects
            with patch.dict(os.environ, {"ALLOWED_AUTO_MERGE_NAMESPACES": "staging"}):
                result = asyncio.get_event_loop().run_until_complete(
                    create_remediation_pr(
                        _finding(namespace="staging", fix_class="probe-fix"),
                        "fix-006",
                        _sandbox("failed"),
                    )
                )

        assert result.auto_merge_eligible is False
        combined = " ".join(str(c) for c in mock_run.call_args_list)
        assert "'gh', 'pr', 'merge'" not in combined
