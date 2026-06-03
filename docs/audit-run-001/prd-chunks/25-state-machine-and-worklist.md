# Section 25 — Iteration State Machine + SQLite Worklist + Work-Split Algorithm

## 1. Purpose

This section is the Phase D contract: data model, atomicity guarantees, and
dependency ordering for 25 implementation agents to claim work without collision.

---

## 2. Audit-Run Iteration State Machine

Each audit-run is one iteration. The phases are:

```
review (50 agents read src/)
  -> synthesize (25 agents write prd-chunks/*.md)
  -> claim     (25 agents SELECT a task from SQLite and lock it)
  -> implement (those 25 agents produce PRs, one per task)
  -> verify    (first 25 agents check that each PR merged and CI passed)
  -> [done | iterate]
```

### 2.1 Mermaid Diagram

```mermaid
stateDiagram-v2
    [*] --> review : new audit-run created

    review --> synthesize : 50 review agents complete; all-findings.json written
    synthesize --> claim   : all prd-chunks/*.md written

    claim --> implement   : each agent holds exactly one task row
    implement --> verify  : all tasks reach status=done or status=failed

    verify --> done       : all acceptance criteria in §22 pass AND\nzero tasks in status=failed
    verify --> iterate    : at least one criterion fails AND iteration_count < 5
    verify --> escalate   : iteration_count >= 5

    iterate --> review
    done --> [*]
    escalate --> [*] : human intervention required
```

### 2.2 Stop Conditions

An audit-run terminates when **any** of the following is true:

| Condition | Terminal state |
|---|---|
| All §22 acceptance criteria pass and `tasks.status=failed` count is zero | `done` |
| `iteration_count >= 5` | `escalate` — write `docs/audit-run-{n}/escalation.md` and halt |
| An unrecoverable system error (vcluster create fails, SQLite is corrupt) | `escalate` |

The iteration counter is stored in `audit_runs(iteration_count)` (see §2.3).

### 2.3 Persistent Iteration Record

```sql
CREATE TABLE IF NOT EXISTS audit_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label       TEXT    NOT NULL UNIQUE,   -- e.g. "audit-run-001"
    phase           TEXT    NOT NULL
                    CHECK (phase IN (
                        'review','synthesize','claim',
                        'implement','verify','done','escalate'
                    )),
    iteration_count INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT    NOT NULL,          -- ISO-8601
    updated_at      TEXT    NOT NULL,
    stopped_reason  TEXT                       -- NULL until terminal
);
```

---

## 3. SQLite Worklist Schema

