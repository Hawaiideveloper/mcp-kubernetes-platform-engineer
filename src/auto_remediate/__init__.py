"""
auto_remediate — Sprint 1 foundation package.

Exports the namespace guard, AuditLogger, and roadmap tracker that establish
the authoritative baseline documented in PRD §01 (Executive Summary & Roadmap).
"""

from .namespace_guard import (
    TRADING_BLOCKED_NAMESPACES,
    ProtectedNamespaceError,
    check_namespace_allowed,
)
from .audit_logger import AuditLogger
from .roadmap import SprintStatus, Roadmap

__all__ = [
    "TRADING_BLOCKED_NAMESPACES",
    "ProtectedNamespaceError",
    "check_namespace_allowed",
    "AuditLogger",
    "SprintStatus",
    "Roadmap",
]
