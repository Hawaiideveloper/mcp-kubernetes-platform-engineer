# Section 13 — CronJob Analyzer + Orphan Job Cleanup

## Purpose

Two unimplemented capabilities: automated detection of degraded CronJob
behavior (missed schedules, repeated backoff failures, accidental suspension,
history-limit orphan accumulation) and deterministic cleanup of orphan Jobs
whose controller has disowned or forgotten them. The cluster event
`Saw a job that the controller did not create or forgot: manual-cw5-003` is
the canonical trigger for the cleanup path.

---

## 1. Data Models

```python
# src/models/cronjob_finding.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, List, Optional

@dataclass
class CronJobFinding:
    name: str
    namespace: str
    issue_type: Literal[
        "missed_schedule", "repeated_backoff",
        "accidental_suspend", "history_limit_orphan",
    ]
    severity: Literal["critical", "high", "medium", "low", "info"]
    evidence: str
    missed_count: int = 0
    affected_jobs: List[str] = field(default_factory=list)

@dataclass
class OrphanJob:
    name: str
    namespace: str
    uid: str
    creation_ts: datetime
    owner_ref_uid: Optional[str]
    is_active: bool

@dataclass
class CleanupResult:
    deleted: List[str]
    skipped_active: List[str]
    skipped_trading: List[str]
    dry_run: bool
```

---

## 2. CronJobAnalyzer

### 2.1 Signature

```python
# src/analyzers/cronjob_analyzer.py
class CronJobAnalyzer:
    MISSED_SCHEDULE_MULTIPLIER = 2   # flag after 2x the schedule interval
    BACKOFF_REPEAT_THRESHOLD = 3     # consecutive runs hitting backoffLimit

    def __init__(self, batch_v1: client.BatchV1Api) -> None: ...

    async def analyze(
        self, namespace: Optional[str] = None
    ) -> List[CronJobFinding]: ...
```

### 2.2 Detection Logic

**Missed schedule** — parse `spec.schedule` with `croniter` against
`status.lastScheduleTime`. If the overdue window exceeds
`MISSED_SCHEDULE_MULTIPLIER * interval_seconds`, emit `missed_schedule`.
Suspended CronJobs are skipped for this check.

**Accidental suspend** — if `spec.suspend == True`, emit `accidental_suspend`
at medium severity regardless of schedule state.

**Repeated backoff** — count owned Jobs with a `Failed/BackoffLimitExceeded`
condition. If count >= `BACKOFF_REPEAT_THRESHOLD`, emit `repeated_backoff`.

**History-limit orphans** — count owned completed/failed Jobs that exceed
`successfulJobsHistoryLimit` (default 3) and `failedJobsHistoryLimit`
(default 1). Surplus jobs accumulate and are never GC'd; emit
`history_limit_orphan` with the list of affected job names.

---

## 3. OrphanJobCleaner

### 3.1 Orphan Detection Algorithm

```
for each Job J in namespace:
    refs = [r for r in J.ownerReferences if r.kind == "CronJob"]
    if not refs: continue          # bare job, not a CronJob child
    for ref in refs:
        if ref.uid NOT IN current CronJob UID set:
            if age(J) < grace_period: continue   # may be in-flight
            if J.status.active > 0:  continue    # never touch running jobs
            J is an orphan
```

This matches the exact condition behind the Kubernetes controller warning
`Saw a job that the controller did not create or forgot`.

### 3.2 Signature

```python
# src/analyzers/orphan_job_cleaner.py
TRADING_NAMESPACES = {"trading", "brightflow-live", "ibkr-real-money-gateway"}

class OrphanJobCleaner:
    def __init__(
        self,
        batch_v1: client.BatchV1Api,
        grace_period_minutes: int = 60,
    ) -> None: ...

    async def find_orphan_jobs(
        self, namespace: Optional[str] = None
    ) -> List[OrphanJob]: ...

    async def cleanup(
        self, jobs: List[OrphanJob], dry_run: bool = True
    ) -> CleanupResult: ...
```

### 3.3 Deterministic Fix Command

```bash
# Confirm job is not running
kubectl get job manual-cw5-003 -n <namespace> \
  -o jsonpath='{.status.active}'   # must be 0

kubectl delete job manual-cw5-003 -n <namespace> --cascade=background
```

