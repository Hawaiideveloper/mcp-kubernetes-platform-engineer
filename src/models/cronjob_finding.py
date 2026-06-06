from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Literal, Optional


@dataclass
class CronJobFinding:
    name: str
    namespace: str
    issue_type: Literal[
        "missed_schedule",
        "repeated_backoff",
        "accidental_suspend",
        "history_limit_orphan",
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
