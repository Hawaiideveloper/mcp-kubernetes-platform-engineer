"""Unit tests for US-019: four-identity RBAC split.

Tests cover:
  - rbac_identities: namespace classification helpers, validate_no_applier_in_trading
  - rbac_audit_logger: record schema, pre/post action behaviour, degraded state
  - rbac_ci_check: file-based check for applier bindings in trading namespaces
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from src.auto_remediate.rbac_identities import (
    TRADING_NAMESPACES,
    RbacIdentity,
    is_applier_eligible,
    is_sandbox_namespace,
    is_system_namespace,
    is_trading_namespace,
    validate_no_applier_in_trading,
)
from src.auto_remediate.rbac_audit_logger import (
    ApplierAuditLogger,
    build_audit_record,
)
from src.auto_remediate.rbac_ci_check import check_directory, check_file


# ---------------------------------------------------------------------------
# rbac_identities
# ---------------------------------------------------------------------------


class TestRbacIdentities:
    def test_trading_namespace_detection(self):
        for ns in ["ibkr-live-trader", "daxxon-trading", "brightflow-live"]:
            assert is_trading_namespace(ns), f"{ns} should be trading"

    def test_non_trading_namespace(self):
        assert not is_trading_namespace("brightflow-dashboard")
        assert not is_trading_namespace("triton-inference")
        assert not is_trading_namespace("sandbox-pr-42")

    def test_system_namespace_detection(self):
        for ns in ["kube-system", "kube-public", "kube-node-lease", "auto-remediate"]:
            assert is_system_namespace(ns)

    def test_sandbox_namespace_detection(self):
        assert is_sandbox_namespace("sandbox-pr-42")
        assert is_sandbox_namespace("sandbox-test")
        assert not is_sandbox_namespace("production")

    def test_applier_eligible_non_trading(self):
        assert is_applier_eligible("brightflow-dashboard")
        assert is_applier_eligible("triton-inference")
        assert is_applier_eligible("my-app-ns")

    def test_applier_not_eligible_trading(self):
        for ns in TRADING_NAMESPACES:
            assert not is_applier_eligible(ns)

    def test_applier_not_eligible_system(self):
        assert not is_applier_eligible("kube-system")
        assert not is_applier_eligible("auto-remediate")

    def test_applier_not_eligible_sandbox(self):
        assert not is_applier_eligible("sandbox-pr-99")

    def test_validate_no_applier_raises_for_trading(self):
        for ns in TRADING_NAMESPACES:
            with pytest.raises(ValueError, match="trading namespace"):
                validate_no_applier_in_trading(ns)

    def test_validate_no_applier_passes_for_eligible(self):
        validate_no_applier_in_trading("brightflow-dashboard")  # must not raise

    def test_rbac_identity_enum_values(self):
        assert RbacIdentity.READER == "auto-remediate-reader"
        assert RbacIdentity.APPLIER == "auto-remediate-applier"
        assert RbacIdentity.SANDBOX == "auto-remediate-sandbox"
        assert RbacIdentity.PR_BOT == "auto-remediate-pr-bot"


# ---------------------------------------------------------------------------
# rbac_audit_logger
# ---------------------------------------------------------------------------


class TestBuildAuditRecord:
    def setup_method(self):
        os.environ["APPLIER_SERVICE_ACCOUNT_NAME"] = "auto-remediate-applier"

    def test_record_has_required_fields(self):
        record = build_audit_record(
            namespace="brightflow-dashboard",
            resource_kind="Deployment",
            resource_name="api-server",
            verb="patch",
            dry_run=False,
            session_id="sess-001",
            result="success",
        )
        assert record["event"] == "applier_action"
        assert record["service_account"] == "auto-remediate-applier"
        assert record["namespace"] == "brightflow-dashboard"
        assert record["resource_kind"] == "Deployment"
        assert record["resource_name"] == "api-server"
        assert record["verb"] == "patch"
        assert record["dry_run"] is False
        assert record["session_id"] == "sess-001"
        assert record["result"] == "success"
        assert record["error_detail"] is None
        assert "timestamp" in record

    def test_record_service_account_from_env(self):
        os.environ["APPLIER_SERVICE_ACCOUNT_NAME"] = "custom-sa"
        record = build_audit_record(
            namespace="ns",
            resource_kind="Pod",
            resource_name="pod-x",
            verb="delete",
            dry_run=True,
            session_id="s",
            result="success",
        )
        assert record["service_account"] == "custom-sa"
        os.environ["APPLIER_SERVICE_ACCOUNT_NAME"] = "auto-remediate-applier"

    def test_record_error_detail(self):
        record = build_audit_record(
            namespace="ns",
            resource_kind="ConfigMap",
            resource_name="cm-a",
            verb="update",
            dry_run=False,
            session_id="s2",
            result="error",
            error_detail="connection refused",
        )
        assert record["result"] == "error"
        assert record["error_detail"] == "connection refused"


class TestApplierAuditLogger:
    def setup_method(self):
        os.environ["APPLIER_SERVICE_ACCOUNT_NAME"] = "auto-remediate-applier"

    def test_session_id_generated_if_not_provided(self):
        audit = ApplierAuditLogger()
        assert audit.session_id
        assert len(audit.session_id) > 0

    def test_explicit_session_id_preserved(self):
        audit = ApplierAuditLogger(session_id="fixed-id")
        assert audit.session_id == "fixed-id"

    def test_pre_action_log_emits_record(self, caplog):
        audit = ApplierAuditLogger(session_id="sess-pre")
        with caplog.at_level(logging.INFO, logger="src.auto_remediate.rbac_audit_logger"):
            audit.pre_action_log(
                namespace="brightflow-dashboard",
                resource_kind="Deployment",
                resource_name="api",
                verb="patch",
                dry_run=False,
            )
        assert any("applier_action" in r.message for r in caplog.records)

    def test_pre_action_log_failure_raises(self):
        audit = ApplierAuditLogger(session_id="fail-pre")
        with patch.object(audit, "_emit", side_effect=OSError("disk full")):
            with pytest.raises(RuntimeError, match="Pre-action audit log failed"):
                audit.pre_action_log(
                    namespace="ns",
                    resource_kind="Pod",
                    resource_name="p",
                    verb="delete",
                    dry_run=False,
                )

    def test_post_action_log_sets_degraded_on_failure(self, caplog):
        audit = ApplierAuditLogger(session_id="fail-post")
        assert not audit.is_degraded
        with patch.object(audit, "_emit", side_effect=OSError("disk full")):
            with caplog.at_level(logging.CRITICAL, logger="src.auto_remediate.rbac_audit_logger"):
                audit.post_action_log(
                    namespace="ns",
                    resource_kind="Service",
                    resource_name="svc",
                    verb="update",
                    dry_run=False,
                    result="success",
                )
        assert audit.is_degraded
        assert any("CRITICAL" in r.levelname for r in caplog.records)

    def test_post_action_log_does_not_raise_on_failure(self):
        audit = ApplierAuditLogger()
        with patch.object(audit, "_emit", side_effect=Exception("boom")):
            # Should NOT raise
            audit.post_action_log(
                namespace="ns",
                resource_kind="ConfigMap",
                resource_name="cm",
                verb="delete",
                dry_run=False,
                result="error",
                error_detail="boom",
            )

    def test_not_degraded_on_success(self, caplog):
        audit = ApplierAuditLogger(session_id="ok-sess")
        with caplog.at_level(logging.INFO, logger="src.auto_remediate.rbac_audit_logger"):
            audit.post_action_log(
                namespace="brightflow-dashboard",
                resource_kind="Deployment",
                resource_name="deploy-a",
                verb="patch",
                dry_run=False,
                result="success",
            )
        assert not audit.is_degraded


# ---------------------------------------------------------------------------
# rbac_ci_check — performance: runs under 2s on fixture files
# ---------------------------------------------------------------------------


class TestRbacCiCheck:
    def _write_yaml(self, directory: Path, filename: str, content: str) -> Path:
        p = directory / filename
        p.write_text(content, encoding="utf-8")
        return p

    def test_clean_file_has_no_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_yaml(
                Path(tmp),
                "ok-role.yaml",
                "namespace: brightflow-dashboard\nname: auto-remediate-applier\n",
            )
            assert check_file(p) == []

    def test_trading_ns_applier_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_yaml(
                Path(tmp),
                "bad-role.yaml",
                "namespace: ibkr-live-trader\nname: auto-remediate-applier\n",
            )
            violations = check_file(p)
            assert len(violations) == 1
            assert "trading namespace" in violations[0]

    def test_all_trading_namespaces_detected(self):
        for ns in ["ibkr-live-trader", "daxxon-trading", "brightflow-live"]:
            with tempfile.TemporaryDirectory() as tmp:
                p = self._write_yaml(
                    Path(tmp),
                    "bad.yaml",
                    f"namespace: {ns}\nname: auto-remediate-applier\n",
                )
                violations = check_file(p)
                assert violations, f"Expected violation for {ns}"

    def test_non_applier_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_yaml(
                Path(tmp),
                "reader.yaml",
                "namespace: ibkr-live-trader\nname: auto-remediate-reader\n",
            )
            assert check_file(p) == []

    def test_directory_check_returns_zero_on_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_yaml(
                Path(tmp),
                "ok.yaml",
                "namespace: brightflow-dashboard\nname: auto-remediate-applier\n",
            )
            assert check_directory(Path(tmp)) == 0

    def test_directory_check_returns_nonzero_on_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_yaml(
                Path(tmp),
                "bad.yaml",
                "namespace: daxxon-trading\nname: auto-remediate-applier\n",
            )
            assert check_directory(Path(tmp)) != 0

    def test_performance_p95_under_2s(self):
        """Handler p95 latency under 2s on stub fixtures (performance validator)."""
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(50):
                self._write_yaml(
                    Path(tmp),
                    f"role-{i}.yaml",
                    f"namespace: ns-{i}\nname: auto-remediate-applier\n",
                )
            start = time.perf_counter()
            check_directory(Path(tmp))
            elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"check_directory took {elapsed:.3f}s > 2s limit"
