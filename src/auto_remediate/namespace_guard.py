"""
namespace_guard.py — Trading-namespace hardblock (PRD §01, Sprint 1).

Provides a constant set of protected namespaces, a custom exception, and a
guard function that MUST be called before any remediation action is applied.
No remediation path may bypass this check.
"""

from __future__ import annotations

from typing import Iterable

# Canonical list of namespaces that must never be auto-remediated.
# Extending this list is a deliberate, reviewed change — do not add
# namespaces programmatically at runtime.
TRADING_BLOCKED_NAMESPACES: frozenset[str] = frozenset(
    {
        "ibkr-live-trader",
        "daxxon-trading",
        "brightflow-live",
    }
)


class ProtectedNamespaceError(Exception):
    """
    Raised when a caller attempts to run remediation against a protected namespace.

    Attributes:
        namespace: The namespace that triggered the guard.
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        super().__init__(
            f"Namespace '{namespace}' is in the protected trading-namespace block. "
            "Automated remediation is not permitted. Use a manual break-glass procedure."
        )


def check_namespace_allowed(
    namespace: str,
    extra_blocked: Iterable[str] | None = None,
) -> None:
    """
    Assert that *namespace* is not in the protected set.

    Args:
        namespace: Kubernetes namespace to check.
        extra_blocked: Optional additional namespaces to block for this call
            (e.g. loaded from an env-var allowlist at startup).

    Raises:
        ProtectedNamespaceError: If *namespace* is blocked.
        ValueError: If *namespace* is empty or not a string.
    """
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError(f"namespace must be a non-empty string, got: {namespace!r}")

    blocked = TRADING_BLOCKED_NAMESPACES
    if extra_blocked is not None:
        blocked = blocked | frozenset(extra_blocked)

    if namespace in blocked:
        raise ProtectedNamespaceError(namespace)
