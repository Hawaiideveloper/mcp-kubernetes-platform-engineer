# PRD Section 15 — vcluster Sandbox Lifecycle

## Purpose

Before any candidate fix touches a production namespace it is applied to a disposable vcluster.
Smoke tests run inside that vcluster. Only a green result allows auto-merge; a red result gates
the change behind a human-reviewed GitHub PR. This is the primary differentiator from k8sgpt,
which diagnoses but never validates a proposed change in isolation before promoting it.

---

## Architecture

### Host namespace layout

Each sandbox occupies a dedicated namespace on the host cluster named `sandbox-${run_id}`, where
`run_id` is a 12-character hex string (`secrets.token_hex(6)`). The vcluster control-plane
StatefulSet and syncer Pod run inside that namespace and are destroyed unconditionally at teardown.

### Lifecycle phases

```
create namespace
  -> vcluster create (connect=false, --distro k3s)
       -> poll Ready (timeout 60s)
            -> vcluster connect (write temp kubeconfig)
                 -> kubectl apply candidate manifest
                      -> kubectl apply stand-in workload probe
                           -> run smoke tests
                                -> capture events + logs -> sandbox.log
                                     -> vcluster delete --delete-namespace
```

Target wall-clock time: under 30 s for the common case. Sub-10 s runs are achievable when the
k3s image is already cached on the node.

---

## Why vcluster, not kind-in-a-container

| Property | vcluster | kind inside a container |
|---|---|---|
| Create latency | 3-8 s (k3s binary bundled in vcluster image) | 45-120 s (DinD setup + image pull) |
| Host API connectivity | Shares host node network; no bridge needed | Requires explicit port-forwarding |
| Privileges required | Normal Pod security context | Privileged (Docker daemon) |
| Cleanup | `vcluster delete` + `kubectl delete ns` | Container kill + volume prune |

On Apple silicon and on the `albright-runners` pool, kind-in-a-container requires privileged mode
and a full image pull on every run. vcluster reuses the k3s binary already present in the
vcluster image.

---

## vcluster CLI invocation

Install once per node:

```bash
curl -L -o /usr/local/bin/vcluster \
  "https://github.com/loft-sh/vcluster/releases/download/v0.19.7/vcluster-linux-amd64"
chmod +x /usr/local/bin/vcluster
```

Create:

```bash
vcluster create "sandbox-${run_id}" \
  --namespace "sandbox-${run_id}" \
  --distro k3s \
  --connect=false \
  --set "sync.fromHost.nodes.enabled=true" \
  --set "controlPlane.statefulSet.resources.requests.cpu=50m" \
  --set "controlPlane.statefulSet.resources.requests.memory=128Mi" \
  --timeout 60s
```

Connect (writes temp kubeconfig):

```bash
vcluster connect "sandbox-${run_id}" \
  --namespace "sandbox-${run_id}" \
  --kube-config "/tmp/sandbox-${run_id}.kubeconfig" \
  --background-proxy
```

Tear down:

```bash
vcluster delete "sandbox-${run_id}" \
  --namespace "sandbox-${run_id}" \
  --delete-namespace
```

Stand-in workload probe applied after the candidate manifest to confirm scheduling works:

```yaml
apiVersion: apps/v1
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
```

---

## Smoke test framework

### SmokeTest Protocol

```python
# src/vcluster_sandbox.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

@dataclass
class SmokeResult:
    passed: bool
    logs: str
    events: list[dict]

@runtime_checkable
class SmokeTest(Protocol):
    async def run(self, kubeconfig: Path) -> SmokeResult: ...
```

### Built-in tests keyed by fix_class

```python
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
        return SmokeResult(passed=proc.returncode == 0, logs=stdout.decode(), events=events)


class PodRunningSmoke:
    fix_class = "pod_restart"

    async def run(self, kubeconfig: Path) -> SmokeResult:
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            proc = await asyncio.create_subprocess_exec(
                "kubectl", "get", "pods", "-n", "default", "--no-headers",
                "-o", "custom-columns=STATUS:.status.phase",
                "--kubeconfig", str(kubeconfig),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            phases = stdout.decode().strip().splitlines()
            if phases and all(p.strip() == "Running" for p in phases):
                return SmokeResult(passed=True, logs=stdout.decode(),
                                   events=await _collect_events(kubeconfig))
            await asyncio.sleep(2)
        return SmokeResult(passed=False, logs="Timeout: pods did not reach Running",
                           events=await _collect_events(kubeconfig))


SMOKE_REGISTRY: dict[str, type] = {
    "pod_restart": PodRunningSmoke,
    "implement": DeploymentRolloutSmoke,
    "rewrite": DeploymentRolloutSmoke,
    "wire-up": DeploymentRolloutSmoke,
    "design": DeploymentRolloutSmoke,
    "resource_patch": DeploymentRolloutSmoke,
}
```

