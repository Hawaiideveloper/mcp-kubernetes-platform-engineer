"""
audit_inventory.py — Current-state inventory over all-findings.json (US-002).

Loads the 480 audit findings and exposes query helpers used by the review
and remediation pipeline.  No finding data is hard-coded here; every number
is derived live from the JSON source so the inventory stays accurate as the
file is updated by later audit runs.
"""

from __future__ import annotations

import json
import pathlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
VALID_FIX_CLASSES = {"rewrite", "design", "implement", "wire-up", "document"}

DEFAULT_FINDINGS_PATH = (
    pathlib.Path(__file__).parent.parent
    / "docs"
    / "audit-run-001"
    / "all-findings.json"
)


@dataclass(frozen=True)
class Finding:
    component_id: str
    kind: str
    severity: str
    fix_class: str
    diagnosis: str
    evidence: str
    evidence_secondary: str
    proposed_fix: str
    test_plan: str

    @classmethod
    def from_dict(cls, raw: dict) -> "Finding":
        return cls(
            component_id=raw.get("component_id", ""),
            kind=raw.get("kind", ""),
            severity=raw.get("severity", "").lower(),
            fix_class=raw.get("fix_class", "").lower(),
            diagnosis=raw.get("diagnosis", ""),
            evidence=raw.get("evidence", ""),
            evidence_secondary=raw.get("evidence_secondary", ""),
            proposed_fix=raw.get("proposed_fix", ""),
            test_plan=raw.get("test_plan", ""),
        )


@dataclass
class ComponentSummary:
    component_id: str
    finding_count: int
    max_severity: str
    primary_fix_class: str
    severities: Dict[str, int]
    fix_classes: Dict[str, int]


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


class AuditInventory:
    """
    Parsed view of all-findings.json with query helpers.

    Parameters
    ----------
    findings_path:
        Path to the JSON array of findings.  Defaults to the canonical
        docs/audit-run-001/all-findings.json path relative to this file.
    """

    def __init__(self, findings_path: Optional[pathlib.Path] = None) -> None:
        path = findings_path or DEFAULT_FINDINGS_PATH
        raw: List[dict] = json.loads(pathlib.Path(path).read_text())
        self._findings: List[Finding] = [Finding.from_dict(r) for r in raw]

    # ------------------------------------------------------------------
    # Basic accessors
    # ------------------------------------------------------------------

    @property
    def findings(self) -> List[Finding]:
        return list(self._findings)

    @property
    def total(self) -> int:
        return len(self._findings)

    # ------------------------------------------------------------------
    # Severity breakdown
    # ------------------------------------------------------------------

    def counts_by_severity(self) -> Dict[str, int]:
        """Return finding count per severity level (all levels present)."""
        counts: Dict[str, int] = {s: 0 for s in _SEVERITY_ORDER}
        for f in self._findings:
            if f.severity in counts:
                counts[f.severity] += 1
        return counts

    # ------------------------------------------------------------------
    # Fix-class breakdown
    # ------------------------------------------------------------------

    def counts_by_fix_class(self) -> Dict[str, int]:
        """Return finding count per fix class."""
        return dict(Counter(f.fix_class for f in self._findings))

    # ------------------------------------------------------------------
    # Component summaries
    # ------------------------------------------------------------------

    def top_components(self, n: int = 15) -> List[ComponentSummary]:
        """
        Return the top-n components by finding count, then by max severity.
        """
        by_component: Dict[str, List[Finding]] = defaultdict(list)
        for f in self._findings:
            by_component[f.component_id].append(f)

        summaries: List[ComponentSummary] = []
        for cid, findings in by_component.items():
            sev_counts = Counter(f.severity for f in findings)
            fix_counts = Counter(f.fix_class for f in findings)
            max_sev = min(
                (s for s in _SEVERITY_ORDER if sev_counts.get(s, 0) > 0),
                default="info",
                key=_SEVERITY_ORDER.index,
            )
            primary_fix = fix_counts.most_common(1)[0][0]
            summaries.append(
                ComponentSummary(
                    component_id=cid,
                    finding_count=len(findings),
                    max_severity=max_sev,
                    primary_fix_class=primary_fix,
                    severities=dict(sev_counts),
                    fix_classes=dict(fix_counts),
                )
            )

        summaries.sort(
            key=lambda s: (
                -s.finding_count,
                _SEVERITY_ORDER.index(s.max_severity),
            )
        )
        return summaries[:n]

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------

    def by_severity(self, severity: str) -> List[Finding]:
        """Return all findings matching the given severity."""
        return [f for f in self._findings if f.severity == severity.lower()]

    def by_fix_class(self, fix_class: str) -> List[Finding]:
        """Return all findings matching the given fix class."""
        return [f for f in self._findings if f.fix_class == fix_class.lower()]

    def by_component(self, component_id: str) -> List[Finding]:
        """Return all findings for the given component_id."""
        return [f for f in self._findings if f.component_id == component_id]

    # ------------------------------------------------------------------
    # Critical findings table
    # ------------------------------------------------------------------

    def critical_findings(self, limit: int = 30) -> List[Finding]:
        """
        Return up to `limit` critical findings, then high, sorted by
        component_id within each severity tier.
        """
        results: List[Finding] = []
        for sev in ("critical", "high"):
            tier = sorted(
                [f for f in self._findings if f.severity == sev],
                key=lambda f: f.component_id,
            )
            results.extend(tier)
            if len(results) >= limit:
                break
        return results[:limit]

    # ------------------------------------------------------------------
    # Pattern summary
    # ------------------------------------------------------------------

    def pattern_summary(self) -> Dict[str, object]:
        """
        High-level pattern breakdown aligned with the five recurring themes
        identified in the PRD §02 audit narrative.
        """
        stub_managers = sum(
            1
            for f in self._findings
            if f.fix_class == "rewrite"
            and any(
                kw in f.component_id
                for kw in ("mcp-tool", "manager", "behavior")
            )
        )
        dead_code = sum(
            1 for f in self._findings if "enhanced" in f.component_id
        )
        doc_overclaim = sum(
            1 for f in self._findings if f.fix_class == "document"
        )
        mock_tests = sum(
            1
            for f in self._findings
            if "test" in f.component_id.lower() or "TEST" in f.evidence
        )
        shell_scripts = sum(
            1
            for f in self._findings
            if f.component_id.endswith(".sh")
        )
        return {
            "stub_managers": stub_managers,
            "dead_enhanced_tools": dead_code,
            "doc_overclaim": doc_overclaim,
            "mock_only_tests": mock_tests,
            "shell_script_issues": shell_scripts,
        }
