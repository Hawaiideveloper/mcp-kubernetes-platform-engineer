# Section 06 — Trading Namespace Hardblock and Safety Allowlist

## Context

This cluster hosts live trading systems. Unattended mutations to these systems can cause
financial loss, corrupt order state, or sever broker connections. The safety gate is
non-negotiable and must be the first check executed before any mutating action.

---

## 1. Hardblock List

Blocked namespaces are defined in `config/safety.yaml` (see Section 3). They are NOT
hardcoded in Python source. The config ships with these defaults:

```yaml
trading_namespaces:
  exact: [ibkr-live-trader, daxxon-trading, brightflow-live]
  pattern: ["*-live", "*-trading", "*-trader", "ibkr-*"]
```

Pattern matching uses `fnmatch` semantics. New namespaces matching a pattern are blocked
automatically without a config change.

---

## 2. Namespace Category Mode Matrix

| Category      | Examples                                   | Auto-restart | Auto-merge | Auto-apply | Action                                      |
|---------------|--------------------------------------------|:------------:|:----------:|:----------:|---------------------------------------------|
| trading       | ibkr-live-trader, daxxon-trading, brightflow-live | NEVER   | NEVER      | NEVER      | Diagnose only; file PR with evidence; no auto-merge |
| stateless-web | brightflow-dashboard, *-ui                 | Allowed (ladder) | Allowed if sandbox-verified | Allowed | Rollback window required |
| batch         | cronjob-*, triton-inference                | Allowed      | Allowed for image migrations and probe tuning | Allowed | No open-order risk |
| system        | kube-system, calico-system, cert-manager   | NEVER        | NEVER      | NEVER      | Notify only; page on-call; never touch      |

**trading tier constraints:** read-only operations (`get`, `describe`, `logs`, `events`)
are permitted for evidence collection. All mutating operations are blocked unconditionally.
Sandbox verification does not override this block. PRs must be human-reviewed and
human-merged; automation must never trigger a merge.

**system tier constraints:** no operations of any kind, including dry-run writes. Emit a
structured alert and page on-call. Do not open PRs for system namespace issues.

---

## 3. Config Schema (`config/safety.yaml`)

```yaml
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

# Namespaces not matched by any category: pr_required, no auto-merge.
default_policy: pr_required

# Human override: operator sets enabled=true with a labeled PR + expiry.
# Automation must never set this flag.
override:
  enabled: false
  authorized_pr_label: "force-apply"
  authorized_by: ""      # operator GitHub handle; required when enabled=true
  expires_at: ""         # ISO-8601; gate rejects if now() > expires_at
```

The server refuses to start if this file is missing or unparseable. `SAFETY_CONFIG_PATH`
env var overrides the default path (`config/safety.yaml`).

---

## 4. SafetyGate Class

```python
# src/safety_gate.py
import fnmatch
from enum import Enum, auto
from typing import Literal
from .config import SafetyConfig
from .audit import AuditLog


class NamespaceCategory(Enum):
    TRADING = auto()
    SYSTEM = auto()
    STATELESS_WEB = auto()
    BATCH = auto()
    UNKNOWN = auto()


class SafetyGateError(PermissionError):
    def __init__(self, namespace: str, action: str, reason: str) -> None:
        self.namespace = namespace
        self.action = action
        self.reason = reason
        super().__init__(f"SafetyGate DENY | ns={namespace} action={action} | {reason}")


MUTATING_ACTIONS = frozenset({
    "apply", "patch", "delete", "restart", "rollout", "scale",
    "exec", "helm_upgrade", "helm_install", "helm_rollback", "auto_merge",
})


class SafetyGate:
    def __init__(self, config: SafetyConfig, audit: AuditLog) -> None:
        self._cfg = config
        self._audit = audit

    def _categorize(self, namespace: str) -> NamespaceCategory:
        def matches(ns, exact, patterns):
            return ns in exact or any(fnmatch.fnmatch(ns, p) for p in patterns)

        cfg = self._cfg
        if matches(namespace, cfg.trading_namespaces.exact, cfg.trading_namespaces.pattern):
            return NamespaceCategory.TRADING
        if matches(namespace, cfg.system_namespaces.exact, cfg.system_namespaces.pattern):
            return NamespaceCategory.SYSTEM
        if matches(namespace, cfg.stateless_web_namespaces.exact, cfg.stateless_web_namespaces.pattern):
            return NamespaceCategory.STATELESS_WEB
        if matches(namespace, cfg.batch_namespaces.exact, cfg.batch_namespaces.pattern):
            return NamespaceCategory.BATCH
        return NamespaceCategory.UNKNOWN

    def check(self, namespace: str, action: str, dry_run: bool = False) -> Literal[True]:
        """
        Raises SafetyGateError on deny. Never returns False.
        Every caller must invoke this before any mutating operation.
        """
        category = self._categorize(namespace)
        is_mutating = action in MUTATING_ACTIONS
        allowed, reason = True, "permitted"

        if category == NamespaceCategory.TRADING and is_mutating:
            allowed = False
            reason = (
                "trading namespace: mutating actions require human PR review; "
                "sandbox verification does not override this block"
            )
        elif category == NamespaceCategory.SYSTEM and is_mutating:
            allowed = False
            reason = "system namespace: all mutating actions blocked; page on-call"

        self._audit.log_gate_decision({
            "event": "gate_decision",
            "namespace": namespace,
            "action": action,
            "category": category.name,
            "allowed": allowed,
            "reason": reason,
            "dry_run": dry_run,
        })

        if not allowed:
            raise SafetyGateError(namespace, action, reason)
        return True
```

