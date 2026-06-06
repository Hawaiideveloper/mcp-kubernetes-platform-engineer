"""Four-identity RBAC split definitions for auto-remediate (US-019).

Defines the four service identities:
  - reader: cluster-wide read-only, used by analyzer/watcher/classifier
  - applier: namespace-scoped write, per non-trading namespace
  - sandbox: full write inside sandbox-* namespaces only
  - pr-bot: no k8s RBAC, github API only
"""
from __future__ import annotations

from enum import Enum


TRADING_NAMESPACES: frozenset[str] = frozenset(
    ["ibkr-live-trader", "daxxon-trading", "brightflow-live"]
)

SYSTEM_NAMESPACES: frozenset[str] = frozenset(
    ["kube-system", "kube-public", "kube-node-lease", "auto-remediate"]
)


class RbacIdentity(str, Enum):
    """The four recognised service identities."""

    READER = "auto-remediate-reader"
    APPLIER = "auto-remediate-applier"
    SANDBOX = "auto-remediate-sandbox"
    PR_BOT = "auto-remediate-pr-bot"


def is_trading_namespace(namespace: str) -> bool:
    """Return True if *namespace* is a trading namespace.

    Trading namespaces must never have an applier binding. This check is
    the code-level enforcement; RBAC absence is the cluster-level enforcement.
    """
    return namespace in TRADING_NAMESPACES


def is_system_namespace(namespace: str) -> bool:
    """Return True if *namespace* is a system or auto-remediate namespace."""
    return namespace in SYSTEM_NAMESPACES


def is_sandbox_namespace(namespace: str) -> bool:
    """Return True if *namespace* matches the sandbox-* pattern."""
    return namespace.startswith("sandbox-")


def is_applier_eligible(namespace: str) -> bool:
    """Return True if an applier Role/RoleBinding may be created for *namespace*.

    A namespace is applier-eligible only when it is:
      - not a trading namespace
      - not a system namespace
      - not a sandbox namespace (sandbox uses its own identity)
    """
    return (
        not is_trading_namespace(namespace)
        and not is_system_namespace(namespace)
        and not is_sandbox_namespace(namespace)
    )


def validate_no_applier_in_trading(namespace: str) -> None:
    """Raise ValueError if an applier binding would be created in a trading namespace.

    This must be called before any Role or RoleBinding creation for the applier
    identity. It is a secondary software gate; the absence of RBAC is the primary gate.
    """
    if is_trading_namespace(namespace):
        raise ValueError(
            f"Applier identity MUST NOT be bound in trading namespace '{namespace}'. "
            "Create an explicit security review record before changing this constraint."
        )