File location: `data/worklist.db` (WAL mode; created on first use).

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tasks (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    prd_section      TEXT    NOT NULL,   -- e.g. "09", "17", "25"
    title            TEXT    NOT NULL,
    blockers         TEXT    NOT NULL DEFAULT '[]',
                                         -- JSON array of task ids (integers)
    deliverable_paths TEXT   NOT NULL DEFAULT '[]',
                                         -- JSON array of file paths
    status           TEXT    NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued','claimed','in_progress','done','failed')),
    claimed_by       TEXT,               -- agent identifier string
    claimed_at       TEXT,               -- ISO-8601 timestamp or NULL
    completed_at     TEXT,               -- ISO-8601 timestamp or NULL
    pr_url           TEXT                -- GitHub PR URL or NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
```

`blockers` stores a JSON array of integer task `id` values whose `status` must
equal `'done'` before this task is claimable. The Python layer enforces this
during the atomic claim (see §4).

---

## 4. Atomic Claim Algorithm

An agent calls `claim_next(agent_id)`. The function uses `BEGIN IMMEDIATE` to
serialize concurrent writers. SQLite's WAL mode allows one writer and many
readers simultaneously; `BEGIN IMMEDIATE` acquires the write lock at transaction
start rather than at first DML, eliminating the TOCTOU window.

### 4.1 SQL

```sql
BEGIN IMMEDIATE;

UPDATE tasks
SET    status     = 'claimed',
       claimed_by  = :agent_id,
       claimed_at  = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE  id = (
    SELECT t.id
    FROM   tasks t
    WHERE  t.status = 'queued'
      AND  NOT EXISTS (
               SELECT 1
               FROM   tasks b
               WHERE  b.id IN (
                          SELECT value
                          FROM   json_each(t.blockers)
                      )
                 AND  b.status != 'done'
           )
    ORDER BY t.id
    LIMIT  1
)
RETURNING id, prd_section, title, blockers, deliverable_paths,
          status, claimed_by, claimed_at;

COMMIT;
```

If zero rows are returned the agent has no work available (either all tasks are
claimed/done, or all remaining tasks are blocked). The agent should sleep and
retry, or exit if `tasks WHERE status IN ('queued','claimed','in_progress')` is
empty.

### 4.2 Python Implementation

```python
# src/worklist.py
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

_CLAIM_SQL = """
BEGIN IMMEDIATE;
"""

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


class WorklistDB:
    """Thread-safe SQLite worklist backed by WAL mode."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            isolation_level=None,   # autocommit; transactions are managed manually
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript("""
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

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
                    pr_url            TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            """)

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

    def seed(self, tasks: list[dict]) -> None:
        """Insert tasks (idempotent — skips rows where title already exists)."""
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
```

---

## 5. Work-Split Rule: Topological Dependency Enforcement

An agent **cannot** claim a task whose `blockers` list contains any task id
with `status != 'done'`. The `NOT EXISTS` sub-query in §4.1 enforces this at
the SQL layer; no application-level check is needed.

A Python helper produces the seed payload in topological order so the database
can be inspected in insertion order:

```python
# src/worklist_seed.py
from __future__ import annotations

from collections import deque
from typing import Any


def topological_sort(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kahn's algorithm. tasks[i]['id'] is a stable integer (1-based).

    Raises ValueError on cycles.
    """
    id_to_task = {t["id"]: t for t in tasks}
    in_degree: dict[int, int] = {t["id"]: 0 for t in tasks}
    dependents: dict[int, list[int]] = {t["id"]: [] for t in tasks}

    for t in tasks:
        for blocker_id in t.get("blockers", []):
            in_degree[t["id"]] += 1
            dependents[blocker_id].append(t["id"])

    queue: deque[int] = deque(
        tid for tid, deg in sorted(in_degree.items()) if deg == 0
    )
    ordered: list[dict[str, Any]] = []

    while queue:
        tid = queue.popleft()
        ordered.append(id_to_task[tid])
        for dep in dependents[tid]:
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(ordered) != len(tasks):
        cycle = [t["id"] for t in tasks if t["id"] not in {o["id"] for o in ordered}]
        raise ValueError(f"Dependency cycle detected among task ids: {cycle}")

    return ordered
```

---

## 6. Dependency Graph Between PRD Sections

The following edges represent hard implementation dependencies. An arrow
`A -> B` means "B cannot be started until A is merged."

```
§09 (analyzer-base)          -> §10 (deployment-analyzer)
§09 (analyzer-base)          -> §11 (node-analyzer)
§09 (analyzer-base)          -> §12 (service-analyzer)
§09 (analyzer-base)          -> §13 (pvc-analyzer)
§09 (analyzer-base)          -> §14 (ingress-analyzer)
§09 (analyzer-base)          -> §15 (cronjob-analyzer)
§09 (analyzer-base)          -> §16 (network-policy-analyzer)
§09 (analyzer-base)          -> §17 (deterministic-remediation-table)
§17 (deterministic-table)    -> §18 (sandbox-execution)
§03 (restart-first-ladder)   -> §17 (deterministic-table)
§25 (this section — worklist) -> §D0 (wire-up: seed worklist)
§17 (deterministic-table)    -> §22 (acceptance-criteria)
§20 (ci-cd)                  -> §22 (acceptance-criteria)
§06 (trading-hardblock)      -> §22 (acceptance-criteria)
§21 (security/rbac)          -> §22 (acceptance-criteria)
ALL sections                  -> §22 (acceptance-criteria)
```

---

## 7. Work Breakdown: 25 Implementation Tasks

The table below is the canonical seed payload for `WorklistDB.seed()`. `id`
values are stable integers used as foreign keys in `blockers`.

| id | prd_section | title | blockers | deliverable_paths | expected diff |
|---|---|---|---|---|---|
| 1 | 09 | Implement BaseAnalyzer + Finding dataclass | [] | `src/analyzers/base.py`, `tests/analyzers/test_base.py` | ~120 lines |
| 2 | 09 | Implement PodAnalyzer | [1] | `src/analyzers/pod_analyzer.py`, `tests/analyzers/test_pod_analyzer.py` | ~180 lines |
| 3 | 10 | Implement DeploymentAnalyzer | [1] | `src/analyzers/deployment_analyzer.py`, `tests/analyzers/test_deployment_analyzer.py` | ~140 lines |
| 4 | 11 | Implement NodeAnalyzer | [1] | `src/analyzers/node_analyzer.py`, `tests/analyzers/test_node_analyzer.py` | ~100 lines |
| 5 | 12 | Implement ServiceAnalyzer | [1] | `src/analyzers/service_analyzer.py`, `tests/analyzers/test_service_analyzer.py` | ~120 lines |
| 6 | 13 | Implement PVCAnalyzer | [1] | `src/analyzers/pvc_analyzer.py`, `tests/analyzers/test_pvc_analyzer.py` | ~120 lines |
| 7 | 14 | Implement IngressAnalyzer | [1] | `src/analyzers/ingress_analyzer.py`, `tests/analyzers/test_ingress_analyzer.py` | ~130 lines |
| 8 | 15 | Implement CronJobAnalyzer | [1] | `src/analyzers/cronjob_analyzer.py`, `tests/analyzers/test_cronjob_analyzer.py` | ~130 lines |
| 9 | 16 | Implement NetworkPolicyAnalyzer | [1] | `src/analyzers/network_policy_analyzer.py`, `tests/analyzers/test_network_policy_analyzer.py` | ~110 lines |
| 10 | 03 | Implement RestartFirstLadder remediator | [] | `src/remediators/restart_ladder.py`, `tests/remediators/test_restart_ladder.py` | ~150 lines |
| 11 | 17 | Implement deterministic remediation table + dispatch | [1, 10] | `src/remediators/table.py`, `tests/remediators/test_table.py` | ~200 lines |
| 12 | 04 | Implement five-minute watchdog asyncio task | [2, 10] | `src/watchdog.py`, `tests/test_watchdog.py` | ~100 lines |
| 13 | 05 | Implement DPO pair extraction | [2, 11] | `src/dpo_extractor.py`, `tests/test_dpo_extractor.py` | ~120 lines |
| 14 | 06 | Implement trading namespace hardblock | [] | `src/hardblock.py`, `tests/test_hardblock.py`, `src/config.py` (patch) | ~80 lines |
| 15 | 18 | Implement vcluster sandbox execution pipeline | [11] | `src/sandbox.py`, `tests/test_sandbox.py` | ~160 lines |
| 16 | 19 | Implement RBAC split (read/write service accounts) | [] | `src/rbac.py`, `k8s/rbac.yaml`, `tests/test_rbac.py` | ~140 lines |
| 17 | 20 | Implement CI/CD workflow (ci.yml + image pinning) | [] | `.github/workflows/ci.yml`, `k8s/deployment.yaml` (patch) | ~180 lines |
| 18 | 21 | Implement audit log (JSONL append-only) | [14, 16] | `src/audit_log.py`, `tests/test_audit_log.py` | ~100 lines |
| 19 | 25 | Implement WorklistDB + atomic claim | [] | `src/worklist.py`, `src/worklist_seed.py`, `tests/test_worklist.py` | ~200 lines |
| 20 | 08 | Implement event stream watcher | [2] | `src/watchers/event_watcher.py`, `tests/watchers/test_event_watcher.py` | ~130 lines |
| 21 | 07 | Implement GitOps PR generation | [11, 15] | `src/gitops.py`, `tests/test_gitops.py` | ~150 lines |
| 22 | 02 | Implement finding deduplication | [1] | `src/dedup.py`, `tests/test_dedup.py` | ~80 lines |
| 23 | D0 | Wire-up: seed worklist from PRD task table | [19] | `scripts/seed_worklist.py` | ~60 lines |
| 24 | D1 | Wire-up: plug analyzers into mcp_server.py dispatch | [2,3,4,5,6,7,8,9,11,12,14,16,18,20,22] | `src/mcp_server.py` (patch) | ~120 lines |
| 25 | 22 | Implement acceptance-criteria gate (done_check.py) | [17,24] | `src/done_check.py`, `tests/test_done_check.py` | ~100 lines |

### 7.1 Key Task Notes

- **Task 1** (BaseAnalyzer): `Finding` must be `frozen=True`; `fingerprint()` excludes mutable fields so the same pod/category yields the same key across poll cycles.
- **Task 10** (RestartFirstLadder): can run in parallel with Task 1 (no dependency); integrates with WorklistDB for per-resource per-resource claim.
- **Task 11** (deterministic table): `dispatch(finding, k8s_state) -> FixCandidate | None`; registers all 10 remediators from §17.
- **Task 14** (trading hardblock): `PROTECTED_NAMESPACES` set in `config.py`; `check_namespace_allowed()` raises `ProtectedNamespaceError` before any mutation call reaches the k8s client.
- **Task 19** (WorklistDB): concurrency test must spawn 10 threads and assert no task id appears in more than one thread's result.
- **Task 24** (wire-up): last substantive coding task; blocked by every other implementation task; gates Task 25.
- **Task 25** (acceptance gate): four gates — pytest exit 0, docker build exit 0, live cluster node count >= 1, zero pods in `Failed`/`CrashLoopBackOff`.

---

## 8. Agent Loop Contract

```python
# Phase D agent entry point
from src.worklist import WorklistDB

db = WorklistDB("data/worklist.db")

while True:
    task = db.claim_next(agent_id=MY_ID)
    if task is None:
        break                             # nothing claimable; all done or all blocked

    db.mark_in_progress(task.id, MY_ID)
    try:
        pr_url = implement(task)
        db.complete(task.id, MY_ID, pr_url)
    except Exception as exc:
        db.fail(task.id, MY_ID, str(exc))
        raise
```

Agents that receive `sqlite3.OperationalError: database is locked` sleep one
second and retry. Under WAL mode this should not occur more than once per agent.

---

## 9. Test Plan

| Test | Assertion |
|---|---|
| `test_claim_atomicity` — 10 threads call `claim_next` simultaneously | Each task id appears in exactly one thread's result; no duplicates |
| `test_blocked_task_not_claimed` — task 2 queued with blocker task 1 in status=queued | `claim_next` returns task 1, not task 2 |
| `test_blocker_done_unblocks` — task 1 set to done, task 2 queued | `claim_next` returns task 2 |
| `test_no_tasks_returns_none` — empty worklist | `claim_next` returns None immediately |
| `test_iteration_escalate` — `iteration_count=5` | `should_escalate` returns True |
| `test_topological_sort_cycle` — task A blocks B blocks A | `topological_sort` raises ValueError |
| `test_topological_sort_happy` — linear chain | returned order matches dependency order |
