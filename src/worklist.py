"""SQLite-backed worklist with atomic claim for parallel audit-run agents."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CLAIM_UPDATE = """
UPDATE tasks
SET    status     = 'claimed',
       claimed_by  = ?,
       claimed_at  = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE  id = (
    SELECT t.id
    FROM   tasks t
    WHERE  t.status = 'queued'
      AND  NOT EXISTS (
               SELECT 1
               FROM   tasks b
               WHERE  b.id IN (SELECT value FROM json_each(t.blockers))
                 AND  b.status != 'done'
           )
    ORDER BY t.id
    LIMIT  1
)
RETURNING id, prd_section, title, blockers, deliverable_paths,
          status, claimed_by, claimed_at;
"""

_INIT_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS audit_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label       TEXT    NOT NULL UNIQUE,
    phase           TEXT    NOT NULL
                    CHECK (phase IN (
                        'review','synthesize','claim',
                        'implement','verify','done','escalate'
                    )),
    iteration_count INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    stopped_reason  TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    prd_section       TEXT    NOT NULL,
    title             TEXT    NOT NULL,
    blockers          TEXT    NOT NULL DEFAULT '[]',
    deliverable_paths TEXT    NOT NULL DEFAULT '[]',
    status            TEXT    NOT NULL DEFAULT 'queued'
                      CHECK (status IN
                          ('queued','claimed','in_progress',
                           'done','failed')),
    claimed_by        TEXT,
    claimed_at        TEXT,
    completed_at      TEXT,
    pr_url            TEXT,
    UNIQUE (prd_section, title)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
"""


@dataclass
class Task:
    id: int
    prd_section: str
    title: str
    blockers: list[int]
    deliverable_paths: list[str]
    status: str
    claimed_by: Optional[str]
    claimed_at: Optional[str]
    completed_at: Optional[str] = None
    pr_url: Optional[str] = None


@dataclass
class AuditRun:
    id: int
    run_label: str
    phase: str
    iteration_count: int
    started_at: str
    updated_at: str
    stopped_reason: Optional[str]


TERMINAL_PHASES = frozenset({"done", "escalate"})
MAX_ITERATIONS = 5


def should_escalate(iteration_count: int) -> bool:
    """Return True when iteration_count has reached the escalation threshold."""
    return iteration_count >= MAX_ITERATIONS


class WorklistDB:
    """Thread-safe SQLite worklist backed by WAL mode."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_INIT_DDL)

    # ------------------------------------------------------------------
    # Audit-run state machine
    # ------------------------------------------------------------------

    def ensure_audit_run(self, run_label: str) -> AuditRun:
        """Create the audit_run row if absent; return current state."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO audit_runs "
                "(run_label, phase, iteration_count, started_at, updated_at) "
                "VALUES (?, 'review', 0, ?, ?)",
                (run_label, now, now),
            )
            row = self._conn.execute(
                "SELECT * FROM audit_runs WHERE run_label = ?",
                (run_label,),
            ).fetchone()
        return self._row_to_run(row)

    def advance_phase(self, run_label: str, new_phase: str) -> AuditRun:
        """Move an audit-run to the next phase."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE audit_runs SET phase = ?, updated_at = ? "
                "WHERE run_label = ?",
                (new_phase, now, run_label),
            )
            row = self._conn.execute(
                "SELECT * FROM audit_runs WHERE run_label = ?",
                (run_label,),
            ).fetchone()
        return self._row_to_run(row)

    def increment_iteration(self, run_label: str) -> AuditRun:
        """Increment iteration_count and reset phase to 'review'."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE audit_runs "
                "SET iteration_count = iteration_count + 1, "
                "    phase = 'review', updated_at = ? "
                "WHERE run_label = ?",
                (now, run_label),
            )
            row = self._conn.execute(
                "SELECT * FROM audit_runs WHERE run_label = ?",
                (run_label,),
            ).fetchone()
        run = self._row_to_run(row)
        if should_escalate(run.iteration_count):
            return self.escalate(run_label, "iteration_count >= MAX_ITERATIONS")
        return run

    def escalate(self, run_label: str, reason: str) -> AuditRun:
        """Move run to escalate phase with a reason."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE audit_runs "
                "SET phase = 'escalate', stopped_reason = ?, updated_at = ? "
                "WHERE run_label = ?",
                (reason, now, run_label),
            )
            row = self._conn.execute(
                "SELECT * FROM audit_runs WHERE run_label = ?",
                (run_label,),
            ).fetchone()
        return self._row_to_run(row)

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    def claim_next(self, agent_id: str) -> Optional[Task]:
        """Atomically claim the lowest-id unblocked queued task.

        Returns None if no claimable task exists.
        Raises sqlite3.OperationalError on lock timeout (caller should retry).
        """
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                cur = self._conn.execute(_CLAIM_UPDATE, (agent_id,))
                row = cur.fetchone()
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

        if row is None:
            return None
        return self._row_to_task(row)

    def mark_in_progress(self, task_id: int, agent_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status='in_progress' "
                "WHERE id=? AND claimed_by=?",
                (task_id, agent_id),
            )

    def complete(self, task_id: int, agent_id: str, pr_url: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status='done', completed_at=?, pr_url=? "
                "WHERE id=? AND claimed_by=?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    pr_url,
                    task_id,
                    agent_id,
                ),
            )

    def fail(self, task_id: int, agent_id: str, reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status='failed', completed_at=?, pr_url=? "
                "WHERE id=? AND claimed_by=?",
                (
                    datetime.now(timezone.utc).isoformat(),
                    f"FAILED: {reason}",
                    task_id,
                    agent_id,
                ),
            )

    def seed(self, tasks: list[dict]) -> None:  # type: ignore[type-arg]
        """Insert tasks (idempotent — skips rows where (prd_section, title) exists)."""
        with self._lock:
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO tasks
                    (prd_section, title, blockers, deliverable_paths)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        t["prd_section"],
                        t["title"],
                        json.dumps(t.get("blockers", [])),
                        json.dumps(t.get("deliverable_paths", [])),
                    )
                    for t in tasks
                ],
            )

    def count_by_status(self) -> dict[str, int]:
        """Return counts keyed by status string."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) FROM tasks GROUP BY status"
            ).fetchall()
        return {r[0]: r[1] for r in rows}

    # ------------------------------------------------------------------
    # Row converters
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            prd_section=row["prd_section"],
            title=row["title"],
            blockers=json.loads(row["blockers"]),
            deliverable_paths=json.loads(row["deliverable_paths"]),
            status=row["status"],
            claimed_by=row["claimed_by"],
            claimed_at=row["claimed_at"],
        )

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> AuditRun:
        return AuditRun(
            id=row["id"],
            run_label=row["run_label"],
            phase=row["phase"],
            iteration_count=row["iteration_count"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            stopped_reason=row["stopped_reason"],
        )
