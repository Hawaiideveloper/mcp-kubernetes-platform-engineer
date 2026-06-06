"""auto_remediate.runtime — observer loop wiring PodAnalyzer into the runtime.

Loads the k8s client (in-cluster), constructs PodAnalyzer, then every 30s
calls analyze() to surface Findings.  Each Finding is logged and appended to
/tmp/audit.log.  Findings are deduped within a 5-minute rolling window by
(namespace, kind, name, category).  /tmp/healthz is heartbeated so the
liveness probe keeps passing.  Shuts down cleanly on SIGTERM/SIGINT.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable, Deque, Tuple

LOG = logging.getLogger("auto_remediate.runtime")
HEALTH = Path(os.environ.get("HEALTH_FILE", "/tmp/healthz"))
AUDIT = Path(os.environ.get("AUDIT_LOG", "/tmp/audit.log"))
LOOP_INTERVAL = int(os.environ.get("LOOP_INTERVAL", "30"))
DEDUP_WINDOW = int(os.environ.get("DEDUP_WINDOW", "300"))  # 5 min

_SHUTDOWN = False

# Rolling dedup window: deque of (expires_at, dedup_key)
DedupeEntry = Tuple[float, str]
_SEEN: Deque[DedupeEntry] = deque()


def _signal(*_: object) -> None:
    global _SHUTDOWN
    _SHUTDOWN = True
    LOG.info("shutdown requested")


def _dedup_key(finding: object) -> str:
    r = finding.resource  # type: ignore[attr-defined]
    return f"{r.namespace}/{r.kind}/{r.name}/{finding.category}"  # type: ignore[attr-defined]


def _is_seen(key: str) -> bool:
    """Return True if key is within the dedup window; also prune expired entries."""
    now = time.time()
    while _SEEN and _SEEN[0][0] <= now:
        _SEEN.popleft()
    return any(k == key for _, k in _SEEN)


def _mark_seen(key: str) -> None:
    _SEEN.append((time.time() + DEDUP_WINDOW, key))


def _append_audit(line: str) -> None:
    try:
        with AUDIT.open("a") as fh:
            fh.write(line + "\n")
    except OSError as exc:
        LOG.error("audit write failed: %s", exc)


def _process_findings(findings: list) -> None:
    for finding in findings:
        key = _dedup_key(finding)
        if _is_seen(key):
            LOG.debug("deduped finding: %s", key)
            continue
        _mark_seen(key)
        r = finding.resource  # type: ignore[attr-defined]
        summary = (
            f"{r.namespace}/{r.kind}/{r.name} "
            f"sev={finding.severity} "  # type: ignore[attr-defined]
            f"cat={finding.category} "  # type: ignore[attr-defined]
            f"fp={finding.fingerprint()} "  # type: ignore[attr-defined]
            f"msg={finding.root_cause_hypothesis!r}"  # type: ignore[attr-defined]
        )
        LOG.info("finding: %s", summary)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _append_audit(f"{ts} {summary}")


async def _run_loop(
    analyzer: object,
    stop: Callable[[], bool] | None = None,
) -> None:
    """Observer loop.  stop() returns True when shutdown is requested.
    Defaults to reading the module-level _SHUTDOWN flag."""

    def _default_stop() -> bool:
        return _SHUTDOWN

    should_stop = stop if stop is not None else _default_stop

    tick = 0
    while not should_stop():
        tick += 1
        HEALTH.write_text(f"alive tick={tick} ts={int(time.time())}\n")
        try:
            findings = await analyzer.run_safe()  # type: ignore[attr-defined]
            LOG.info("tick=%d findings=%d", tick, len(findings))
            _process_findings(findings)
        except Exception as exc:
            LOG.exception("analyzer error: %s", exc)
        # Sleep in small slices so a stop() check wakes us quickly
        for _ in range(max(1, LOOP_INTERVAL * 2)):
            if should_stop():
                break
            await asyncio.sleep(0.5)


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)

    try:
        from kubernetes import client, config  # type: ignore[import]
        try:
            config.load_incluster_config()
            LOG.info("loaded in-cluster k8s config")
        except Exception:
            config.load_kube_config()
            LOG.info("loaded kubeconfig")
        core_v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
        ns_count = len(core_v1.list_namespace().items)
        LOG.info("connected to k8s; %d namespaces visible", ns_count)
    except Exception as exc:
        LOG.error("k8s init failed: %s", exc)
        return 2

    from analyzers.pod_analyzer import PodAnalyzer  # type: ignore[import]

    analyzer = PodAnalyzer(core_v1=core_v1, apps_v1=apps_v1)
    HEALTH.write_text("ready\n")
    LOG.info(
        "observer loop starting; interval=%ds dedup_window=%ds",
        LOOP_INTERVAL,
        DEDUP_WINDOW,
    )

    asyncio.run(_run_loop(analyzer))

    LOG.info("shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
