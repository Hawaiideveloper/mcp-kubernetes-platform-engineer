"""vcluster sandbox lifecycle -- US-015"""
from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

SANDBOX_CONCURRENCY: int = int(os.getenv("SANDBOX_CONCURRENCY", "5"))
SANDBOX_READY_TIMEOUT: int = int(os.getenv("SANDBOX_READY_TIMEOUT", "60"))
SANDBOX_LOG_DIR: str = os.getenv("SANDBOX_LOG_DIR", "docs/audit-run-001/sandboxes")
VCLUSTER_DISTRO: str = os.getenv("VCLUSTER_DISTRO", "k3s")

_SANDBOX_SEM = asyncio.Semaphore(SANDBOX_CONCURRENCY)


@dataclass
class SmokeResult:
    passed: bool
    logs: str
    events: list[dict] = field(default_factory=list)


@runtime_checkable
class SmokeTest(Protocol):
    async def run(self, kubeconfig: Path) -> SmokeResult:
        ...


PROBE_MANIFEST = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: sandbox-probe
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: sandbox-probe
  template:
    metadata:
      labels:
        app: sandbox-probe
    spec:
      containers:
        - name: probe
          image: gcr.io/google_containers/pause:3.9
          resources:
            requests:
              cpu: "1m"
              memory: "4Mi"
"""


async def _collect_events(kubeconfig: Path) -> list[dict]:
    proc = await asyncio.create_subprocess_exec(
        "kubectl", "get", "events", "-A", "-o", "json",
        "--kubeconfig", str(kubeconfig),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return json.loads(stdout).get("items", [])
    except Exception:
        return []


def write_sandbox_log(
    run_id: str,
    manifest_yaml: str,
    smoke: SmokeResult,
    base_dir: Path | None = None,
) -> Path:
    resolved_base = base_dir or Path(SANDBOX_LOG_DIR)
    log_dir = resolved_base / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "sandbox.log"
    sep = chr(10)
    log_path.write_text(sep.join([
        "=== applied manifest diff ===",
        manifest_yaml,
        "--- smoke test output ---",
        smoke.logs,
        "--- kubernetes events ---",
        json.dumps(smoke.events, indent=2),
    ]))
    return log_path


class DeploymentRolloutSmoke:
    fix_class = "implement"

    def __init__(self, deployment: str = "sandbox-probe", timeout: int = 25) -> None:
        self.deployment = deployment
        self.timeout = timeout

    async def run(self, kubeconfig: Path) -> SmokeResult:
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "rollout", "status",
            f"deployment/{self.deployment}",
            "--timeout", f"{self.timeout}s",
            "--kubeconfig", str(kubeconfig),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        events = await _collect_events(kubeconfig)
        return SmokeResult(
            passed=proc.returncode == 0,
            logs=stdout.decode(),
            events=events,
        )


class PodRunningSmoke:
    fix_class = "pod_restart"

    async def run(self, kubeconfig: Path) -> SmokeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 20
        while loop.time() < deadline:
            proc = await asyncio.create_subprocess_exec(
                "kubectl", "get", "pods", "-n", "default", "--no-headers",
                "-o", "custom-columns=STATUS:.status.phase",
                "--kubeconfig", str(kubeconfig),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            phases = stdout.decode().strip().splitlines()
            if phases and all(p.strip() == "Running" for p in phases):
                return SmokeResult(
                    passed=True,
                    logs=stdout.decode(),
                    events=await _collect_events(kubeconfig),
                )
            await asyncio.sleep(2)
        return SmokeResult(
            passed=False,
            logs="Timeout: pods did not reach Running",
            events=await _collect_events(kubeconfig),
        )


SMOKE_REGISTRY: dict[str, type] = {
    "pod_restart": PodRunningSmoke,
    "implement": DeploymentRolloutSmoke,
    "rewrite": DeploymentRolloutSmoke,
    "wire-up": DeploymentRolloutSmoke,
    "design": DeploymentRolloutSmoke,
    "resource_patch": DeploymentRolloutSmoke,
}


async def _run_cmd(*args: str, check: bool = False) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if check and proc.returncode != 0:
        raise RuntimeError(f"Command {args!r} failed: {stderr.decode()}")
    return proc.returncode or 0, stdout.decode(), stderr.decode()


async def _wait_vcluster_ready(run_id: str, namespace: str, timeout: int) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        rc, stdout, _ = await _run_cmd(
            "kubectl", "get", "pods", "-n", namespace,
            "-l", f"app=vcluster,release={run_id}",
            "--no-headers", "-o", "custom-columns=READY:.status.containerStatuses[0].ready",
        )
        if rc == 0 and "true" in stdout.lower():
            return True
        await asyncio.sleep(2)
    return False


async def _sandbox_lifecycle(run_id: str, manifest_yaml: str, fix_class: str) -> SmokeResult:
    namespace = f"sandbox-{run_id}"
    kubeconfig = Path(f"/tmp/sandbox-{run_id}.kubeconfig")  # noqa: S108
    try:
        await _run_cmd(
            "vcluster", "create", f"sandbox-{run_id}",
            "--namespace", namespace,
            "--distro", VCLUSTER_DISTRO,
            "--connect=false",
            "--set", "sync.fromHost.nodes.enabled=true",
            "--set", "controlPlane.statefulSet.resources.requests.cpu=50m",
            "--set", "controlPlane.statefulSet.resources.requests.memory=128Mi",
            "--timeout", f"{SANDBOX_READY_TIMEOUT}s",
        )
        ready = await _wait_vcluster_ready(run_id, namespace, SANDBOX_READY_TIMEOUT)
        if not ready:
            return SmokeResult(
                passed=False,
                logs="sandbox unavailable: vcluster did not reach Ready within 60s",
                events=[],
            )
        await _run_cmd(
            "vcluster", "connect", f"sandbox-{run_id}",
            "--namespace", namespace,
            "--kube-config", str(kubeconfig),
            "--background-proxy",
        )
        proc = await asyncio.create_subprocess_exec(
            "kubectl", "apply", "-f", "-",
            "--kubeconfig", str(kubeconfig),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        apply_out, _ = await proc.communicate(input=manifest_yaml.encode())
        if proc.returncode != 0:
            events = await _collect_events(kubeconfig)
            result = SmokeResult(
                passed=False,
                logs="kubectl apply failed: " + apply_out.decode(),
                events=events,
            )
            write_sandbox_log(run_id, manifest_yaml, result)
            return result
        probe_proc = await asyncio.create_subprocess_exec(
            "kubectl", "apply", "-f", "-",
            "--kubeconfig", str(kubeconfig),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await probe_proc.communicate(input=PROBE_MANIFEST.encode())
        smoke_cls = SMOKE_REGISTRY.get(fix_class, DeploymentRolloutSmoke)
        smoke_instance: SmokeTest = smoke_cls()  # type: ignore[call-arg]
        result = await smoke_instance.run(kubeconfig)
        write_sandbox_log(run_id, manifest_yaml, result)
        return result
    finally:
        await _run_cmd(
            "vcluster", "delete", f"sandbox-{run_id}",
            "--namespace", namespace,
            "--delete-namespace",
        )
        kubeconfig.unlink(missing_ok=True)


async def run_sandbox(run_id: str, manifest_yaml: str, fix_class: str) -> SmokeResult:
    """Public entry point. Runs a sandboxed smoke test with concurrency limit."""
    async with _SANDBOX_SEM:
        return await _sandbox_lifecycle(run_id, manifest_yaml, fix_class)


def new_run_id() -> str:
    """Generate a 12-char hex run_id."""
    return secrets.token_hex(6)
