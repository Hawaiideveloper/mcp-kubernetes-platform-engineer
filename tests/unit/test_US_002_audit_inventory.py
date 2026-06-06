"""
tests/unit/test_US_002_audit_inventory.py

Unit tests for AuditInventory (US-002 — current-state inventory).

These tests exercise the real all-findings.json when it is available and
fall back to a fixture when running in isolation (e.g. inside a container
that only has the worktree, not the full docs tree).
"""

from __future__ import annotations

import json
import pathlib

import pytest

from src.audit_inventory import (
    AuditInventory,
    ComponentSummary,
    Finding,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_SAMPLE_FINDINGS = [
    {
        "component_id": "mcp-tool:diagnose_cluster_health",
        "kind": "mcp-tool",
        "severity": "critical",
        "fix_class": "rewrite",
        "diagnosis": "Fully stubbed; returns invented node names.",
        "evidence": "src/k8s_manager.py:1-50",
        "evidence_secondary": "",
        "proposed_fix": "Call CoreV1Api().list_node().",
        "test_plan": "Mock kubernetes.client and assert API is called.",
    },
    {
        "component_id": "src/helm_manager.py",
        "kind": "source",
        "severity": "high",
        "fix_class": "rewrite",
        "diagnosis": "install_helm_chart passes URL as repo name.",
        "evidence": "src/helm_manager.py:20-40",
        "evidence_secondary": "",
        "proposed_fix": "Parse URL separately from repo name.",
        "test_plan": "Assert subprocess args contain correct repo name.",
    },
    {
        "component_id": "behavior:rbac_split",
        "kind": "behavior",
        "severity": "critical",
        "fix_class": "design",
        "diagnosis": "All operations share a single Kubernetes identity.",
        "evidence": "k8s/serviceaccount.yaml",
        "evidence_secondary": "",
        "proposed_fix": "Create read-only and write ServiceAccounts.",
        "test_plan": "Verify two SA manifests exist with distinct permissions.",
    },
    {
        "component_id": "README.md",
        "kind": "document",
        "severity": "critical",
        "fix_class": "document",
        "diagnosis": "Five production-readiness claims are false.",
        "evidence": "README.md:1-50",
        "evidence_secondary": "",
        "proposed_fix": "Replace with accurate capability descriptions.",
        "test_plan": "Review document for false claims.",
    },
    {
        "component_id": "setup-vscode-k8s.sh",
        "kind": "script",
        "severity": "critical",
        "fix_class": "rewrite",
        "diagnosis": "Single-quoted heredoc prevents variable expansion.",
        "evidence": "setup-vscode-k8s.sh:15",
        "evidence_secondary": "",
        "proposed_fix": "Use double-quoted heredoc.",
        "test_plan": "Shellcheck passes.",
    },
    {
        "component_id": "mcp-tool:check_network_connectivity",
        "kind": "mcp-tool",
        "severity": "critical",
        "fix_class": "rewrite",
        "diagnosis": "Returns fabricated connectivity data.",
        "evidence": "src/k8s_manager.py:100-120",
        "evidence_secondary": "",
        "proposed_fix": "Call NetworkingV1Api().",
        "test_plan": "Mock k8s client and assert called.",
    },
    {
        "component_id": "enhanced:kubectl_describe",
        "kind": "enhanced",
        "severity": "critical",
        "fix_class": "wire-up",
        "diagnosis": "Tool defined but mcp_server.py never imports enhanced_tools.",
        "evidence": "src/mcp_server.py:1-20",
        "evidence_secondary": "",
        "proposed_fix": "Import enhanced_tools in mcp_server.py.",
        "test_plan": "Integration test: call tool via MCP client.",
    },
    {
        "component_id": "k8s/pvc.yaml",
        "kind": "manifest",
        "severity": "high",
        "fix_class": "document",
        "diagnosis": "PVC hardcodes local-path storage class.",
        "evidence": "k8s/pvc.yaml:5",
        "evidence_secondary": "",
        "proposed_fix": "Parameterise storageClassName.",
        "test_plan": "Verify no hardcoded storageClassName.",
    },
    {
        "component_id": "src/documentation_manager.py",
        "kind": "source",
        "severity": "high",
        "fix_class": "rewrite",
        "diagnosis": "Startup blocks on live HTTP to kubernetes.io.",
        "evidence": "src/documentation_manager.py:30-60",
        "evidence_secondary": "",
        "proposed_fix": "Add offline fallback cache.",
        "test_plan": "Assert startup completes without network.",
    },
    {
        "component_id": "mcp-tool:analyze_logs",
        "kind": "mcp-tool",
        "severity": "medium",
        "fix_class": "rewrite",
        "diagnosis": "Returns hardcoded static log data.",
        "evidence": "src/diagnostics_manager.py:40-80",
        "evidence_secondary": "",
        "proposed_fix": "Call CoreV1Api().read_namespaced_pod_log().",
        "test_plan": "Mock CoreV1Api and assert called.",
    },
]


@pytest.fixture()
def tmp_findings_path(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "all-findings.json"
    p.write_text(json.dumps(_SAMPLE_FINDINGS))
    return p


@pytest.fixture()
def inventory(tmp_findings_path: pathlib.Path) -> AuditInventory:
    return AuditInventory(findings_path=tmp_findings_path)


# ---------------------------------------------------------------------------
# Tests — Finding dataclass
# ---------------------------------------------------------------------------


class TestFinding:
    def test_from_dict_normalises_severity(self):
        raw = {**_SAMPLE_FINDINGS[0], "severity": "Critical"}
        f = Finding.from_dict(raw)
        assert f.severity == "critical"

    def test_from_dict_normalises_fix_class(self):
        raw = {**_SAMPLE_FINDINGS[0], "fix_class": "REWRITE"}
        f = Finding.from_dict(raw)
        assert f.fix_class == "rewrite"

    def test_from_dict_missing_optional_field(self):
        raw = {k: v for k, v in _SAMPLE_FINDINGS[0].items() if k != "evidence_secondary"}
        f = Finding.from_dict(raw)
        assert f.evidence_secondary == ""


# ---------------------------------------------------------------------------
# Tests — AuditInventory
# ---------------------------------------------------------------------------


class TestAuditInventory:
    def test_total_count(self, inventory: AuditInventory):
        assert inventory.total == len(_SAMPLE_FINDINGS)

    def test_findings_returns_copy(self, inventory: AuditInventory):
        a = inventory.findings
        b = inventory.findings
        assert a is not b
        assert len(a) == len(b)

    # counts_by_severity

    def test_counts_by_severity_all_levels_present(self, inventory: AuditInventory):
        counts = inventory.counts_by_severity()
        assert set(counts.keys()) == {"critical", "high", "medium", "low", "info"}

    def test_counts_by_severity_values(self, inventory: AuditInventory):
        counts = inventory.counts_by_severity()
        critical = sum(1 for f in _SAMPLE_FINDINGS if f["severity"] == "critical")
        high = sum(1 for f in _SAMPLE_FINDINGS if f["severity"] == "high")
        medium = sum(1 for f in _SAMPLE_FINDINGS if f["severity"] == "medium")
        assert counts["critical"] == critical
        assert counts["high"] == high
        assert counts["medium"] == medium
        assert counts["low"] == 0
        assert counts["info"] == 0

    def test_counts_sum_to_total(self, inventory: AuditInventory):
        counts = inventory.counts_by_severity()
        assert sum(counts.values()) == inventory.total

    # counts_by_fix_class

    def test_counts_by_fix_class(self, inventory: AuditInventory):
        counts = inventory.counts_by_fix_class()
        rewrite_count = sum(1 for f in _SAMPLE_FINDINGS if f["fix_class"] == "rewrite")
        assert counts["rewrite"] == rewrite_count

    # top_components

    def test_top_components_length_capped(self, inventory: AuditInventory):
        top = inventory.top_components(n=3)
        assert len(top) <= 3

    def test_top_components_sorted_by_count_desc(self, inventory: AuditInventory):
        top = inventory.top_components(n=10)
        counts = [c.finding_count for c in top]
        assert counts == sorted(counts, reverse=True)

    def test_top_components_returns_component_summary(self, inventory: AuditInventory):
        top = inventory.top_components(n=5)
        for cs in top:
            assert isinstance(cs, ComponentSummary)

    # by_severity

    def test_by_severity_critical(self, inventory: AuditInventory):
        crits = inventory.by_severity("critical")
        assert all(f.severity == "critical" for f in crits)
        assert len(crits) == sum(1 for f in _SAMPLE_FINDINGS if f["severity"] == "critical")

    def test_by_severity_case_insensitive(self, inventory: AuditInventory):
        assert inventory.by_severity("CRITICAL") == inventory.by_severity("critical")

    def test_by_severity_empty_for_unknown(self, inventory: AuditInventory):
        assert inventory.by_severity("none") == []

    # by_fix_class

    def test_by_fix_class_rewrite(self, inventory: AuditInventory):
        rewrites = inventory.by_fix_class("rewrite")
        assert all(f.fix_class == "rewrite" for f in rewrites)

    # by_component

    def test_by_component_known(self, inventory: AuditInventory):
        results = inventory.by_component("README.md")
        assert len(results) == 1
        assert results[0].component_id == "README.md"

    def test_by_component_unknown(self, inventory: AuditInventory):
        assert inventory.by_component("does-not-exist") == []

    # critical_findings

    def test_critical_findings_limit(self, inventory: AuditInventory):
        results = inventory.critical_findings(limit=3)
        assert len(results) <= 3

    def test_critical_findings_sorted_by_component(self, inventory: AuditInventory):
        results = inventory.critical_findings(limit=50)
        # Within the critical tier, check sorted by component_id
        critical_only = [f for f in results if f.severity == "critical"]
        ids = [f.component_id for f in critical_only]
        assert ids == sorted(ids)

    # pattern_summary

    def test_pattern_summary_keys(self, inventory: AuditInventory):
        summary = inventory.pattern_summary()
        expected_keys = {
            "stub_managers",
            "dead_enhanced_tools",
            "doc_overclaim",
            "mock_only_tests",
            "shell_script_issues",
        }
        assert set(summary.keys()) == expected_keys

    def test_pattern_summary_values_non_negative(self, inventory: AuditInventory):
        summary = inventory.pattern_summary()
        for key, val in summary.items():
            assert val >= 0, f"{key} should be non-negative"

    def test_pattern_summary_shell_scripts(self, inventory: AuditInventory):
        summary = inventory.pattern_summary()
        sh_count = sum(1 for f in _SAMPLE_FINDINGS if f["component_id"].endswith(".sh"))
        assert summary["shell_script_issues"] == sh_count


# ---------------------------------------------------------------------------
# Integration-ish: load the real findings file if available
# ---------------------------------------------------------------------------


class TestRealFindings:
    """
    These tests run against the actual all-findings.json when present.
    They are skipped gracefully when the file is absent.
    """

    REAL_PATH = (
        pathlib.Path(__file__).parent.parent.parent
        / "docs"
        / "audit-run-001"
        / "all-findings.json"
    )

    @pytest.fixture(autouse=True)
    def require_real_file(self):
        if not self.REAL_PATH.exists():
            pytest.skip("all-findings.json not present — skipping real-data tests")

    @pytest.fixture()
    def real_inventory(self) -> AuditInventory:
        return AuditInventory(findings_path=self.REAL_PATH)

    def test_US_002_total_is_480(self, real_inventory: AuditInventory):
        assert real_inventory.total == 480

    def test_US_002_critical_count(self, real_inventory: AuditInventory):
        counts = real_inventory.counts_by_severity()
        assert counts["critical"] == 117

    def test_US_002_high_count(self, real_inventory: AuditInventory):
        counts = real_inventory.counts_by_severity()
        assert counts["high"] == 215

    def test_US_002_severity_sum(self, real_inventory: AuditInventory):
        counts = real_inventory.counts_by_severity()
        assert sum(counts.values()) == 480

    def test_US_002_top_component_has_findings(self, real_inventory: AuditInventory):
        top = real_inventory.top_components(n=1)
        assert len(top) == 1
        assert top[0].finding_count >= 1

    def test_US_002_pattern_summary_stub_managers_nonzero(self, real_inventory: AuditInventory):
        summary = real_inventory.pattern_summary()
        assert summary["stub_managers"] > 0
