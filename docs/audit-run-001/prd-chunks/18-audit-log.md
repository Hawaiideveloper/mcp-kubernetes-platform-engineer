# Section 18 — Audit Log, Finding Persistence, and Deduplication

## Overview

The auto-remediator touches production resources. Every action it takes must
be traceable to a specific actor, timestamp, target, and evidence snapshot.
This section specifies the immutable audit log, the persistent finding store,
and the deduplication contract that prevents alert storms from generating
redundant work orders.

---

## 18.1 Audit Log

### 18.1.1 Requirement

Every discrete action taken by the remediator pipeline appends exactly one
structured record to the audit log before the action's return path completes.
The covered action verbs are:

- `detect` — analyzer emits a finding
- `classify` — severity and fix-class assigned
- `sandbox` — fix applied to ephemeral namespace
- `pr_open` — GitHub PR created
- `pr_merge` — PR merged by auto-approver
- `restart` — workload or node component restarted
- `observe` — health probe outcome recorded post-action
- `escalate` — paged to on-call; no automated action taken

Write failures must not suppress the underlying action. The writer wraps each
`append` in a `try/except OSError` and emits a structured error to stderr.

### 18.1.2 Record Schema

One JSONL line per action. All fields are required unless marked optional.

```jsonc
{
  "timestamp":       "2026-06-02T14:31:07.412Z",   // UTC ISO-8601 with ms
  "actor":           "remediator/sa-auto-fix",      // service-account or human email
  "action":          "pr_open",                     // one of the eight verbs above
  "target": {
    "kind":          "Deployment",
    "namespace":     "payments",
    "name":          "checkout-api"
  },
  "finding_id":      "find_7f3a2b",                 // FK to findings table
  "fix_id":          "fix_19cc44",                  // optional; null before fix exists
  "sandbox_id":      "sb_a1b2c3",                   // optional; null outside sandbox phase
  "pr_url":          "https://github.com/…/pull/42",// optional; null before pr_open
  "outcome":         "success",                     // success | failure | skipped | blocked
  "evidence_pointer":"s3://audit-evidence/find_7f3a2b/pod-events.json",
  "dpo_pair_url":    "s3://dpo-pairs/find_7f3a2b.jsonl" // optional; written after resolution
}
```

Field constraints:

| Field | Type | Notes |
|---|---|---|
| `timestamp` | string | `datetime.utcnow().isoformat() + "Z"` |
| `actor` | string | service-account path or `user:<email>` |
| `action` | string | constrained to the eight verbs; ValueError on unknown |
| `target.kind` | string | Kubernetes GroupVersionKind short form |
| `finding_id` | string | 8-char hex prefix of fingerprint SHA-256 |
| `outcome` | string | constrained enum; see above |
| `evidence_pointer` | string | GCS URI written before the record |

### 18.1.3 Storage

**Primary path:** `/var/log/auto-remediate/audit.jsonl`

- Append-only. The writer opens with `O_WRONLY | O_APPEND | O_CREAT`.
- File-level advisory lock (`fcntl.flock(fd, LOCK_EX)`) guards concurrent writers.
- The directory is backed by a `PersistentVolume` (ReadWriteOnce, `storageClass: standard-retain`).

**Rotation:** Daily at 00:00 UTC via a `CronJob` that renames
`audit.jsonl` → `audit.jsonl.YYYYMMDD` and sends SIGHUP to the writer
process. The writer reopens the file after catching SIGHUP.

**Retention:**
- 90 days online on the PV.
- On day 91, a second `CronJob` compresses each rotated file with `gzip -9`
  and uploads it to `gs://org-audit-archive/auto-remediate/YYYY/MM/DD/`.
- Local compressed copy deleted after upload confirmed (exit 0 from `gsutil cp`).

```yaml
# PVC definition (abbreviated)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: audit-log-pvc
  namespace: auto-remediate
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: standard-retain
  resources:
    requests:
      storage: 50Gi
```

---

## 18.2 Finding Persistence

### 18.2.1 SQLite Table: `findings`

The findings store is a WAL-mode SQLite database at
`/var/lib/auto-remediate/findings.db`, also PV-backed (same claim or a
sibling PVC). WAL mode ensures readers never block writers.

