"""
tests/unit/test_US022_acceptance.py

Unit tests for US-022: acceptance criteria and Checklist.md verifier.

Covers:
  - AcceptanceReport aggregation
  - check_checklist: exists, all checked, has unchecked, missing file
  - check_changelog_version: valid header, missing header, missing file
  - check_source_contains_k8s_call: found, not found, missing src dir
  - run_static_criteria: composite runner
"""

from __future__ import annotations

import textwrap
from pathlib import Path


from auto_remediate.acceptance import (
    AcceptanceReport,
    CriterionResult,
    check_changelog_version,
    check_checklist,
    check_source_contains_k8s_call,
    run_static_criteria,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path, **files: str) -> Path:
    """Write *files* dict of {relative_path: content} into tmp_path."""
    for rel, content in files.items():
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(textwrap.dedent(content), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# AcceptanceReport
# ---------------------------------------------------------------------------


class TestAcceptanceReport:
    def test_empty_report_is_not_passed(self) -> None:
        report = AcceptanceReport()
        assert not report.passed()

    def test_all_pass(self) -> None:
        report = AcceptanceReport(
            results=[
                CriterionResult("C1", passed=True),
                CriterionResult("C2", passed=True),
            ]
        )
        assert report.passed()
        assert report.failing() == []

    def test_one_fail(self) -> None:
        report = AcceptanceReport(
            results=[
                CriterionResult("C1", passed=True),
                CriterionResult("C2", passed=False, detail="lint error"),
            ]
        )
        assert not report.passed()
        assert len(report.failing()) == 1

    def test_summary_format(self) -> None:
        report = AcceptanceReport(
            results=[
                CriterionResult("C1", passed=True),
                CriterionResult("C2", passed=False),
            ]
        )
        summary = report.summary()
        assert "1/2" in summary
        assert "passed" in summary


# ---------------------------------------------------------------------------
# check_checklist
# ---------------------------------------------------------------------------


class TestCheckChecklist:
    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = check_checklist(tmp_path)
        assert not result.passed
        assert result.criterion_id == "C10"
        assert "not found" in result.detail

    def test_all_boxes_checked_passes(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            # Checklist
            - [x] C1: lint
            - [x] C2: tests
            - [X] C3: type check
            """
        )
        (tmp_path / "Checklist.md").write_text(content)
        result = check_checklist(tmp_path)
        assert result.passed
        assert "Unchecked: 0" in result.detail

    def test_unchecked_box_fails(self, tmp_path: Path) -> None:
        content = textwrap.dedent(
            """\
            # Checklist
            - [x] C1: lint
            - [ ] C2: tests
            """
        )
        (tmp_path / "Checklist.md").write_text(content)
        result = check_checklist(tmp_path)
        assert not result.passed
        assert "Unchecked: 1" in result.detail

    def test_empty_checklist_passes_no_boxes(self, tmp_path: Path) -> None:
        (tmp_path / "Checklist.md").write_text("# Checklist\n\nNo items.\n")
        result = check_checklist(tmp_path)
        assert result.passed
        assert "Unchecked: 0" in result.detail


# ---------------------------------------------------------------------------
# check_changelog_version
# ---------------------------------------------------------------------------


class TestCheckChangelogVersion:
    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = check_changelog_version(tmp_path)
        assert not result.passed
        assert result.criterion_id == "CHANGELOG"

    def test_valid_alpha_header_passes(self, tmp_path: Path) -> None:
        content = "## [Alpha-42-ab1234-0-1_0-2026-06-06] — 2026-06-06\n\n### Fixed\n- something\n"
        (tmp_path / "CHANGELOG.md").write_text(content)
        result = check_changelog_version(tmp_path)
        assert result.passed
        assert "Alpha-42" in result.detail

    def test_no_alpha_header_fails(self, tmp_path: Path) -> None:
        content = "## [1.0.0] — 2026-01-01\n\n### Fixed\n- something\n"
        (tmp_path / "CHANGELOG.md").write_text(content)
        result = check_changelog_version(tmp_path)
        assert not result.passed
        assert "No Alpha-*" in result.detail

    def test_multiple_alpha_headers_counted(self, tmp_path: Path) -> None:
        content = (
            "## [Alpha-2-aaaaaa-0-1_0-2026-06-06] — 2026-06-06\n\n"
            "## [Alpha-1-bbbbbb-0-1_0-2026-06-05] — 2026-06-05\n"
        )
        (tmp_path / "CHANGELOG.md").write_text(content)
        result = check_changelog_version(tmp_path)
        assert result.passed
        assert "2" in result.detail


# ---------------------------------------------------------------------------
# check_source_contains_k8s_call
# ---------------------------------------------------------------------------


class TestCheckSourceContainsK8sCall:
    def test_missing_src_fails(self, tmp_path: Path) -> None:
        result = check_source_contains_k8s_call(tmp_path)
        assert not result.passed
        assert result.criterion_id == "C6a"

    def test_call_present_passes(self, tmp_path: Path) -> None:
        _make_repo(
            tmp_path,
            **{
                "src/k8s_manager.py": (
                    "def list_pods():\n"
                    "    return client.CoreV1Api().list_namespaced_pod('default')\n"
                )
            },
        )
        result = check_source_contains_k8s_call(tmp_path)
        assert result.passed
        assert "list_namespaced_pod" in result.detail

    def test_call_absent_fails(self, tmp_path: Path) -> None:
        _make_repo(
            tmp_path,
            **{"src/manager.py": "def hello():\n    pass\n"},
        )
        result = check_source_contains_k8s_call(tmp_path)
        assert not result.passed

    def test_nested_src_file_detected(self, tmp_path: Path) -> None:
        _make_repo(
            tmp_path,
            **{
                "src/sub/deep/manager.py": (
                    "v1.list_namespaced_pod(namespace)\n"
                )
            },
        )
        result = check_source_contains_k8s_call(tmp_path)
        assert result.passed


# ---------------------------------------------------------------------------
# run_static_criteria (composite)
# ---------------------------------------------------------------------------


class TestRunStaticCriteria:
    def test_all_pass_on_valid_repo(self, tmp_path: Path) -> None:
        # Checklist with all boxes checked
        checklist = textwrap.dedent(
            """\
            # Checklist
            - [x] C1: lint passes
            - [x] C2: tests pass
            """
        )
        # CHANGELOG with valid header
        changelog = "## [Alpha-1-abc123-0-1_0-2026-06-06] — 2026-06-06\n\n- initial\n"
        # src with k8s call
        _make_repo(
            tmp_path,
            **{
                "Checklist.md": checklist,
                "CHANGELOG.md": changelog,
                "src/k8s.py": "v1.list_namespaced_pod(ns)\n",
            },
        )
        report = run_static_criteria(tmp_path)
        assert report.passed(), f"Failing: {[r.detail for r in report.failing()]}"
        assert len(report.results) == 3

    def test_partial_fail_detected(self, tmp_path: Path) -> None:
        checklist = "# Checklist\n- [ ] C1: not done\n"
        changelog = "## [Alpha-1-abc123-0-1_0-2026-06-06] — 2026-06-06\n"
        _make_repo(
            tmp_path,
            **{
                "Checklist.md": checklist,
                "CHANGELOG.md": changelog,
                "src/k8s.py": "v1.list_namespaced_pod(ns)\n",
            },
        )
        report = run_static_criteria(tmp_path)
        assert not report.passed()
        assert len(report.failing()) == 1
        assert report.failing()[0].criterion_id == "C10"
