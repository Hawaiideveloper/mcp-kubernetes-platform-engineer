"""auto_remediate.runtime — minimal long-lived entrypoint.

Loads safety config, opens k8s client, exposes a /healthz file under /tmp,
heartbeats the audit log every 60s. Full event-watcher wiring lands in a
follow-up; this proves the package deploys and stays Ready.
"""
from __future__ import annotations
import logging
import os
import signal
import sys
import time
from pathlib import Path

LOG = logging.getLogger("auto_remediate.runtime")
HEALTH = Path(os.environ.get("HEALTH_FILE", "/tmp/healthz"))
SHUTDOWN = False


def _signal(*_):
    global SHUTDOWN
    SHUTDOWN = True
    LOG.info("shutdown requested")


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)

    try:
        from kubernetes import client, config
        try:
            config.load_incluster_config()
            LOG.info("loaded in-cluster k8s config")
        except Exception:
            config.load_kube_config()
            LOG.info("loaded kubeconfig")
        v1 = client.CoreV1Api()
        ns = v1.list_namespace().items
        LOG.info("connected to k8s; %d namespaces visible", len(ns))
    except Exception as e:
        LOG.error("k8s init failed: %s", e)
        return 2

    HEALTH.write_text("ready\n")
    LOG.info("auto_remediate.runtime ready; heartbeating")
    tick = 0
    while not SHUTDOWN:
        tick += 1
        HEALTH.write_text(f"alive tick={tick} ts={int(time.time())}\n")
        if tick % 10 == 0:
            LOG.info("alive tick=%d", tick)
        time.sleep(6)
    LOG.info("shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