```sql
CREATE TABLE IF NOT EXISTS findings (
    id                TEXT PRIMARY KEY,          -- uuid4 hex, no dashes
    fingerprint_sha256 TEXT NOT NULL UNIQUE,     -- sha256(ns+kind+name+severity+root_cause)
    first_seen        TEXT NOT NULL,             -- UTC ISO-8601
    last_seen         TEXT NOT NULL,             -- updated on each recurrence
    occurrence_count  INTEGER NOT NULL DEFAULT 1,
    ns                TEXT NOT NULL,
    kind              TEXT NOT NULL,
    name              TEXT NOT NULL,
    severity          TEXT NOT NULL CHECK(severity IN ('critical','high','medium','low','info')),
    status            TEXT NOT NULL DEFAULT 'open'
                          CHECK(status IN ('open','in_pr','resolved','escalated')),
    current_pr_url    TEXT,                      -- null until pr_open action
    root_cause_hash   TEXT NOT NULL              -- sha256 of normalized root-cause string
);

CREATE INDEX IF NOT EXISTS idx_findings_ns      ON findings(ns);
CREATE INDEX IF NOT EXISTS idx_findings_status  ON findings(status);
CREATE INDEX IF NOT EXISTS idx_findings_last_seen ON findings(last_seen);
```

All writes go through a single async writer coroutine (`asyncio.Queue`-based)
so the WAL serialization point is managed in Python without additional locking.

### 18.2.2 Upsert Pattern

```python
import hashlib, uuid
from datetime import datetime, timezone

def _fingerprint(ns: str, kind: str, name: str,
                 severity: str, root_cause_hash: str) -> str:
    raw = f"{ns}|{kind}|{name}|{severity}|{root_cause_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()

async def upsert_finding(db, ns, kind, name, severity, root_cause_hash, **extra):
    fp = _fingerprint(ns, kind, name, severity, root_cause_hash)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute("""
        INSERT INTO findings
            (id, fingerprint_sha256, first_seen, last_seen,
             occurrence_count, ns, kind, name, severity, status, root_cause_hash)
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, 'open', ?)
        ON CONFLICT(fingerprint_sha256) DO UPDATE SET
            last_seen        = excluded.last_seen,
            occurrence_count = occurrence_count + 1
    """, (uuid.uuid4().hex, fp, now, now, ns, kind, name, severity, root_cause_hash))
    await db.commit()
```

---

## 18.3 Finding Deduplication

### 18.3.1 Dedup Contract

Two raw findings are the **same finding** when all of the following match:

1. `namespace`
2. `kind`
3. `name`
4. `severity`
5. `root_cause_hash` — SHA-256 of a normalized root-cause string (whitespace
   collapsed, cluster-specific UIDs stripped)

And the second finding arrives within **24 hours** of the first.

When the dedup rule fires, the system:
- Increments `occurrence_count`
- Updates `last_seen`
- Does **not** open a new PR or sandbox

When the 24-hour window expires without resolution, `status` stays `open` and
the next occurrence resets the window (updates `last_seen`).

### 18.3.2 Root-Cause Hash Computation

```python
import hashlib, re

def root_cause_hash(raw_message: str) -> str:
    """
    Normalize a finding message to a stable key.
    Removes pod/node UIDs, IP addresses, and timestamps.
    """
    s = raw_message.lower()
    s = re.sub(r'\b[0-9a-f]{8}-[0-9a-f-]{27}\b', '<uid>', s)   # UUIDs
    s = re.sub(r'\b\d{1,3}(\.\d{1,3}){3}\b', '<ip>', s)         # IPv4
    s = re.sub(r'\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}', '<ts>', s) # timestamps
    s = re.sub(r'\s+', ' ', s).strip()
    return hashlib.sha256(s.encode()).hexdigest()
```

---

## 18.4 Query API for the Audit-Log Viewer

The MCP server exposes a read-only tool `query_audit_log` with three filter
modes. All results are returned as a list of audit-entry dicts, newest first,
maximum 500 per call.

```python
async def query_audit_log(
    ns: str | None = None,
    since: str | None = None,   # UTC ISO-8601 lower bound
    until: str | None = None,   # UTC ISO-8601 upper bound
    finding_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Reads audit.jsonl (or the in-memory ring buffer for the current day)
    and applies filters. At least one filter must be provided.
    """
    ...
```

Implementation uses a forward scan of the JSONL file with early exit once
`timestamp > until`. For large historical windows, the caller should specify a
narrow `since`/`until` range; the API enforces `limit <= 500`.

---

## 18.5 Tests

### 18.5.1 Audit-Log Rotation Test

