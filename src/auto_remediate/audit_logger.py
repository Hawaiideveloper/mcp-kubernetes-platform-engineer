"""
audit_logger.py — Structured, append-only AuditLogger (PRD §01, Sprint 1).

Every remediation action and namespace-guard rejection is recorded as a
newline-delimited JSON entry.  The log file is opened in append mode so
entries are never overwritten.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_AUDIT_LOG = Path(os.getenv("AUDIT_LOG_PATH", "/var/log/mcp-audit.jsonl"))  # noqa: S108


class AuditLogger:
    """
    Thread-safe append-only audit log writer.

    Each log entry is a single JSON object written on one line (JSONL format).
    The file is created if it does not exist; existing content is preserved.

    Example usage::

        audit = AuditLogger()
        audit.record("namespace_guard_rejected", namespace="ibkr-live-trader",
                     caller="execute_remediation")
        audit.record("remediation_applied", namespace="staging",
                     action="restart", resource="pod/worker-0")
    """

    def __init__(self, log_path: Path | str | None = None) -> None:
        self._log_path = Path(log_path) if log_path else _DEFAULT_AUDIT_LOG
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(self, event: str, **fields: Any) -> dict[str, Any]:
        """
        Write a single audit entry to the log.

        Args:
            event: Short machine-readable event name, e.g. ``"remediation_applied"``.
            **fields: Arbitrary key/value pairs to include in the log entry.

        Returns:
            The dict that was serialised to the log (useful for testing).
        """
        entry: dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        line = json.dumps(entry, default=str)
        with self._lock:
            with self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return entry

    def record_guard_rejection(self, namespace: str, caller: str) -> dict[str, Any]:
        """Convenience wrapper for namespace-guard rejection events."""
        return self.record(
            "namespace_guard_rejected",
            namespace=namespace,
            caller=caller,
            severity="WARN",
        )

    def record_remediation(
        self,
        namespace: str,
        action: str,
        resource: str,
        outcome: str,
        **extra: Any,
    ) -> dict[str, Any]:
        """Convenience wrapper for remediation action events."""
        return self.record(
            "remediation_applied",
            namespace=namespace,
            action=action,
            resource=resource,
            outcome=outcome,
            **extra,
        )

    # ------------------------------------------------------------------
    # Inspection helpers (tests / diagnostics)
    # ------------------------------------------------------------------

    def read_entries(self) -> list[dict[str, Any]]:
        """Return all entries from the log as a list of dicts."""
        if not self._log_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    @property
    def log_path(self) -> Path:
        """Return the resolved path of the audit log file."""
        return self._log_path
