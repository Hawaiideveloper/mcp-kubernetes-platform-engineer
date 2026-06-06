from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from auto_remediate.nim_models import Explanation, FixKind, Finding
from auto_remediate.nim_backend import FakeBackend, make_backend
from auto_remediate.finding_cache import CachedBackend, FindingCache
from auto_remediate.deterministic_table import lookup_candidates


@pytest.fixture
def sample_finding() -> Finding:
    return Finding(
        component_id="deploy/foo",
        kind="crashloop",
        severity="high",
        evidence="Pod restarted 10 times",
        diagnosis="OOM or misconfigured entrypoint",
        fix_class="rollout_restart",
        proposed_fix="kubectl rollout restart deploy/foo",
    )


@pytest.fixture
def tmp_cache(tmp_path: Path) -> FindingCache:
    return FindingCache(db_path=tmp_path / "test_cache.db")


class TestFakeBackend:
    @pytest.mark.asyncio
    async def test_call_count_increments(self, sample_finding: Finding) -> None:
        fb = FakeBackend(fixed_summary="ok")
        assert fb.call_count == 0
        await fb.explain(sample_finding)
        assert fb.call_count == 1
        await fb.explain(sample_finding)
        assert fb.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_explanation_with_candidates(self, sample_finding: Finding) -> None:
        fb = FakeBackend()
        exp = await fb.explain(sample_finding)
        assert isinstance(exp, Explanation)
        assert len(exp.fix_candidates) >= 1
        assert exp.finding_hash == sample_finding.cache_key()

    @pytest.mark.asyncio
    async def test_no_network_calls(self, sample_finding: Finding) -> None:
        with patch("socket.getaddrinfo", side_effect=OSError("no network")):
            fb = FakeBackend()
            exp = await fb.explain(sample_finding)
        assert exp.summary == "test summary"


class TestFindingCache:
    def test_get_miss_on_empty(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        result = tmp_cache.get(sample_finding, "model-a")
        assert result is None

    def test_set_then_get_hit(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        tmp_cache.set(sample_finding, "PAYLOAD", "model-a")
        result = tmp_cache.get(sample_finding, "model-a")
        assert result == "PAYLOAD"

    def test_model_id_mismatch_is_miss(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        tmp_cache.set(sample_finding, "PAYLOAD", "model-a")
        result = tmp_cache.get(sample_finding, "model-b")
        assert result is None

    def test_hit_rate(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        assert tmp_cache.hit_rate() == 0.0
        tmp_cache.set(sample_finding, "P", "model-a")
        tmp_cache.get(sample_finding, "model-a")
        tmp_cache.get(sample_finding, "model-b")
        assert tmp_cache.hit_rate() == pytest.approx(0.5)

    def test_evict_expired(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        now = time.time()
        tmp_cache._conn.execute(
            "INSERT OR REPLACE INTO explanation_cache "
            "(hash, finding_json, explanation, model_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                sample_finding.cache_key(),
                sample_finding.canonical_json(),
                "P",
                "model-a",
                now - 200,
                now - 1,
            ),
        )
        tmp_cache._conn.commit()
        evicted = tmp_cache.evict_expired()
        assert evicted == 1


class TestCachedBackend:
    @pytest.mark.asyncio
    async def test_cache_hit_second_call(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        fb = FakeBackend()
        cb = CachedBackend(fb, tmp_cache, "fake-model")
        exp1 = await cb.explain(sample_finding)
        assert not exp1.from_cache
        assert fb.call_count == 1
        exp2 = await cb.explain(sample_finding)
        assert exp2.from_cache
        assert fb.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_after_ttl(self, tmp_cache: FindingCache, sample_finding: Finding) -> None:
        fb = FakeBackend()
        cb = CachedBackend(fb, tmp_cache, "fake-model")
        await cb.explain(sample_finding)
        assert fb.call_count == 1
        future_time = time.time() + 8 * 24 * 3600
        with patch("auto_remediate.finding_cache.time") as mock_time:
            mock_time.time.return_value = future_time
            exp = await cb.explain(sample_finding)
        assert not exp.from_cache
        assert fb.call_count == 2


class TestMakeBackend:
    def test_returns_fake_when_no_key(self, tmp_cache: FindingCache) -> None:
        clean_env = {k: v for k, v in os.environ.items() if k not in ("NIM_API_KEY", "LLM_BACKEND")}
        with patch.dict(os.environ, clean_env, clear=True):
            backend = make_backend(tmp_cache)
        assert isinstance(backend, FakeBackend)

    def test_returns_fake_when_llm_backend_fake(self, tmp_cache: FindingCache) -> None:
        with patch.dict(os.environ, {"LLM_BACKEND": "fake"}):
            backend = make_backend(tmp_cache)
        assert isinstance(backend, FakeBackend)


class TestDeterministicTable:
    def test_crashloop_returns_rollout_restart(self, sample_finding: Finding) -> None:
        candidates = lookup_candidates(sample_finding)
        kinds = [c.kind for c in candidates]
        assert FixKind.ROLLOUT_RESTART in kinds

    def test_unknown_kind_returns_fallback(self) -> None:
        f = Finding(
            component_id="svc/bar",
            kind="unknown_weird_thing",
            severity="low",
            evidence="n/a",
            diagnosis="n/a",
            fix_class="unknown",
            proposed_fix="",
        )
        candidates = lookup_candidates(f)
        assert len(candidates) >= 1
        assert candidates[0].kind == FixKind.KUBECTL_PATCH

    def test_source_is_deterministic(self, sample_finding: Finding) -> None:
        candidates = lookup_candidates(sample_finding)
        for c in candidates:
            assert c.source == "deterministic"
