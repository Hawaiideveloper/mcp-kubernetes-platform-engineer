from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Set

from kubernetes import client

from src.models.cronjob_finding import CleanupResult, OrphanJob

logger = logging.getLogger(__name__)

TRADING_NAMESPACES: Set[str] = {
    "trading",
    "brightflow-live",
    "ibkr-real-money-gateway",
}


class OrphanJobCleaner:
    def __init__(
        self,
        batch_v1: client.BatchV1Api,
        grace_period_minutes: int = 60,
    ) -> None:
        self.batch_v1 = batch_v1
        self.grace_period_minutes = grace_period_minutes

    async def find_orphan_jobs(
        self, namespace: Optional[str] = None
    ) -> List[OrphanJob]:
        orphans: List[OrphanJob] = []

        if namespace:
            job_list = self.batch_v1.list_namespaced_job(namespace)
            cj_list = self.batch_v1.list_namespaced_cron_job(namespace)
        else:
            job_list = self.batch_v1.list_job_for_all_namespaces()
            cj_list = self.batch_v1.list_cron_job_for_all_namespaces()

        # Build set of known CronJob UIDs
        current_cj_uids: Set[str] = set()
        for cj in (cj_list.items if cj_list else []):
            uid = getattr(getattr(cj, "metadata", None), "uid", None)
            if uid:
                current_cj_uids.add(uid)

        now_ts = datetime.now(timezone.utc).timestamp()
        grace_seconds = self.grace_period_minutes * 60

        for job in (job_list.items if job_list else []):
            meta = getattr(job, "metadata", None)
            if not meta:
                continue

            refs = getattr(meta, "owner_references", None) or []
            cj_refs = [r for r in refs if getattr(r, "kind", "") == "CronJob"]
            if not cj_refs:
                continue  # bare job, not a CronJob child

            for ref in cj_refs:
                ref_uid = getattr(ref, "uid", None)
                if ref_uid in current_cj_uids:
                    continue  # owner still exists

                # Check grace period
                creation_ts = getattr(meta, "creation_timestamp", None)
                if creation_ts is not None:
                    if hasattr(creation_ts, "timestamp"):
                        creation_epoch = creation_ts.timestamp()
                    else:
                        creation_epoch = float(creation_ts)
                    if (now_ts - creation_epoch) < grace_seconds:
                        continue  # may be in-flight

                # Check if active
                status = getattr(job, "status", None)
                active = getattr(status, "active", 0) or 0
                is_active = active > 0

                # Determine creation_ts for OrphanJob
                if creation_ts is not None:
                    if hasattr(creation_ts, "timestamp"):
                        dt_creation = datetime.fromtimestamp(
                            creation_ts.timestamp(), tz=timezone.utc
                        )
                    else:
                        dt_creation = datetime.fromtimestamp(
                            float(creation_ts), tz=timezone.utc
                        )
                else:
                    dt_creation = datetime.now(timezone.utc)

                orphans.append(
                    OrphanJob(
                        name=meta.name,
                        namespace=meta.namespace,
                        uid=meta.uid or "",
                        creation_ts=dt_creation,
                        owner_ref_uid=ref_uid,
                        is_active=is_active,
                    )
                )

        return orphans

    async def cleanup(
        self, jobs: List[OrphanJob], dry_run: bool = True
    ) -> CleanupResult:
        deleted: List[str] = []
        skipped_active: List[str] = []
        skipped_trading: List[str] = []

        for job in jobs:
            # Trading namespace guard — non-overridable
            if job.namespace in TRADING_NAMESPACES:
                skipped_trading.append(job.name)
                logger.warning(
                    "Skipping orphan job %s/%s — trading namespace; manual review required",
                    job.namespace,
                    job.name,
                )
                continue

            # Never touch active jobs
            if job.is_active:
                skipped_active.append(job.name)
                logger.info(
                    "Skipping orphan job %s/%s — still has active pods",
                    job.namespace,
                    job.name,
                )
                continue

            if dry_run:
                logger.info(
                    "DRY RUN: would delete orphan job %s/%s",
                    job.namespace,
                    job.name,
                )
                deleted.append(job.name)
                continue

            try:
                self.batch_v1.delete_namespaced_job(
                    name=job.name,
                    namespace=job.namespace,
                    body=client.V1DeleteOptions(
                        propagation_policy="Background"
                    ),
                )
                deleted.append(job.name)
                logger.info(
                    "Deleted orphan job %s/%s",
                    job.namespace,
                    job.name,
                )
            except Exception as exc:
                logger.error(
                    "Failed to delete orphan job %s/%s: %s",
                    job.namespace,
                    job.name,
                    exc,
                )

        return CleanupResult(
            deleted=deleted,
            skipped_active=skipped_active,
            skipped_trading=skipped_trading,
            dry_run=dry_run,
        )
