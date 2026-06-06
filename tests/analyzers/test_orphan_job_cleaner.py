from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.orphan_job_cleaner import OrphanJobCleaner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_orphan_job(
    name: str,
    ns: str = "default",
    owner_uid: str = "stale-uid-999",
    active: int = 0,
    age_minutes: int = 120,
) -> MagicMock:
    """Build a mock Kubernetes Job with a stale CronJob ownerRef."""
    job = MagicMock()
    job.metadata.name = name
    job.metadata.namespace = ns
    job.metadata.uid = f"uid-{name}"

    now_ts = datetime.now(timezone.utc).timestamp()
    past_ts = now_ts - age_minutes * 60
    ts = MagicMock()
    ts.timestamp.return_value = past_ts
    job.metadata.creation_timestamp = ts

    ref = MagicMock()
    ref.kind = "CronJob"
    ref.uid = owner_uid
    job.metadata.owner_references = [ref]

    job.status.active = active
    job.status.succeeded = 1 if active == 0 else 0
    job.status.failed = 0
    return job


def _mock_batch(jobs: list, cj: list) -> MagicMock:
    batch = MagicMock()

    job_result = MagicMock()
    job_result.items = jobs
    batch.list_namespaced_job.return_value = job_result
    batch.list_job_for_all_namespaces.return_value = job_result

    cj_result = MagicMock()
    cj_result.items = cj
    batch.list_namespaced_cron_job.return_value = cj_result
    batch.list_cron_job_for_all_namespaces.return_value = cj_result
    return batch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_orphan_manual_cw5_003() -> None:
    """Job whose ownerRef UID points to a deleted CronJob is detected."""
    job = _make_orphan_job("manual-cw5-003", owner_uid="stale-uid-999")
    cleaner = OrphanJobCleaner(
        _mock_batch(jobs=[job], cj=[]), grace_period_minutes=60
    )
    orphans = await cleaner.find_orphan_jobs("default")
    assert len(orphans) == 1
    assert orphans[0].name == "manual-cw5-003"


@pytest.mark.asyncio
async def test_active_job_never_deleted() -> None:
    """Active jobs are skipped and never deleted."""
    job = _make_orphan_job("manual-cw5-003", active=1)
    batch = _mock_batch(jobs=[job], cj=[])
    cleaner = OrphanJobCleaner(batch, grace_period_minutes=60)
    orphans = await cleaner.find_orphan_jobs("default")
    result = await cleaner.cleanup(orphans, dry_run=False)
    batch.delete_namespaced_job.assert_not_called()
    assert "manual-cw5-003" in result.skipped_active


@pytest.mark.asyncio
async def test_trading_namespace_blocked() -> None:
    """Jobs in trading namespace are never deleted."""
    job = _make_orphan_job("manual-cw5-003", ns="trading")
    cleaner = OrphanJobCleaner(_mock_batch(jobs=[job], cj=[]))
    orphans = await cleaner.find_orphan_jobs("trading")
    result = await cleaner.cleanup(orphans, dry_run=False)
    assert "manual-cw5-003" in result.skipped_trading


@pytest.mark.asyncio
async def test_dry_run_no_api_calls() -> None:
    """Dry run must not make delete calls."""
    job = _make_orphan_job("manual-cw5-003")
    batch = _mock_batch(jobs=[job], cj=[])
    cleaner = OrphanJobCleaner(batch)
    orphans = await cleaner.find_orphan_jobs("default")
    result = await cleaner.cleanup(orphans, dry_run=True)
    batch.delete_namespaced_job.assert_not_called()
    assert result.dry_run is True


@pytest.mark.asyncio
async def test_real_delete_called_for_stale_orphan() -> None:
    """Non-dry-run must call delete for a genuine orphan."""
    job = _make_orphan_job("manual-cw5-003")
    batch = _mock_batch(jobs=[job], cj=[])
    cleaner = OrphanJobCleaner(batch, grace_period_minutes=60)
    orphans = await cleaner.find_orphan_jobs("default")
    result = await cleaner.cleanup(orphans, dry_run=False)
    call_kwargs = batch.delete_namespaced_job.call_args
    assert call_kwargs.kwargs["name"] == "manual-cw5-003"
    assert call_kwargs.kwargs["namespace"] == "default"
    assert call_kwargs.kwargs["body"].propagation_policy == "Background"  
    assert "manual-cw5-003" in result.deleted


@pytest.mark.asyncio
async def test_grace_period_skips_fresh_job() -> None:
    """Jobs newer than the grace period are not flagged as orphans."""
    job = _make_orphan_job("fresh-orphan", age_minutes=10)
    cleaner = OrphanJobCleaner(
        _mock_batch(jobs=[job], cj=[]), grace_period_minutes=60
    )
    orphans = await cleaner.find_orphan_jobs("default")
    assert len(orphans) == 0


@pytest.mark.asyncio
async def test_known_owner_not_orphan() -> None:
    """Job whose owner UID matches an existing CronJob is not flagged."""
    cj = MagicMock()
    cj.metadata.uid = "live-uid-001"
    job = _make_orphan_job("normal-job", owner_uid="live-uid-001")
    cleaner = OrphanJobCleaner(
        _mock_batch(jobs=[job], cj=[cj]), grace_period_minutes=60
    )
    orphans = await cleaner.find_orphan_jobs("default")
    assert len(orphans) == 0


@pytest.mark.asyncio
async def test_brightflow_live_blocked() -> None:
    """brightflow-live is a trading namespace and must be blocked."""
    job = _make_orphan_job("live-job", ns="brightflow-live")
    cleaner = OrphanJobCleaner(_mock_batch(jobs=[job], cj=[]))
    orphans = await cleaner.find_orphan_jobs("brightflow-live")
    result = await cleaner.cleanup(orphans, dry_run=False)
    assert "live-job" in result.skipped_trading