Code equivalent: `OrphanJobCleaner.cleanup([orphan], dry_run=False)` which
calls `batch_v1.delete_namespaced_job(propagation_policy="Background")`.

### 3.4 Trading-Namespace Rule

If `job.namespace in TRADING_NAMESPACES`, `cleanup()` adds the job to
`skipped_trading` and issues no delete call, regardless of the `dry_run` flag
or any caller override. The operator must open a PR for manual review.

---

## 4. Tests

### 4.1 CronJobAnalyzer — missed schedule and suspend

```python
# tests/analyzers/test_cronjob_analyzer.py
@pytest.mark.asyncio
async def test_missed_schedule_detected():
    # CronJob with 30-min schedule, last run 3 hours ago
    cj = _make_cj(schedule="*/30 * * * *", last_schedule_offset_minutes=180)
    findings = await CronJobAnalyzer(mock_batch([cj], [])).analyze("default")
    missed = [f for f in findings if f.issue_type == "missed_schedule"]
    assert len(missed) == 1 and missed[0].missed_count >= 3

@pytest.mark.asyncio
async def test_suspend_skips_missed_schedule_and_flags_suspend():
    cj = _make_cj(schedule="*/5 * * * *", last_schedule_offset_minutes=60, suspend=True)
    findings = await CronJobAnalyzer(mock_batch([cj], [])).analyze("default")
    assert not any(f.issue_type == "missed_schedule" for f in findings)
    assert any(f.issue_type == "accidental_suspend" for f in findings)
```

### 4.2 OrphanJobCleaner — manual-cw5-003 fixture

```python
# tests/analyzers/test_orphan_job_cleaner.py
@pytest.mark.asyncio
async def test_find_orphan_manual_cw5_003():
    # Job whose ownerRef UID points to a deleted CronJob
    job = _make_orphan_job("manual-cw5-003", owner_uid="stale-uid-999")
    cleaner = OrphanJobCleaner(mock_batch(jobs=[job], cj=[]), grace_period_minutes=60)
    orphans = await cleaner.find_orphan_jobs("default")
    assert len(orphans) == 1
    assert orphans[0].name == "manual-cw5-003"

@pytest.mark.asyncio
async def test_active_job_never_deleted():
    job = _make_orphan_job("manual-cw5-003", active=1)
    batch = mock_batch(jobs=[job], cj=[])
    cleaner = OrphanJobCleaner(batch, grace_period_minutes=60)
    orphans = await cleaner.find_orphan_jobs("default")
    result = await cleaner.cleanup(orphans, dry_run=False)
    batch.delete_namespaced_job.assert_not_called()
    assert "manual-cw5-003" in result.skipped_active

@pytest.mark.asyncio
async def test_trading_namespace_blocked():
    job = _make_orphan_job("manual-cw5-003", ns="trading")
    cleaner = OrphanJobCleaner(mock_batch(jobs=[job], cj=[]))
    orphans = await cleaner.find_orphan_jobs("trading")
    result = await cleaner.cleanup(orphans, dry_run=False)
    assert "manual-cw5-003" in result.skipped_trading

@pytest.mark.asyncio
async def test_dry_run_no_api_calls():
    job = _make_orphan_job("manual-cw5-003")
    batch = mock_batch(jobs=[job], cj=[])
    cleaner = OrphanJobCleaner(batch)
    orphans = await cleaner.find_orphan_jobs("default")
    result = await cleaner.cleanup(orphans, dry_run=True)
    batch.delete_namespaced_job.assert_not_called()
    assert result.dry_run is True
```

---

## 5. Integration Points

- `DiagnosticsManager._check_workloads()` calls `CronJobAnalyzer.analyze()`
  and appends results to the finding queue.
- `RemediationQueue` routes `orphan_job` findings to `OrphanJobCleaner.cleanup()`
  with `dry_run` mirroring the global `NON_DESTRUCTIVE_MODE` flag.
- Trading-namespace guard is enforced inside `OrphanJobCleaner.cleanup()` and
  is not overridable by the caller.

## 6. Dependencies

| Package | Min version | Purpose |
|---------|-------------|---------|
| `croniter` | 1.4 | Parse cron expressions, compute next-run time |
| `kubernetes` | 28.1 | `BatchV1Api` for CronJob and Job listing/deletion |
