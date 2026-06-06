"""
Tests for US-006: Trading namespace hardblock and safety allowlist.

pytest -k US-006 -v
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src/ is on path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from safety_config import SafetyConfig
from safety_gate import (
    AuditLog,
    NamespaceCategory,
    SafetyGate,
    SafetyGateError,
    MUTATING_ACTIONS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_YAML = """\
version: "1"

trading_namespaces:
  exact: [ibkr-live-trader, daxxon-trading, brightflow-live]
  pattern: ["*-live", "*-trading", "*-trader", "ibkr-*"]

system_namespaces:
  exact: [kube-system, kube-public, kube-node-lease, calico-system, cert-manager, ingress-nginx]
  pattern: []

stateless_web_namespaces:
  exact: [brightflow-dashboard]
  pattern: ["*-dashboard", "*-ui"]

batch_namespaces:
  exact: [triton-inference]
  pattern: ["cronjob-*", "*-batch", "*-jobs"]

default_policy: pr_required

override:
  enabled: false
  authorized_pr_label: "force-apply"
  authorized_by: ""
  expires_at: ""
"""


@pytest.fixture(scope="module")
def safety_config_file(tmp_path_factory):
    """Write minimal safety.yaml to a temp file; return its path."""
    p = tmp_path_factory.mktemp("cfg") / "safety.yaml"
    p.write_text(MINIMAL_YAML, encoding="utf-8")
    return str(p)


@pytest.fixture(scope="module")
def safety_cfg(safety_config_file):
    return SafetyConfig.load(safety_config_file)


@pytest.fixture()
def mock_audit_log():
    mock = MagicMock(spec=AuditLog)
    return mock


@pytest.fixture()
def gate(safety_cfg, mock_audit_log):
    return SafetyGate(config=safety_cfg, audit=mock_audit_log)


# ---------------------------------------------------------------------------
# US-006 — Trading namespace exact-match blocking
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ns",
    ["ibkr-live-trader", "daxxon-trading", "brightflow-live"],
)
@pytest.mark.parametrize(
    "action",
    ["apply", "restart", "delete", "scale", "auto_merge"],
)
def test_US_006_trading_ns_blocks_mutating_actions(gate, ns, action):
    """Exact-match trading namespaces must block all mutating actions."""
    with pytest.raises(SafetyGateError) as exc_info:
        gate.check(namespace=ns, action=action)
    assert "trading namespace" in exc_info.value.reason


@pytest.mark.parametrize(
    "ns",
    ["ibkr-live-trader", "daxxon-trading", "brightflow-live"],
)
def test_US_006_trading_ns_blocks_mutating_even_when_dry_run_false(gate, ns):
    """dry_run=False is not a bypass for trading namespaces."""
    with pytest.raises(SafetyGateError):
        gate.check(namespace=ns, action="apply", dry_run=False)


@pytest.mark.parametrize(
    "ns",
    ["ibkr-live-trader", "daxxon-trading", "brightflow-live"],
)
def test_US_006_trading_ns_allows_read_only(gate, ns):
    """Read-only actions must be allowed in trading namespaces."""
    gate.check(namespace=ns, action="get")
    gate.check(namespace=ns, action="logs")
    gate.check(namespace=ns, action="describe")
    gate.check(namespace=ns, action="events")


# ---------------------------------------------------------------------------
# US-006 — Trading namespace pattern matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ns",
    [
        "payments-live",      # *-live
        "algo-trader",        # *-trader
        "fx-trading",         # *-trading
        "ibkr-paper",         # ibkr-*
    ],
)
def test_US_006_pattern_matched_trading_ns_is_blocked(gate, ns):
    """Pattern-matched trading namespaces must be blocked for mutations."""
    with pytest.raises(SafetyGateError):
        gate.check(namespace=ns, action="apply")


# ---------------------------------------------------------------------------
# US-006 — System namespace blocking
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "ns",
    ["kube-system", "calico-system", "cert-manager", "ingress-nginx"],
)
def test_US_006_system_ns_blocks_mutating(gate, ns):
    """System namespaces must block all mutating actions."""
    with pytest.raises(SafetyGateError) as exc_info:
        gate.check(namespace=ns, action="apply")
    assert "system namespace" in exc_info.value.reason


# ---------------------------------------------------------------------------
# US-006 — Audit log records
# ---------------------------------------------------------------------------

def test_US_006_gate_logs_deny_decision(gate, mock_audit_log):
    """Deny decisions must be written to the audit log with correct fields."""
    with pytest.raises(SafetyGateError):
        gate.check(namespace="ibkr-live-trader", action="restart")
    call_args = mock_audit_log.log_gate_decision.call_args[0][0]
    assert call_args["allowed"] is False
    assert call_args["namespace"] == "ibkr-live-trader"
    assert call_args["event"] == "gate_decision"
    assert call_args["category"] == "TRADING"


def test_US_006_gate_logs_allow_decision(gate, mock_audit_log):
    """Allow decisions must also be written to the audit log."""
    gate.check(namespace="brightflow-dashboard", action="restart")
    call_args = mock_audit_log.log_gate_decision.call_args[0][0]
    assert call_args["allowed"] is True
    assert call_args["namespace"] == "brightflow-dashboard"
    assert call_args["event"] == "gate_decision"


# ---------------------------------------------------------------------------
# US-006 — Stateless-web and batch namespaces are allowed for mutations
# ---------------------------------------------------------------------------

def test_US_006_stateless_web_allows_mutations(gate):
    """Stateless-web namespaces must allow mutating actions."""
    gate.check(namespace="brightflow-dashboard", action="apply")
    gate.check(namespace="my-dashboard", action="scale")
    gate.check(namespace="frontend-ui", action="restart")


def test_US_006_batch_allows_mutations(gate):
    """Batch namespaces must allow mutating actions."""
    gate.check(namespace="triton-inference", action="apply")
    gate.check(namespace="cronjob-nightly", action="scale")
    gate.check(namespace="data-batch", action="apply")


# ---------------------------------------------------------------------------
# US-006 — SafetyGateError carries metadata
# ---------------------------------------------------------------------------

def test_US_006_safety_gate_error_attributes():
    """SafetyGateError must expose namespace, action, and reason attributes."""
    err = SafetyGateError("ibkr-live-trader", "apply", "test reason")
    assert err.namespace == "ibkr-live-trader"
    assert err.action == "apply"
    assert err.reason == "test reason"
    assert "SafetyGate DENY" in str(err)


# ---------------------------------------------------------------------------
# US-006 — MUTATING_ACTIONS completeness
# ---------------------------------------------------------------------------

def test_US_006_mutating_actions_set_contains_required_operations():
    """MUTATING_ACTIONS must include all write-path entry points."""
    required = {
        "apply", "patch", "delete", "restart", "rollout", "scale",
        "exec", "helm_upgrade", "helm_install", "helm_rollback", "auto_merge",
    }
    assert required.issubset(MUTATING_ACTIONS)


# ---------------------------------------------------------------------------
# US-006 — SafetyConfig loading
# ---------------------------------------------------------------------------

def test_US_006_config_loads_trading_namespaces(safety_cfg):
    """Loaded config must include known exact trading namespaces."""
    assert "ibkr-live-trader" in safety_cfg.trading_namespaces.exact
    assert "daxxon-trading" in safety_cfg.trading_namespaces.exact
    assert "brightflow-live" in safety_cfg.trading_namespaces.exact


def test_US_006_config_loads_trading_patterns(safety_cfg):
    """Loaded config must include fnmatch patterns for trading namespaces."""
    assert "*-live" in safety_cfg.trading_namespaces.pattern
    assert "ibkr-*" in safety_cfg.trading_namespaces.pattern


def test_US_006_config_missing_file_raises_runtime_error(tmp_path):
    """Server must refuse to start if safety.yaml is missing."""
    with pytest.raises(RuntimeError, match="not found"):
        SafetyConfig.load(str(tmp_path / "nonexistent.yaml"))


def test_US_006_config_unparseable_raises_runtime_error(tmp_path):
    """Server must refuse to start if safety.yaml is unparseable."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(": : : invalid yaml :::", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unparseable"):
        SafetyConfig.load(str(bad))


def test_US_006_config_override_disabled_by_default(safety_cfg):
    """Override must default to disabled."""
    assert safety_cfg.override.enabled is False


# ---------------------------------------------------------------------------
# US-006 — Categorize helper exposed for diagnostics
# ---------------------------------------------------------------------------

def test_US_006_categorize_returns_trading_for_exact(gate):
    assert gate.categorize("ibkr-live-trader") == NamespaceCategory.TRADING


def test_US_006_categorize_returns_system_for_kube_system(gate):
    assert gate.categorize("kube-system") == NamespaceCategory.SYSTEM


def test_US_006_categorize_returns_unknown_for_unmatched(gate):
    assert gate.categorize("my-random-app") == NamespaceCategory.UNKNOWN


# ---------------------------------------------------------------------------
# US-006 — check() return value on allow
# ---------------------------------------------------------------------------

def test_US_006_check_returns_true_on_allow(gate):
    """check() must return exactly True (not a truthy value) on allow."""
    result = gate.check(namespace="brightflow-dashboard", action="apply")
    assert result is True
