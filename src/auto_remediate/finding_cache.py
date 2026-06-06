"""
finding_cache — SQLite-backed explanation cache keyed by finding hash (PRD §08).
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

from .nim_models import Explanation, FixCandidate, FixKind, Finding, LlmBackend

_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_HIT_COUNT = 0
_MISS_COUNT = 0


class FindingCache:
    """
    SQLite-backed cache keyed by sha256(finding.canonical_json()).
    Thread-safe for single-process use.
    """

    def __init__(self, db_path: Path = Path("explanation_cache.db")) -> None:
        global _HIT_COUNT, _MISS_COUNT
        _HIT_COUNT = 0
        _MISS_COUNT = 0
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS explanation_cache (
                hash         TEXT PRIMARY KEY,
                finding_json TEXT NOT NULL,
                explanation  TEXT NOT NULL,
                model_id     TEXT NOT NULL,
                created_at   REAL NOT NULL,
                expires_at   REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def get(self, finding: Finding, model_id: str) -> Optional[str]:
        global _HIT_COUNT, _MISS_COUNT
        row = self._conn.execute(
            "SELECT explanation, expires_at, model_id FROM explanation_cache WHERE hash = ?",
            (finding.cache_key(),),
        ).fetchone()
        if row is None or time.time() > row[1] or row[2] != model_id:
            _MISS_COUNT += 1
            return None
        _HIT_COUNT += 1
        return row[0]

    def set(self, finding: Finding, explanation_json: str, model_id: str) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO explanation_cache
                (hash, finding_json, explanation, model_id, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                finding.cache_key(),
                finding.canonical_json(),
                explanation_json,
                model_id,
                now,
                now + _TTL_SECONDS,
            ),
        )
        self._conn.commit()

    def hit_rate(self) -> float:
        total = _HIT_COUNT + _MISS_COUNT
        return _HIT_COUNT / total if total else 0.0

    def evict_expired(self) -> int:
        cur = self._conn.execute(
            "DELETE FROM explanation_cache WHERE expires_at < ?", (time.time(),)
        )
        self._conn.commit()
        return cur.rowcount


class CachedBackend:
    """
    Wraps any LlmBackend with FindingCache: on hit returns cached Explanation;
    on miss calls backend and stores result.
    """

    def __init__(
        self, backend: LlmBackend, cache: FindingCache, model_id: str
    ) -> None:
        self._backend = backend
        self._cache = cache
        self._model_id = model_id

    async def explain(self, finding: Finding) -> Explanation:
        cached_json = self._cache.get(finding, self._model_id)
        if cached_json is not None:
            data = json.loads(cached_json)
            candidates = [
                FixCandidate(
                    kind=FixKind(c["kind"]),
                    command_or_diff=c["command_or_diff"],
                    rationale=c["rationale"],
                    rank=c["rank"],
                    source=c["source"],
                )
                for c in data["fix_candidates"]
            ]
            return Explanation(
                finding_hash=data["finding_hash"],
                summary=data["summary"],
                fix_candidates=candidates,
                raw_llm_text=data.get("raw_llm_text"),
                from_cache=True,
            )

        result = await self._backend.explain(finding)
        payload = json.dumps(
            {
                "finding_hash": result.finding_hash,
                "summary": result.summary,
                "fix_candidates": [
                    {
                        "kind": c.kind.value,
                        "command_or_diff": c.command_or_diff,
                        "rationale": c.rationale,
                        "rank": c.rank,
                        "source": c.source,
                    }
                    for c in result.fix_candidates
                ],
                "raw_llm_text": result.raw_llm_text,
            }
        )
        self._cache.set(finding, payload, self._model_id)
        return result
