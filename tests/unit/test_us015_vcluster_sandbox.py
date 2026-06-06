"""Unit tests for US-015 vcluster sandbox lifecycle."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / 'src'))

from auto_remediate.vcluster_sandbox import (  # noqa: E402
    SMOKE_REGISTRY,
    DeploymentRolloutSmoke,
    PodRunningSmoke,
    SmokeResult,
    SmokeTest,
    new_run_id,
    write_sandbox_log,
)


def test_new_run_id_length() -> None:
    rid = new_run_id()
    assert len(rid) == 12


def test_new_run_id_hex() -> None:
    rid = new_run_id()
    int(rid, 16)


def test_new_run_id_unique() -> None:
    ids = {new_run_id() for _ in range(20)}
    assert len(ids) == 20


def test_smoke_result_default_events() -> None:
    r = SmokeResult(passed=True, logs='ok')
    assert r.events == []


def test_smoke_result_passed_false() -> None:
    r = SmokeResult(passed=False, logs='error', events=[{'type': 'Warning'}])
    assert not r.passed
    assert len(r.events) == 1


def test_deployment_rollout_smoke_is_protocol() -> None:
    assert isinstance(DeploymentRolloutSmoke(), SmokeTest)


def test_pod_running_smoke_is_protocol() -> None:
    assert isinstance(PodRunningSmoke(), SmokeTest)


def test_smoke_registry_keys() -> None:
    expected = {'pod_restart', 'implement', 'rewrite', 'wire-up', 'design', 'resource_patch'}
    assert expected == set(SMOKE_REGISTRY.keys())


def test_smoke_registry_pod_restart() -> None:
    assert SMOKE_REGISTRY['pod_restart'] is PodRunningSmoke


def test_smoke_registry_implement() -> None:
    assert SMOKE_REGISTRY['implement'] is DeploymentRolloutSmoke


def test_write_sandbox_log_creates_file(tmp_path: Path) -> None:
    result = SmokeResult(passed=True, logs='all good', events=[])
    log_path = write_sandbox_log('abc123', 'manifest: {}', result, base_dir=tmp_path)
    assert log_path.exists()
    assert log_path.name == 'sandbox.log'


def test_write_sandbox_log_content(tmp_path: Path) -> None:
    events = [{'type': 'Normal', 'reason': 'Scheduled'}]
    result = SmokeResult(passed=False, logs='timeout', events=events)
    log_path = write_sandbox_log('run-test', 'kind: Pod', result, base_dir=tmp_path)
    content = log_path.read_text()
    assert 'kind: Pod' in content
    assert 'timeout' in content
    assert 'Scheduled' in content


def test_write_sandbox_log_nested(tmp_path: Path) -> None:
    result = SmokeResult(passed=True, logs='ok')
    log_path = write_sandbox_log('nested-run', 'x: y', result, base_dir=tmp_path / 'deep' / 'dir')
    assert log_path.exists()


@pytest.mark.asyncio
async def test_deployment_rollout_smoke_passes() -> None:
    smoke = DeploymentRolloutSmoke(deployment='my-deploy', timeout=10)
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(b'successfully rolled out', None))
    with patch('auto_remediate.vcluster_sandbox.asyncio.create_subprocess_exec',
               new_callable=AsyncMock, return_value=fake_proc), \
         patch('auto_remediate.vcluster_sandbox._collect_events',
               new_callable=AsyncMock, return_value=[]):
        result = await smoke.run(Path('/tmp/fake.kubeconfig'))
    assert result.passed is True
    assert 'successfully rolled out' in result.logs


@pytest.mark.asyncio
async def test_deployment_rollout_smoke_fails() -> None:
    smoke = DeploymentRolloutSmoke()
    fake_proc = MagicMock()
    fake_proc.returncode = 1
    fake_proc.communicate = AsyncMock(return_value=(b'error: timed out', None))
    with patch('auto_remediate.vcluster_sandbox.asyncio.create_subprocess_exec',
               new_callable=AsyncMock, return_value=fake_proc), \
         patch('auto_remediate.vcluster_sandbox._collect_events',
               new_callable=AsyncMock, return_value=[]):
        result = await smoke.run(Path('/tmp/fake.kubeconfig'))
    assert result.passed is False


@pytest.mark.asyncio
async def test_pod_running_smoke_passes() -> None:
    smoke = PodRunningSmoke()
    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(b"Running", b""))
    with patch('auto_remediate.vcluster_sandbox.asyncio.create_subprocess_exec',
               new_callable=AsyncMock, return_value=fake_proc), \
         patch('auto_remediate.vcluster_sandbox._collect_events',
               new_callable=AsyncMock, return_value=[]):
        result = await smoke.run(Path('/tmp/fake.kubeconfig'))
    assert result.passed is True


@pytest.mark.asyncio
async def test_run_sandbox_unavailable_when_not_ready() -> None:
    from auto_remediate.vcluster_sandbox import run_sandbox
    with patch('auto_remediate.vcluster_sandbox._run_cmd',
               new_callable=AsyncMock, return_value=(0, '', '')), \
         patch('auto_remediate.vcluster_sandbox._wait_vcluster_ready',
               new_callable=AsyncMock, return_value=False):
        result = await run_sandbox('deadbeef1234', 'manifest: {}', 'implement')
    assert result.passed is False
    assert result.logs.startswith('sandbox unavailable:')


def test_sandbox_concurrency_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('SANDBOX_CONCURRENCY', '3')
    assert int(os.environ['SANDBOX_CONCURRENCY']) == 3
