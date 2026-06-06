"""
audit_logger.py — PRD §18 compliant append-only audit logger.

Supports:
- JSONL append with fcntl advisory locking
- Rotation via reopen()
- All eight PRD action verbs validated
- Write failures caught and emitted to stderr without suppressing caller
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_DEFAULT_AUDIT_LOG = Path(os.getenv("AUDIT_LOG_PATH", "/var/log/mcp-audit.jsonl"))  # noqa: S108

VALID_ACTIONS = frozenset({
    "detect", "classify", "sandbox", "pr_open",
    "pr_merge", "restart", "observe", "escalate",
})

VALID_OUTCOMES = frozenset({"success", "failure", "skipped", "blocked"})


class AuditLogger:
    """
    Thread-safe, append-only audit log writer conforming to PRD §18.

    Supports both legacy .record() API and new .append() API.
    .reopen() handles log rotation (rename + SIGHUP pattern).
    """

    def __init__(self, log_path: Path | str | None = None) -> None:
        self._log_path = Path(log_path) if log_path else _DEFAULT_AUDIT_LOG
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fd: int = -1
        self._open_file()

    def _open_file(self) -> None:
        """Open (or re-open) the log file in append mode."""
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
        self._fd = os.open(str(self._log_path), flags, 0o644)

    def reopen(self) -> None:
        """
        Re-open the log file after external rotation (rename).
        Call this after the rotated file has been moved away.
        """
        with self._lock:
            self._open_file()

    def append(self, record: Dict[str, Any]) -> None:
        """
        Append one structured record dict to the JSONL log.

        Write failures emit to stderr but do NOT raise, so the
        underlying remediator action is not suppressed.
        """
        line = (json.dumps(record, default=str) + "\n").encode()
        try:
            with self._lock:
                fd = self._fd
                if fd < 0:
                    raise OSError("log file descriptor is closed")
                fcntl.flock(fd, fcntl.LOCK_EX)
                try:
                    os.write(fd, line)
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError as exc:
            print(
                json.dumps({"level": "ERROR", "msg": "audit_write_failed", "error": str(exc)}),
                file=sys.stderr,
            )

    def log_action(
        self,
        actor: str,
        action: str,
        target: Dict[str, str],
        finding_id: str,
        outcome: str,
        evidence_pointer: str,
        fix_id: Optional[str] = None,
        sandbox_id: Optional[str] = None,
        pr_url: Optional[str] = None,
        dpo_pair_url: Optional[str] = None,
    ) -> None:
        """Append a fully structured PRD §18.1.2 audit record."""
        if action not in VALID_ACTIONS:
            raise ValueError(f"Unknown action {action!r}; must be one of {VALID_ACTIONS}")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"Unknown outcome {outcome!r}")
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "actor": actor,
            "action": action,
            "target": target,
            "finding_id": finding_id,
            "fix_id": fix_id,
            "sandbox_id": sandbox_id,
            "pr_url": pr_url,
            "outcome": outcome,
            "evidence_pointer": evidence_pointer,
            "dpo_pair_url": dpo_pair_url,
        }
        self.append(record)

    # ------------------------------------------------------------------
    # Legacy API (preserved for existing callers)
    # ------------------------------------------------------------------

    def record(self, event: str, **fields: Any) -> Dict[str, Any]:
        """Legacy: write a single audit entry keyed by event name."""
        entry: Dict[str, Any] = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        self.append(entry)
        return entry

    def record_guard_rejection(self, namespace: str, caller: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        return self.record(
            "remediation_applied",
            namespace=namespace,
            action=action,
            resource=resource,
            outcome=outcome,
            **extra,
        )

    def read_entries(self) -> list[Dict[str, Any]]:
        if not self._log_path.exists():
            return []
        entries: list[Dict[str, Any]] = []
        with self._log_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    @property
    def log_path(self) -> Path:
        return self._log_path

    def __del__(self) -> None:
        if self._fd >= 0:
            try:
                os.close(self._fd)
            except OSError:
                pass