```python
# tests/test_audit_rotation.py
import json, os, tempfile, time
from pathlib import Path
from src.audit_logger import AuditLogger

def test_rotation_and_record_count():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        logger = AuditLogger(log_path=str(log_path))

        # Write 1000 fake records
        for i in range(1000):
            logger.append({
                "timestamp": f"2026-06-02T00:{i//60:02d}:{i%60:02d}.000Z",
                "actor": "remediator/sa-auto-fix",
                "action": "detect",
                "target": {"kind": "Pod", "namespace": "default", "name": f"pod-{i}"},
                "finding_id": f"find_{i:04x}",
                "fix_id": None, "sandbox_id": None, "pr_url": None,
                "outcome": "success",
                "evidence_pointer": f"gs://evidence/find_{i:04x}.json",
                "dpo_pair_url": None,
            })

        lines = log_path.read_text().splitlines()
        assert len(lines) == 1000, f"expected 1000, got {len(lines)}"

        # Simulate rotation: rename and reopen
        rotated = Path(d) / "audit.jsonl.20260602"
        log_path.rename(rotated)
        logger.reopen()

        logger.append({
            "timestamp": "2026-06-03T00:00:00.000Z",
            "actor": "remediator/sa-auto-fix",
            "action": "detect",
            "target": {"kind": "Pod", "namespace": "default", "name": "pod-new"},
            "finding_id": "find_new1",
            "fix_id": None, "sandbox_id": None, "pr_url": None,
            "outcome": "success",
            "evidence_pointer": "gs://evidence/find_new1.json",
            "dpo_pair_url": None,
        })

        assert rotated.exists()
        assert len(rotated.read_text().splitlines()) == 1000
        assert len(log_path.read_text().splitlines()) == 1
```

### 18.5.2 Dedup Collapse Test

```python
# tests/test_finding_dedup.py
import asyncio
from src.finding_store import upsert_finding, get_finding_by_fingerprint
import aiosqlite, tempfile, os

async def _run():
    with tempfile.TemporaryDirectory() as d:
        db_path = os.path.join(d, "findings.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.executescript(SCHEMA_SQL)  # imported from src/schema.py

            rc_hash = "aaabbbccc"  # same root cause for all 50 emissions

            # Emit 50 findings with the same (ns, kind, name, severity, root_cause_hash)
            for _ in range(50):
                await upsert_finding(
                    db, ns="payments", kind="Deployment",
                    name="checkout-api", severity="high",
                    root_cause_hash=rc_hash,
                )

            async with db.execute(
                "SELECT occurrence_count FROM findings WHERE root_cause_hash = ?",
                (rc_hash,)
            ) as cur:
                row = await cur.fetchone()

            assert row is not None, "finding not persisted"
            assert row[0] == 50, f"expected 50 occurrences, got {row[0]}"

            # Confirm only one row exists
            async with db.execute("SELECT COUNT(*) FROM findings") as cur:
                count = (await cur.fetchone())[0]
            assert count == 1, f"dedup failed: {count} rows found"

asyncio.run(_run())
```

### 18.5.3 Query API Filter Test

```python
# tests/test_query_audit_log.py
from src.audit_query import query_audit_log
import asyncio, tempfile
from pathlib import Path

async def _run():
    with tempfile.TemporaryDirectory() as d:
        log_path = Path(d) / "audit.jsonl"
        # Write records across two namespaces
        records = []
        for i in range(200):
            ns = "payments" if i % 2 == 0 else "infra"
            records.append({
                "timestamp": f"2026-06-02T01:{i//60:02d}:{i%60:02d}.000Z",
                "actor": "remediator/sa-auto-fix",
                "action": "detect",
                "target": {"kind": "Pod", "namespace": ns, "name": f"pod-{i}"},
                "finding_id": f"find_{i:04x}",
                "fix_id": None, "sandbox_id": None, "pr_url": None,
                "outcome": "success",
                "evidence_pointer": f"gs://evidence/find_{i:04x}.json",
                "dpo_pair_url": None,
            })
        import json
        log_path.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        results = await query_audit_log(
            log_path=str(log_path), ns="payments", limit=500
        )
        assert len(results) == 100, f"expected 100, got {len(results)}"
        assert all(r["target"]["namespace"] == "payments" for r in results)

        results_range = await query_audit_log(
            log_path=str(log_path),
            since="2026-06-02T01:01:00.000Z",
            until="2026-06-02T01:02:00.000Z",
            limit=500,
        )
        assert all(
            "2026-06-02T01:01" <= r["timestamp"] <= "2026-06-02T01:02"
            for r in results_range
        )

asyncio.run(_run())
```

---

## 18.6 Acceptance Criteria

| # | Criterion |
|---|---|
| AC-18-1 | Every remediator action (all eight verbs) produces one JSONL line before its return path completes. |
| AC-18-2 | A write failure to `audit.jsonl` logs to stderr and does not raise in the calling action. |
| AC-18-3 | `audit.jsonl` is rotated daily; post-rotation writes land in the new file within one cycle. |
| AC-18-4 | Rotated files older than 90 days are compressed and uploaded to GCS before local deletion. |
| AC-18-5 | 50 identical findings (same ns/kind/name/severity/root_cause_hash) produce exactly one row with `occurrence_count = 50`. |
| AC-18-6 | `query_audit_log` with `ns="payments"` returns only records where `target.namespace == "payments"`. |
| AC-18-7 | 1000 fake records are written and all 1000 are present after a simulated rotation. |
