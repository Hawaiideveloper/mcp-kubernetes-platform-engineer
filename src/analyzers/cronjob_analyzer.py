from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from kubernetes import client

from src.models.cronjob_finding import CronJobFinding

logger = logging.getLogger(__name__)


class CronJobAnalyzer:
    MISSED_SCHEDULE_MULTIPLIER = 2
    BACKOFF_REPEAT_THRESHOLD = 3

    def __init__(self, batch_v1: client.BatchV1Api) -> None:
        self.batch_v1 = batch_v1

    async def analyze(
        self, namespace: Optional[str] = None
    ) -> List[CronJobFinding]:
        findings: List[CronJobFinding] = []

        if namespace:
            cj_list = self.batch_v1.list_namespaced_cron_job(namespace)
            job_list = self.batch_v1.list_namespaced_job(namespace)
        else:
            cj_list = self.batch_v1.list_cron_job_for_all_namespaces()
            job_list = self.batch_v1.list_job_for_all_namespaces()

        cron_jobs = cj_list.items if cj_list else []
        all_jobs = job_list.items if job_list else []

        for cj in cron_jobs:
            ns = cj.metadata.namespace
            name = cj.metadata.name
            spec = cj.spec or {}
            _ = cj.status or {}

            suspend = getattr(spec, "suspend", False) or False

            # Accidental suspend check
            if suspend:
                findings.append(
                    CronJobFinding(
                        name=name,
                        namespace=ns,
                        issue_type="accidental_suspend",
                        severity="medium",
                        evidence=f"CronJob {ns}/{name} has spec.suspend=True",
                    )
                )
                # Skip missed-schedule for suspended CronJobs
            else:
                # Missed schedule check
                findings.extend(
                    self._check_missed_schedule(cj)
                )

            # Repeated backoff check
            owned_jobs = [
                j for j in all_jobs
                if self._is_owned_by(j, cj.metadata.uid)
            ]
            findings.extend(
                self._check_repeated_backoff(cj, owned_jobs)
            )

            # History-limit orphan check
            findings.extend(
                self._check_history_limit_orphans(cj, owned_jobs)
            )

        return findings

    def _check_missed_schedule(self, cj: object) -> List[CronJobFinding]:
        from croniter import croniter

        spec = cj.spec  # type: ignore[attr-defined]
        status = cj.status  # type: ignore[attr-defined]
        schedule = getattr(spec, "schedule", None)
        last_schedule_time = getattr(status, "last_schedule_time", None)

        if not schedule or not last_schedule_time:
            return []

        try:
            if hasattr(last_schedule_time, "timestamp"):
                last_ts = last_schedule_time.timestamp()
            else:
                last_ts = float(last_schedule_time)

            now_ts = datetime.now(timezone.utc).timestamp()
            cron = croniter(schedule, last_ts)
            # Compute the interval in seconds (next - last)
            next_ts = cron.get_next(float)
            interval_seconds = next_ts - last_ts

            overdue_seconds = now_ts - last_ts
            threshold = self.MISSED_SCHEDULE_MULTIPLIER * interval_seconds

            if overdue_seconds > threshold and interval_seconds > 0:
                missed_count = int(overdue_seconds / interval_seconds)
                return [
                    CronJobFinding(
                        name=cj.metadata.name,  # type: ignore[attr-defined]
                        namespace=cj.metadata.namespace,  # type: ignore[attr-defined]
                        issue_type="missed_schedule",
                        severity="high",
                        evidence=(
                            f"Last scheduled {overdue_seconds:.0f}s ago; "
                            f"interval={interval_seconds:.0f}s; "
                            f"threshold={threshold:.0f}s"
                        ),
                        missed_count=missed_count,
                    )
                ]
        except Exception as exc:
            logger.warning("missed_schedule check failed for %s: %s", cj.metadata.name, exc)  # type: ignore[attr-defined]

        return []

    def _check_repeated_backoff(
        self, cj: object, owned_jobs: list
    ) -> List[CronJobFinding]:
        failed_jobs = []
        for j in owned_jobs:
            conditions = getattr(getattr(j, "status", None), "conditions", None) or []
            for cond in conditions:
                if (
                    getattr(cond, "type", "") == "Failed"
                    and getattr(cond, "reason", "") == "BackoffLimitExceeded"
                    and getattr(cond, "status", "") == "True"
                ):
                    failed_jobs.append(j.metadata.name)
                    break

        if len(failed_jobs) >= self.BACKOFF_REPEAT_THRESHOLD:
            return [
                CronJobFinding(
                    name=cj.metadata.name,  # type: ignore[attr-defined]
                    namespace=cj.metadata.namespace,  # type: ignore[attr-defined]
                    issue_type="repeated_backoff",
                    severity="high",
                    evidence=(
                        f"{len(failed_jobs)} jobs hit BackoffLimitExceeded: "
                        + ", ".join(failed_jobs[:5])
                    ),
                    affected_jobs=failed_jobs,
                )
            ]
        return []

    def _check_history_limit_orphans(
        self, cj: object, owned_jobs: list
    ) -> List[CronJobFinding]:
        spec = cj.spec  # type: ignore[attr-defined]
        success_limit = getattr(spec, "successful_jobs_history_limit", 3) or 3
        failed_limit = getattr(spec, "failed_jobs_history_limit", 1) or 1

        completed_jobs = []
        failed_jobs = []
        for j in owned_jobs:
            st = getattr(j, "status", None)
            active = getattr(st, "active", 0) or 0
            succeeded = getattr(st, "succeeded", 0) or 0
            failed = getattr(st, "failed", 0) or 0
            if active == 0:
                if succeeded > 0:
                    completed_jobs.append(j.metadata.name)
                elif failed > 0:
                    failed_jobs.append(j.metadata.name)

        surplus = []
        if len(completed_jobs) > success_limit:
            surplus.extend(completed_jobs[success_limit:])
        if len(failed_jobs) > failed_limit:
            surplus.extend(failed_jobs[failed_limit:])

        if surplus:
            return [
                CronJobFinding(
                    name=cj.metadata.name,  # type: ignore[attr-defined]
                    namespace=cj.metadata.namespace,  # type: ignore[attr-defined]
                    issue_type="history_limit_orphan",
                    severity="low",
                    evidence=(
                        f"{len(surplus)} jobs exceed history limits "
                        f"(success_limit={success_limit}, failed_limit={failed_limit})"
                    ),
                    affected_jobs=surplus,
                )
            ]
        return []

    def _is_owned_by(self, job: object, uid: Optional[str]) -> bool:
        if not uid:
            return False
        refs = getattr(getattr(job, "metadata", None), "owner_references", None) or []
        return any(
            getattr(r, "kind", "") == "CronJob" and getattr(r, "uid", "") == uid
            for r in refs
        )
