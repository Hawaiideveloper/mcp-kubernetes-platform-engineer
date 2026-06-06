"""
finding_store.py — PRD §18.2 SQLite-backed finding persistence with dedup.

WAL mode + async writer via aiosqlite.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS findings (
    id                TEXT PRIMARY KEY,
    fingerprint_sha256 TEXT NOT NULL UNIQUE,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    occurrence_count  INTEGER NOT NULL DEFAULT 1,
    ns                TEXT NOT NULL,
    kind              TEXT NOT NULL,
    name              TEXT NOT NULL,
    severity          TEXT NOT NULL CHECK(severity IN ('critical','high','medium','low','info')),
    status            TEXT NOT NULL DEFAULT 'open'
                          CHECK(status IN ('open','in_pr','resolved','escalated')),
    current_pr_url    TEXT,
    root_cause_hash   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_findings_ns       ON findings(ns);
CREATE INDEX IF NOT EXISTS idx_findings_status   ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_last_seen ON findings(last_seen);
"""


def _fingerprint(
    ns: str, kind: str, name: str, severity: str, root_cause_hash: str
) -> str:
    raw = f"{ns}|{kind}|{name}|{severity}|{root_cause_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def upsert_finding(
    db: Any,
    ns: str,
    kind: str,
    name: str,
    severity: str,
    root_cause_hash: str,
    **extra: Any,
) -> str:
    """
    Insert a new finding or increment occurrence_count on duplicate.

    Returns the fingerprint SHA-256.
    """
    fp = _fingerprint(ns, kind, name, severity, root_cause_hash)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO findings
            (id, fingerprint_sha256, first_seen, last_seen,
             occurrence_count, ns, kind, name, severity, status, root_cause_hash)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'open', ?)
        ON CONFLICT(fingerprint_sha256) DO UPDATE SET
            last_seen        = excluded.last_seen,
            occurrence_count = occurrence_count + 1
        """,
        (uuid.uuid4().hex, fp, now, now, ns, kind, name, severity, root_cause_hash),
    )
    await db.commit()
    return fp


async def get_finding_by_fingerprint(db: Any, fp: str) -> Optional[dict]:
    """Return a finding row as a dict, or None."""
    async with db.execute(
        "SELECT * FROM findings WHERE fingerprint_sha256 = ?", (fp,)
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


async def get_finding_by_id(db: Any, finding_id: str) -> Optional[dict]:
    """Return a finding row by id (uuid hex) as a dict, or None."""
    async with db.execute(
        "SELECT * FROM findings WHERE id = ?", (finding_id,)
    ) as cur:
        row = await cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
