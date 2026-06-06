"""
SafetyGate — trading namespace hardblock and safety allowlist.

Every mutating operation MUST call SafetyGate.check() before proceeding.
The gate is instantiated once at startup and injected; never re-instantiated
per request.

Wired entry points that MUST call check() before any mutation:
  execute_remediation, kubectl_apply, kubectl_delete, kubectl_scale,
  kubectl_patch, kubectl_rollout, helm_install, helm_upgrade,
  helm_rollback, auto_merge_pr.
"""

import fnmatch
from enum import Enum, auto
from typing import Literal

try:
    from .audit import AuditLog
    from .safety_config import SafetyConfig
except ImportError:
    from audit import AuditLog  # type: ignore[no-redef]
    from safety_config import SafetyConfig  # type: ignore[no-redef]


class NamespaceCategory(Enum):
    TRADING = auto()
    SYSTEM = auto()
    STATELESS_WEB = auto()
    BATCH = auto()
    UNKNOWN = auto()


class SafetyGateError(PermissionError):
    """Raised when the safety gate denies a mutating action."""

    def __init__(self, namespace: str, action: str, reason: str) -> None:
        self.namespace = namespace
        self.action = action
        self.reason = reason
        super().__init__(
            f"SafetyGate DENY | ns={namespace} action={action} | {reason}"
        )


# All actions the gate considers mutating. Read-only actions (get, list,
# describe, logs, events, watch) are not in this set and are always permitted.
MUTATING_ACTIONS: frozenset[str] = frozenset(
    {
        "apply",
        "patch",
        "delete",
        "restart",
        "rollout",
        "scale",
        "exec",
        "helm_upgrade",
        "helm_install",
        "helm_rollback",
        "auto_merge",
    }
)


class SafetyGate:
    """
    First-check safety gate for all mutating Kubernetes operations.

    Trading namespaces: mutating actions are blocked unconditionally.
    System namespaces: all mutating actions blocked; alert on-call.
    All other namespaces: allowed subject to policy in SafetyConfig.

    There is no automation bypass path. Override is exclusively human-driven
    via PR + labeled commit; this class contains no override bypass logic.
    """

    def __init__(self, config: SafetyConfig, audit: AuditLog) -> None:
        self._cfg = config
        self._audit = audit

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _categorize(self, namespace: str) -> NamespaceCategory:
        def matches(ns: str, exact: list, patterns: list) -> bool:
            return ns in exact or any(fnmatch.fnmatch(ns, p) for p in patterns)

        cfg = self._cfg
        if matches(
            namespace,
            cfg.trading_namespaces.exact,
            cfg.trading_namespaces.pattern,
        ):
            return NamespaceCategory.TRADING
        if matches(
            namespace,
            cfg.system_namespaces.exact,
            cfg.system_namespaces.pattern,
        ):
            return NamespaceCategory.SYSTEM
        if matches(
            namespace,
            cfg.stateless_web_namespaces.exact,
            cfg.stateless_web_namespaces.pattern,
        ):
            return NamespaceCategory.STATELESS_WEB
        if matches(
            namespace,
            cfg.batch_namespaces.exact,
            cfg.batch_namespaces.pattern,
        ):
            return NamespaceCategory.BATCH
        return NamespaceCategory.UNKNOWN

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def categorize(self, namespace: str) -> NamespaceCategory:
        """Expose categorization for diagnostics (read-only; never mutates)."""
        return self._categorize(namespace)

    def check(
        self,
        namespace: str,
        action: str,
        dry_run: bool = False,
    ) -> Literal[True]:
        """
        Check whether the action is permitted in the given namespace.

        Returns True on success. Raises SafetyGateError on deny.
        Never returns False.

        Every caller must invoke this before any mutating operation.
        If the audit log write fails, the gate raises AuditLogError so
        the action is denied rather than proceeding silently.
        """
        category = self._categorize(namespace)
        is_mutating = action in MUTATING_ACTIONS
        allowed: bool = True
        reason: str = "permitted"

        if category == NamespaceCategory.TRADING and is_mutating:
            allowed = False
            reason = (
                "trading namespace: mutating actions require human PR review; "
                "sandbox verification does not override this block"
            )
        elif category == NamespaceCategory.SYSTEM and is_mutating:
            allowed = False
            reason = "system namespace: all mutating actions blocked; page on-call"

        self._audit.log_gate_decision(
            {
                "event": "gate_decision",
                "namespace": namespace,
                "action": action,
                "category": category.name,
                "allowed": allowed,
                "reason": reason,
                "dry_run": dry_run,
            }
        )

        if not allowed:
            raise SafetyGateError(namespace, action, reason)
        return True