**Wiring:** `SafetyGate.check()` is called at the entry of every write-path function:
`execute_remediation`, `kubectl_apply`, `kubectl_delete`, `kubectl_scale`, `kubectl_patch`,
`kubectl_rollout`, `helm_install`, `helm_upgrade`, `helm_rollback`, `auto_merge_pr`.
The gate is instantiated once at startup and injected; never re-instantiated per request.

---

## 5. Audit Log Record

Every gate decision (allow and deny) emits this record to the append-only audit log
(see Section 18). If the audit log write fails, the gate denies the action and surfaces
the failure.

```json
{
  "event": "gate_decision",
  "timestamp": "<ISO-8601>",
  "namespace": "<str>",
  "action": "<str>",
  "category": "TRADING | SYSTEM | STATELESS_WEB | BATCH | UNKNOWN",
  "allowed": true,
  "reason": "<str>",
  "dry_run": false,
  "session_id": "<UUID or null>"
}
```

---

## 6. Override Escape Hatch

There is no automation path that bypasses the gate. The escape hatch is exclusively
human-driven:

1. Open a PR with the manifest change and a full evidence bundle.
2. Label the PR `force-apply`.
3. An authorized operator sets `override.enabled: true`, `authorized_by`, and
   `expires_at` (maximum 4 hours) in `config/safety.yaml` via a direct commit.
4. A second authorized operator approves and merges that commit.
5. The operator manually applies: `kubectl apply -f <manifest> --dry-run=server`, then
   `kubectl apply -f <manifest>`.
6. Immediately reset `override.enabled: false` and commit.

The gate code contains no override bypass path. There is no CLI flag, env var, or API
endpoint that enables auto-apply to a trading namespace.

---

## 7. Tests

```python
# tests/test_safety_gate.py

@pytest.mark.parametrize("ns", ["ibkr-live-trader", "daxxon-trading", "brightflow-live"])
@pytest.mark.parametrize("action", ["apply", "restart", "delete", "scale", "auto_merge"])
def test_trading_ns_blocks_mutating_actions(gate, ns, action):
    with pytest.raises(SafetyGateError) as exc_info:
        gate.check(namespace=ns, action=action)
    assert "trading namespace" in exc_info.value.reason

@pytest.mark.parametrize("ns", ["ibkr-live-trader", "daxxon-trading", "brightflow-live"])
def test_trading_ns_blocks_mutating_even_when_dry_run_false(gate, ns):
    # Sandbox verification (dry_run=False path) is not a bypass.
    with pytest.raises(SafetyGateError):
        gate.check(namespace=ns, action="apply", dry_run=False)

@pytest.mark.parametrize("ns", ["ibkr-live-trader", "daxxon-trading", "brightflow-live"])
def test_trading_ns_allows_read_only(gate, ns):
    gate.check(namespace=ns, action="get")      # must not raise
    gate.check(namespace=ns, action="logs")     # must not raise

@pytest.mark.parametrize("ns", ["payments-live", "algo-trader", "ibkr-paper"])
def test_pattern_matched_trading_ns_is_blocked(gate, ns):
    with pytest.raises(SafetyGateError):
        gate.check(namespace=ns, action="apply")

def test_system_ns_blocks_mutating(gate):
    with pytest.raises(SafetyGateError):
        gate.check(namespace="kube-system", action="apply")

def test_gate_logs_deny_decision(gate, mock_audit_log):
    with pytest.raises(SafetyGateError):
        gate.check(namespace="ibkr-live-trader", action="restart")
    call_args = mock_audit_log.log_gate_decision.call_args[0][0]
    assert call_args["allowed"] is False
    assert call_args["namespace"] == "ibkr-live-trader"

def test_gate_logs_allow_decision(gate, mock_audit_log):
    gate.check(namespace="brightflow-dashboard", action="restart")
    call_args = mock_audit_log.log_gate_decision.call_args[0][0]
    assert call_args["allowed"] is True
```
