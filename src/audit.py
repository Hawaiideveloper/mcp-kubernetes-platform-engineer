"""
Append-only audit log for SafetyGate decisions.

Every gate decision (allow and deny) is recorded here. If the write
fails, callers should surface the failure rather than silently continue.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class AuditLogError(RuntimeError):
    """Raised when the audit log cannot be written."""


class AuditLog:
    """Thread-safe, append-only structured audit log."""

    def __init__(
        self,
        log_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> None:
        self._path = Path(log_path) if log_path else None
        self._session_id = session_id

    def log_gate_decision(self, record: Dict[str, Any]) -> None:
        """
        Append a gate decision record.

        Raises AuditLogError if the write fails so the gate can deny
        the action rather than proceed silently.
        """
        enriched = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            **record,
        }
        line = json.dumps(enriched, default=str)

        # Always emit to structured logger
        if enriched.get("allowed"):
            logger.info("gate_decision allowed: %s", line)
        else:
            logger.warning("gate_decision denied: %s", line)

        # Optionally persist to a JSONL file
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                raise AuditLogError(
                    f"Audit log write failed ({self._path}): {exc}"
                ) from exc
