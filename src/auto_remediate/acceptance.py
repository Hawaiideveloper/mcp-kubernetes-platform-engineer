"""
acceptance.py — Acceptance criteria verifier (PRD §22, US-022).

Provides programmatic checks for the done-bar criteria so that CI and
the Phase E iteration loop can confirm project readiness without parsing prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


# ---------------------------------------------------------------------------
# Criterion data model
# ---------------------------------------------------------------------------


@dataclass
class CriterionResult:
    """Result of a single acceptance criterion check."""

    criterion_id: str
    passed: bool
    detail: str = ""


@dataclass
class AcceptanceReport:
    """Aggregated results for all criteria."""

    results: List[CriterionResult] = field(default_factory=list)

    def passed(self) -> bool:
        """Return True only when every criterion passed."""
        return bool(self.results) and all(r.passed for r in self.results)

    def failing(self) -> List[CriterionResult]:
        """Return only the failing criteria."""
        return [r for r in self.results if not r.passed]

    def summary(self) -> str:
        """One-line pass/fail summary with counts."""
        ok = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        return f"{ok}/{total} criteria passed"


# ---------------------------------------------------------------------------
# Individual criterion checkers
# ---------------------------------------------------------------------------


def check_checklist(repo_root: Path) -> CriterionResult:
    """
    C10 — Verify Checklist.md exists and has zero unchecked boxes.

    Args:
        repo_root: Root of the repository (must contain Checklist.md).

    Returns:
        CriterionResult with passed=True when Checklist.md has no ``- [ ]`` entries.
    """
    checklist = repo_root / "Checklist.md"
    if not checklist.exists():
        return CriterionResult(
            criterion_id="C10",
            passed=False,
            detail="Checklist.md not found at repo root",
        )

    text = checklist.read_text(encoding="utf-8")
    unchecked = re.findall(r"- \[ \]", text)
    checked = re.findall(r"- \[x\]", text, re.IGNORECASE)

    if unchecked:
        return CriterionResult(
            criterion_id="C10",
            passed=False,
            detail=f"Checked: {len(checked)}  Unchecked: {len(unchecked)}",
        )

    return CriterionResult(
        criterion_id="C10",
        passed=True,
        detail=f"Checked: {len(checked)}  Unchecked: 0",
    )


def check_changelog_version(repo_root: Path) -> CriterionResult:
    """
    Verify CHANGELOG.md exists and contains at least one version header in the
    expected Alpha-* format.

    Args:
        repo_root: Root of the repository.

    Returns:
        CriterionResult indicating whether the version format is present.
    """
    changelog = repo_root / "CHANGELOG.md"
    if not changelog.exists():
        return CriterionResult(
            criterion_id="CHANGELOG",
            passed=False,
            detail="CHANGELOG.md not found at repo root",
        )

    text = changelog.read_text(encoding="utf-8")
    pattern = r"## \[Alpha-\d+-[0-9a-f]+-\d+-\d+_\d+-\d{4}-\d{2}-\d{2}\]"
    matches = re.findall(pattern, text)

    if not matches:
        return CriterionResult(
            criterion_id="CHANGELOG",
            passed=False,
            detail="No Alpha-* version header found in CHANGELOG.md",
        )

    return CriterionResult(
        criterion_id="CHANGELOG",
        passed=True,
        detail=f"Found {len(matches)} version header(s); latest: {matches[0]}",
    )


def check_source_contains_k8s_call(repo_root: Path) -> CriterionResult:
    """
    C6a — Verify at least one source file calls list_namespaced_pod.

    Args:
        repo_root: Root of the repository.

    Returns:
        CriterionResult indicating whether the Kubernetes API call is wired.
    """
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return CriterionResult(
            criterion_id="C6a",
            passed=False,
            detail="src/ directory not found",
        )

    matches: list[str] = []
    for py_file in src_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        if "list_namespaced_pod" in text:
            matches.append(str(py_file.relative_to(repo_root)))

    if not matches:
        return CriterionResult(
            criterion_id="C6a",
            passed=False,
            detail="list_namespaced_pod not found in any src/*.py file",
        )

    return CriterionResult(
        criterion_id="C6a",
        passed=True,
        detail=f"list_namespaced_pod found in: {', '.join(matches)}",
    )


# ---------------------------------------------------------------------------
# Composite runner
# ---------------------------------------------------------------------------


def run_static_criteria(repo_root: Path) -> AcceptanceReport:
    """
    Run all static (filesystem-only) acceptance criteria checks.

    These checks do not require a live cluster; they validate what is
    committed to the repo.

    Args:
        repo_root: Root of the repository checkout.

    Returns:
        AcceptanceReport with results for C6a, CHANGELOG, and C10.
    """
    report = AcceptanceReport()
    report.results.append(check_source_contains_k8s_call(repo_root))
    report.results.append(check_changelog_version(repo_root))
    report.results.append(check_checklist(repo_root))
    return report
