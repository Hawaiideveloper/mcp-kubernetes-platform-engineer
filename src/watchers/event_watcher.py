"""US-007: Cluster Event Stream Watcher — dedup, classify, SQLite queue."""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from prometheus_client import Counter

logger = logging.getLogger(__name__)

REASON_TO_FIX_CLASS: dict[tuple[str, str], str] = {
    ("BackOff", "Pod"): "restart-first-ladder",
    ("OOMKilling", "Pod"): "restart-first-ladder",
    ("ImagePullBackOff", "Pod"): "image-tag-migration",
    ("ErrImagePull", "Pod"): "image-tag-migration",
    ("FailedScheduling", "Pod"): "resource-shortage",
    ("FailedMount", "Pod"): "pvc-issue",
    ("FailedAttachVolume", "Pod"): "pvc-issue",
    ("Evicted", "Pod"): "resource-shortage",
    ("NodeNotReady", "Node"): "node-issue",
    ("FailedCreate", "ReplicaSet"): "resource-shortage",
    ("Killing", "Pod"): "ignored",
}

RATE_LIMITED_REASONS: dict[str, int] = {"Unhealthy": 120}
DEDUP_WINDOW_SECONDS: int = 60
QUEUE_DEPTH_LIMIT: int = 50

BACKPRESSURE_COUNTER = Counter(
    "event_watcher_backpressure_total",
    "Events dropped due to work queue depth limit",
)

_DDL = """
CREATE TABLE IF NOT EXISTS work_queue (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ns          TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    fix_class   TEXT    NOT NULL,
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    count       INTEGER NOT NULL DEFAULT 1,
    status      TEXT    NOT NULL DEFAULT 'queued'
                CHECK(status IN ('queued','claimed','resolved','escalated'))
);
CREATE INDEX IF NOT EXISTS idx_wq_status ON work_queue(status);
CREATE INDEX IF NOT EXISTS idx_wq_dedup  ON work_queue(ns, name, reason, last_seen);
"""


class EventStreamWatcher:
    """Watches the Kubernetes event stream and feeds a SQLite work queue."""

    def __init__(self, core_v1: Any, db_path: str, stop_event: Any = None) -> None:
        self._core_v1 = core_v1
        self._db_path = db_path
        self._stop_event = stop_event
        self._last_rv: str = ""
        self._rate_limit_seen: dict[tuple[str, str, str], float] = {}
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as con:
            con.executescript(_DDL)

    def _queue_depth(self) -> int:
        with sqlite3.connect(self._db_path) as con:
            row = con.execute(
                "SELECT COUNT(*) FROM work_queue WHERE status='queued'"
            ).fetchone()
        return int(row[0]) if row else 0

    def _upsert(self, ev: Any, fix_class: str) -> None:
        """Insert or increment a work-queue row within the dedup window."""
        ns = (ev.metadata.namespace or "") if ev.metadata else ""
        name = ev.involved_object.name if ev.involved_object else ""
        reason = ev.reason or ""
        kind = (ev.involved_object.kind or "") if ev.involved_object else ""
        now_iso = datetime.now(timezone.utc).isoformat()
        window_cutoff = datetime.now(timezone.utc).timestamp() - DEDUP_WINDOW_SECONDS
        window_iso = datetime.fromtimestamp(window_cutoff, tz=timezone.utc).isoformat()

        with sqlite3.connect(self._db_path) as con:
            row = con.execute(
                "SELECT id FROM work_queue WHERE ns=? AND name=? AND reason=? "
                "AND status='queued' AND last_seen > ?",
                (ns, name, reason, window_iso),
            ).fetchone()
            if row:
                con.execute(
                    "UPDATE work_queue SET count=count+1, last_seen=? WHERE id=?",
                    (now_iso, row[0]),
                )
            else:
                con.execute(
                    "INSERT INTO work_queue (ns,kind,name,reason,fix_class,first_seen,last_seen)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (ns, kind, name, reason, fix_class, now_iso, now_iso),
                )

    def classify(self, ev: Any) -> str:
        """Map event reason+kind to a fix_class string."""
        reason = ev.reason or ""
        kind = (ev.involved_object.kind or "") if ev.involved_object else ""
        return REASON_TO_FIX_CLASS.get((reason, kind), "unknown")

    def _is_rate_limited(self, ns: str, name: str, reason: str) -> bool:
        limit_secs = RATE_LIMITED_REASONS.get(reason)
        if limit_secs is None:
            return False
        key = (ns, name, reason)
        now = time.monotonic()
        last = self._rate_limit_seen.get(key, 0.0)
        if now - last < limit_secs:
            return True
        self._rate_limit_seen[key] = now
        return False

    def _consume_stream(self) -> None:
        """Process one watch stream connection."""
        from kubernetes import watch  # type: ignore[import-untyped]

        w = watch.Watch()
        for raw_event in w.stream(
            self._core_v1.list_event_for_all_namespaces,
            timeout_seconds=0,
            resource_version=self._last_rv,
        ):
            if self._stop_event and self._stop_event.is_set():
                w.stop()
                return

            ev_obj = raw_event.get("object")
            if ev_obj is None:
                continue

            if hasattr(ev_obj, "metadata") and ev_obj.metadata:
                rv = ev_obj.metadata.resource_version
                if rv:
                    self._last_rv = rv

            if getattr(ev_obj, "type", None) != "Warning":
                continue

            ns = (ev_obj.metadata.namespace or "") if ev_obj.metadata else ""
            name = ev_obj.involved_object.name if ev_obj.involved_object else ""
            reason = ev_obj.reason or ""

            if self._is_rate_limited(ns, name, reason):
                continue

            fix_class = self.classify(ev_obj)
            if fix_class == "ignored":
                continue

            if self._queue_depth() < QUEUE_DEPTH_LIMIT:
                self._upsert(ev_obj, fix_class)
            else:
                BACKPRESSURE_COUNTER.inc()
                logger.error("work queue depth at limit; classification paused")

    async def run(self) -> None:
        """Async reconnect loop — wraps _consume_stream with backoff."""
        import asyncio

        from kubernetes.client.exceptions import ApiException  # type: ignore[import-untyped]

        backoff = [1, 2, 4, 8, 16, 30]
        attempt = 0
        while not (self._stop_event and self._stop_event.is_set()):
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._consume_stream)
                attempt = 0
            except ApiException as exc:
                if exc.status == 410:
                    logger.warning("Got 410 Gone; resetting resource_version")
                    self._last_rv = ""
                else:
                    logger.error("ApiException in watcher: %s", exc)
                delay = backoff[min(attempt, len(backoff) - 1)]
                attempt += 1
                await asyncio.sleep(delay)
            except Exception as exc:  # noqa: BLE001
                logger.error("Unexpected watcher error: %s", exc)
                delay = backoff[min(attempt, len(backoff) - 1)]
                attempt += 1
                await asyncio.sleep(delay)
