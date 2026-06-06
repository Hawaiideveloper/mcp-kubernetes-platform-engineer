from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.cronjob_analyzer import CronJobAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_spec(
    schedule: str,
    suspend: bool = False,
    success_limit: int = 3,
    failed_limit: int = 1,
) -> MagicMock:
    spec = MagicMock()
    spec.schedule = schedule
    spec.suspend = suspend
    spec.successful_jobs_history_limit = success_limit
    spec.failed_jobs_history_limit = failed_limit
    return spec


def _make_status(last_schedule_offset_minutes: int = 0) -> MagicMock:
    st = MagicMock()
    if last_schedule_offset_minutes == 0:
        st.last_schedule_time = None
    else:
        now_ts = datetime.now(timezone.utc).timestamp()
        past_ts = now_ts - last_schedule_offset_minutes * 60
        t = MagicMock()
        t.timestamp.return_value = past_ts
        st.last_schedule_time = t
    return st


def _make_cj(
    schedule: str,
    last_schedule_offset_minutes: int = 0,
    suspend: bool = False,
    uid: str = "cj-uid-001",
    name: str = "test-cj",
    namespace: str = "default",
) -> MagicMock:
    cj = MagicMock()
    cj.metadata.name = name
    cj.metadata.namespace = namespace
    cj.metadata.uid = uid
    cj.spec = _make_spec(schedule, suspend=suspend)
    cj.status = _make_status(last_schedule_offset_minutes)
    return cj


def _make_failed_job(name: str, cj_uid: str) -> MagicMock:
    job = MagicMock()
    job.metadata.name = name
    job.metadata.namespace = "default"
    job.metadata.uid = f"job-{name}-uid"
    ref = MagicMock()
    ref.kind = "CronJob"
    ref.uid = cj_uid
    job.metadata.owner_references = [ref]

    cond = MagicMock()
    cond.type = "Failed"
    cond.reason = "BackoffLimitExceeded"
    cond.status = "True"
    job.status.conditions = [cond]
    job.status.active = 0
    job.status.succeeded = 0
    job.status.failed = 1
    return job


def _mock_batch(cjs: list, jobs: list) -> MagicMock:
    batch = MagicMock()
    cj_result = MagicMock()
    cj_result.items = cjs
    batch.list_namespaced_cron_job.return_value = cj_result
    batch.list_cron_job_for_all_namespaces.return_value = cj_result

    job_result = MagicMock()
    job_result.items = jobs
    batch.list_namespaced_job.return_value = job_result
    batch.list_job_for_all_namespaces.return_value = job_result
    return batch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missed_schedule_detected() -> None:
    """CronJob with 30-min schedule, last run 3 hours ago."""
    cj = _make_cj(schedule="*/30 * * * *", last_schedule_offset_minutes=180)
    findings = await CronJobAnalyzer(_mock_batch([cj], [])).analyze("default")
    missed = [f for f in findings if f.issue_type == "missed_schedule"]
    assert len(missed) == 1
    assert missed[0].missed_count >= 3


@pytest.mark.asyncio
async def test_suspend_skips_missed_schedule_and_flags_suspend() -> None:
    """Suspended CronJob must not emit missed_schedule but must emit accidental_suspend."""
    cj = _make_cj(
        schedule="*/5 * * * *",
        last_schedule_offset_minutes=60,
        suspend=True,
    )
    findings = await CronJobAnalyzer(_mock_batch([cj], [])).analyze("default")
    assert not any(f.issue_type == "missed_schedule" for f in findings)
    assert any(f.issue_type == "accidental_suspend" for f in findings)


@pytest.mark.asyncio
async def test_no_finding_when_on_schedule() -> None:
    """CronJob that ran just 10 minutes ago with 30-min schedule should be fine."""
    cj = _make_cj(schedule="*/30 * * * *", last_schedule_offset_minutes=10)
    findings = await CronJobAnalyzer(_mock_batch([cj], [])).analyze("default")
    missed = [f for f in findings if f.issue_type == "missed_schedule"]
    assert len(missed) == 0


@pytest.mark.asyncio
async def test_repeated_backoff_detected() -> None:
    """Three jobs with BackoffLimitExceeded should emit repeated_backoff."""
    cj = _make_cj(schedule="*/10 * * * *", uid="cj-uid-backoff")
    jobs = [_make_failed_job(f"job-{i}", "cj-uid-backoff") for i in range(3)]
    findings = await CronJobAnalyzer(_mock_batch([cj], jobs)).analyze("default")
    backoff = [f for f in findings if f.issue_type == "repeated_backoff"]
    assert len(backoff) == 1
    assert len(backoff[0].affected_jobs) == 3


@pytest.mark.asyncio
async def test_repeated_backoff_below_threshold() -> None:
    """Two failed jobs — below threshold of 3, no finding."""
    cj = _make_cj(schedule="*/10 * * * *", uid="cj-uid-low")
    jobs = [_make_failed_job(f"job-{i}", "cj-uid-low") for i in range(2)]
    findings = await CronJobAnalyzer(_mock_batch([cj], jobs)).analyze("default")
    assert not any(f.issue_type == "repeated_backoff" for f in findings)


@pytest.mark.asyncio
async def test_history_limit_orphan_detected() -> None:
    """4 successful jobs against a limit of 3 should produce history_limit_orphan."""
    cj = _make_cj(schedule="*/5 * * * *", uid="cj-hist")
    jobs = []
    for i in range(4):
        j = MagicMock()
        j.metadata.name = f"success-job-{i}"
        j.metadata.namespace = "default"
        j.metadata.uid = f"uid-{i}"
        ref = MagicMock()
        ref.kind = "CronJob"
        ref.uid = "cj-hist"
        j.metadata.owner_references = [ref]
        j.status.active = 0
        j.status.succeeded = 1
        j.status.failed = 0
        j.status.conditions = []
        jobs.append(j)
    findings = await CronJobAnalyzer(_mock_batch([cj], jobs)).analyze("default")
    hist = [f for f in findings if f.issue_type == "history_limit_orphan"]
    assert len(hist) == 1
    assert len(hist[0].affected_jobs) == 1  # 4 - 3 = 1 surplus


@pytest.mark.asyncio
async def test_no_last_schedule_time_no_missed_finding() -> None:
    """CronJob with no lastScheduleTime should not raise or emit missed_schedule."""
    cj = _make_cj(schedule="*/30 * * * *", last_schedule_offset_minutes=0)
    findings = await CronJobAnalyzer(_mock_batch([cj], [])).analyze("default")
    assert not any(f.issue_type == "missed_schedule" for f in findings)