---

## Event and log capture

```python
async def _collect_events(kubeconfig: Path) -> list[dict]:
    proc = await asyncio.create_subprocess_exec(
        "kubectl", "get", "events", "-A", "-o", "json",
        "--kubeconfig", str(kubeconfig),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        return json.loads(stdout).get("items", [])
    except Exception:
        return []

def write_sandbox_log(run_id: str, manifest_yaml: str, smoke: SmokeResult,
                      base_dir: Path = Path("docs/audit-run-001/sandboxes")) -> Path:
    log_dir = base_dir / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "sandbox.log"
    log_path.write_text("\n".join([
        "=== applied manifest diff ===", manifest_yaml,
        "--- smoke test output ---", smoke.logs,
        "--- kubernetes events ---", json.dumps(smoke.events, indent=2),
    ]))
    return log_path
```

Output path: `docs/audit-run-001/sandboxes/<run_id>/sandbox.log`

---

## Concurrency

```python
import os, asyncio
_SANDBOX_SEM = asyncio.Semaphore(int(os.getenv("SANDBOX_CONCURRENCY", "5")))

async def run_sandbox(run_id: str, manifest_yaml: str, fix_class: str) -> SmokeResult:
    async with _SANDBOX_SEM:
        return await _sandbox_lifecycle(run_id, manifest_yaml, fix_class)
```

Maximum parallel sandboxes defaults to 5, configurable via `SANDBOX_CONCURRENCY`.

---

## Failure handling

If `_wait_vcluster_ready` returns `False` (vcluster did not reach Running within 60 s), the
lifecycle returns:

```python
SmokeResult(
    passed=False,
    logs="sandbox unavailable: vcluster did not reach Ready within 60s",
    events=[],
)
```

The caller must detect the `"sandbox unavailable:"` prefix and emit a finding of kind
`sandbox_unavailable` with `fix_class = "pr_only"`. No auto-merge is permitted for that finding;
it is queued for human review only.

---

## Integration test

```python
# tests/integration/test_vcluster_sandbox.py
import asyncio, subprocess
import pytest
from pathlib import Path
from src.vcluster_sandbox import run_sandbox, SmokeResult

KNOWN_BAD_MANIFEST = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: bad-deploy
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: bad-deploy
  template:
    metadata:
      labels:
        app: bad-deploy
    spec:
      containers:
        - name: main
          image: this-image-does-not-exist:never
          resources:
            requests:
              cpu: "1m"
              memory: "4Mi"
"""

@pytest.mark.integration
def test_known_bad_manifest_fails_smoke():
    run_id = "integ-bad-001"
    result: SmokeResult = asyncio.run(
        run_sandbox(run_id, KNOWN_BAD_MANIFEST, fix_class="implement")
    )
    assert not result.passed, f"Expected failure for bad image. logs: {result.logs}"
    log_path = Path(f"docs/audit-run-001/sandboxes/{run_id}/sandbox.log")
    assert log_path.exists()
    assert "bad-deploy" in log_path.read_text()

@pytest.mark.integration
def test_vcluster_destroyed_after_failure():
    run_id = "integ-teardown-001"
    asyncio.run(run_sandbox(run_id, KNOWN_BAD_MANIFEST, fix_class="implement"))
    r = subprocess.run(["kubectl", "get", "ns", f"sandbox-{run_id}"], capture_output=True)
    assert r.returncode != 0, f"Namespace sandbox-{run_id} still exists after teardown"
```

Run with:

```bash
pytest tests/integration/test_vcluster_sandbox.py -v --timeout=120 -m integration
```

Requires a reachable cluster (`KUBECONFIG` or `~/.kube/config`) and `vcluster` on `$PATH`.

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `SANDBOX_CONCURRENCY` | `5` | Max parallel vclusters |
| `SANDBOX_READY_TIMEOUT` | `60` | Seconds before abort and `sandbox_unavailable` finding |
| `SANDBOX_LOG_DIR` | `docs/audit-run-001/sandboxes` | Output directory for sandbox.log |
| `VCLUSTER_DISTRO` | `k3s` | Backing distro passed to `--distro` |
| `VCLUSTER_VERSION` | `0.19.7` | CLI version pinned in CI |
