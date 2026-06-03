# PRD Section 08 — NIM Backend + Finding-Hash Cache

## 1. Context

Audit findings `behavior:nim_backend_integration` (severity: high) and
`behavior:backend_cache` (severity: medium) both confirm that no LLM backend
interface and no explanation cache exist anywhere in `src/`. The server produces
zero AI-generated explanations despite README claims of intelligent analysis.
This section specifies the design that remedies both gaps.

LLMs are used exclusively to **explain** findings and **propose fixes**. They do
not execute commands or apply manifests. All actionable output is parsed into a
structured `FixCandidate` and surfaced to the operator; free-form text is logged
only.

---

## 2. Data Models

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FixKind(str, Enum):
    KUBECTL_PATCH = "kubectl_patch"
    MANIFEST_DIFF = "manifest_diff"
    ROLLOUT_RESTART = "rollout_restart"
    SCALE = "scale"
    LABEL_EDIT = "label_edit"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Finding:
    """Canonical representation of a single audit finding."""
    component_id: str
    kind: str
    severity: str
    evidence: str
    diagnosis: str
    fix_class: str
    proposed_fix: str
    # Increment when the finding schema changes to bust the cache.
    schema_version: int = 1

    def canonical_json(self) -> str:
        """Deterministic JSON for cache-key hashing."""
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "component_id": self.component_id,
                "kind": self.kind,
                "severity": self.severity,
                "evidence": self.evidence,
                "diagnosis": self.diagnosis,
                "fix_class": self.fix_class,
                "proposed_fix": self.proposed_fix,
            },
            sort_keys=True,
            ensure_ascii=True,
        )

    def cache_key(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass
class FixCandidate:
    """Structured fix proposed by the LLM or the deterministic table."""
    kind: FixKind
    command_or_diff: str      # e.g. "kubectl patch deploy/foo -p '...'" or a YAML diff
    rationale: str
    rank: int                 # 1 = top recommendation
    source: str               # "llm" | "deterministic"


@dataclass
class Explanation:
    finding_hash: str
    summary: str
    fix_candidates: list[FixCandidate]
    raw_llm_text: Optional[str] = None   # logged only, never executed
    from_cache: bool = False
```

---

## 3. `LlmBackend` Protocol

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmBackend(Protocol):
    """Pluggable LLM backend.  Implementations must be async-safe."""

    async def explain(self, finding: Finding) -> Explanation:
        """Return a structured Explanation for the given finding."""
        ...
```

### 3.1 `NimBackend` (default)

```python
import asyncio
import logging
import os
from openai import AsyncOpenAI

log = logging.getLogger(__name__)

_JINJA_TEMPLATE = """\
You are a senior Kubernetes SRE with deep expertise in cluster operations,
security hardening, and automated remediation.

## Finding
{{ finding.component_id }} (severity: {{ finding.severity }})

Evidence:
{{ finding.evidence }}

Diagnosis:
{{ finding.diagnosis }}

## Current fix_class from deterministic table
{{ finding.fix_class }}

## Candidate fixes from deterministic table (rank these)
{% for c in candidates %}
{{ loop.index }}. [{{ c.kind.value }}] {{ c.command_or_diff }}
{% endfor %}

## Instructions
1. Review the evidence and diagnosis.
2. Rank the candidate fixes from most to least appropriate for this exact finding.
3. Select the single best fix and provide:
   - kind: one of kubectl_patch | manifest_diff | rollout_restart | scale | label_edit | unknown
   - command_or_diff: the exact kubectl command or YAML diff to apply
   - rationale: one paragraph explaining why this fix addresses the root cause
4. If none of the candidates is appropriate, propose a new one under the same schema.
5. Respond ONLY with valid JSON matching this schema:
   {
     "ranked_candidates": [
       {"rank": 1, "kind": "...", "command_or_diff": "...", "rationale": "..."},
       ...
     ],
     "top_pick_rank": 1,
     "summary": "One-sentence plain-English explanation of the finding."
   }
   Do not include any text outside the JSON object.
"""


class NimBackend:
    """NVIDIA NIM chat-completions backend."""

    DEFAULT_MODEL = "meta/llama-3.1-70b-instruct"
    DEFAULT_TIMEOUT = 30.0
    MAX_RETRIES = 2

    def __init__(
        self,
        endpoint_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._endpoint = endpoint_url or os.environ["NIM_BASE_URL"]
        self._model = model or os.environ.get("NIM_MODEL", self.DEFAULT_MODEL)
        self._api_key = api_key or os.environ["NIM_API_KEY"]
        self._timeout = timeout
        self._client = AsyncOpenAI(
            base_url=self._endpoint,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=self.MAX_RETRIES,
        )

    async def explain(self, finding: Finding) -> Explanation:
        from jinja2 import Template
        from src.deterministic_table import lookup_candidates

        candidates = lookup_candidates(finding)
        prompt = Template(_JINJA_TEMPLATE).render(
            finding=finding, candidates=candidates
        )

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                raw = resp.choices[0].message.content or ""
                return _parse_llm_response(raw, finding, candidates)
            except Exception as exc:
                log.warning("NIMBackend attempt %d failed: %s", attempt + 1, exc)
                if attempt == self.MAX_RETRIES:
                    raise
                await asyncio.sleep(1.0)
        raise RuntimeError("unreachable")


def _parse_llm_response(
    raw: str, finding: Finding, candidates: list[FixCandidate]
) -> Explanation:
    """Parse structured JSON from the LLM response; log free-form text."""
    import json as _json

    log.debug("LLM raw output for %s: %s", finding.component_id, raw)
    try:
        data = _json.loads(raw)
        ranked = [
            FixCandidate(
                kind=FixKind(c.get("kind", "unknown")),
                command_or_diff=c["command_or_diff"],
                rationale=c["rationale"],
                rank=c["rank"],
                source="llm",
            )
            for c in data["ranked_candidates"]
        ]
        return Explanation(
            finding_hash=finding.cache_key(),
            summary=data.get("summary", ""),
            fix_candidates=ranked,
            raw_llm_text=raw,
        )
    except Exception as exc:
        log.warning(
            "Failed to parse LLM JSON for %s (%s); falling back to deterministic",
            finding.component_id,
            exc,
        )
        return _deterministic_fallback(finding, candidates)
```

### 3.2 `OllamaBackend` (local dev)

```python
class OllamaBackend:
    """Local Ollama endpoint for development; same interface as NimBackend."""

    def __init__(self, endpoint_url: str = "http://localhost:11434") -> None:
        self._endpoint = endpoint_url
        # Reuse NimBackend with overridden URL and a placeholder key.
        self._nim = NimBackend(
            endpoint_url=f"{endpoint_url}/v1",
            model=os.environ.get("OLLAMA_MODEL", "llama3"),
            api_key="ollama",
        )

    async def explain(self, finding: Finding) -> Explanation:
        return await self._nim.explain(finding)
```

### 3.3 `FakeBackend` (tests)

```python
class FakeBackend:
    """Deterministic stub for unit tests; never makes network calls."""

    def __init__(self, fixed_summary: str = "test summary") -> None:
        self._summary = fixed_summary
        self.call_count = 0

    async def explain(self, finding: Finding) -> Explanation:
        self.call_count += 1
        from src.deterministic_table import lookup_candidates
        candidates = lookup_candidates(finding)
        return Explanation(
            finding_hash=finding.cache_key(),
            summary=self._summary,
            fix_candidates=candidates,
        )
```

---

## 4. Deterministic Fallback

```python
def _deterministic_fallback(
    finding: Finding, candidates: list[FixCandidate]
) -> Explanation:
    """Used when the NIM backend is unreachable or returns unparseable output."""
    return Explanation(
        finding_hash=finding.cache_key(),
        summary=f"[no LLM enrichment] {finding.diagnosis[:200]}",
        fix_candidates=candidates,
        raw_llm_text=None,
    )
```

When `NimBackend.explain` raises after all retries, callers catch the exception
and call `_deterministic_fallback` directly. The operator receives a valid
`Explanation` with candidates from the rule table and a summary tag indicating
LLM enrichment was unavailable. No error is surfaced to end-users as a crash.

---

## 5. SQLite Finding-Hash Cache

```python
import sqlite3
import time
from pathlib import Path
from typing import Optional

_TTL_SECONDS = 7 * 24 * 3600   # 7 days
_HIT_COUNT = 0
_MISS_COUNT = 0


class FindingCache:
    """
    SQLite-backed cache keyed by sha256(finding.canonical_json()).
    Thread-safe for single-process use; not suitable for multi-replica without
    an external store.
    """

    def __init__(self, db_path: Path = Path("explanation_cache.db")) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS explanation_cache (
                hash        TEXT PRIMARY KEY,
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
```

The `model_id` column guards against cache poisoning: a cached entry produced by
`meta/llama-3.1-70b-instruct` will not be served when `NIM_MODEL` is changed to
a different model. The `schema_version` field on `Finding` ensures that any
change to the finding data model also busts existing cache entries because
`canonical_json()` embeds the version.

---

## 6. Backend Factory

```python
def make_backend(cache: FindingCache) -> LlmBackend:
    """
    Reads LLM_BACKEND env var (nim | ollama | fake).
    Defaults to nim if NIM_API_KEY is set, otherwise fake.
    """
    mode = os.environ.get("LLM_BACKEND", "").lower()
    if not mode:
        mode = "nim" if os.environ.get("NIM_API_KEY") else "fake"
    if mode == "nim":
        return NimBackend()
    if mode == "ollama":
        return OllamaBackend()
    return FakeBackend()
```

---

## 7. Failure Modes and Mitigations

| Failure | Behavior | Mitigation |
|---|---|---|
| NIM endpoint unreachable | `explain()` raises after 2 retries | Caller catches, uses `_deterministic_fallback`; operator sees `[no LLM enrichment]` prefix |
| NIM returns malformed JSON | `_parse_llm_response` logs warning, falls back | `raw_llm_text` preserved in log for debugging |
| NIM rate-limit (429) | OpenAI client retries with backoff (max 2) | After retries exhausted, falls back to deterministic |
| Cache entry expired | TTL check at read time returns miss | Re-invokes LLM, stores fresh entry |
| Cache poisoning via model change | `model_id` column mismatch = miss | New entry written with updated model_id |
| Finding schema change | `schema_version` bump changes hash | Old entries become unreachable and expire naturally |

---

## 8. Metrics

The `FindingCache.hit_rate()` method returns a float that the metrics endpoint
should expose as `explanation_cache_hit_rate_ratio`. A Prometheus gauge is
appropriate; the value is sampled on each scrape.

```python
# Example Prometheus registration (in metrics.py)
from prometheus_client import Gauge

CACHE_HIT_RATE = Gauge(
    "explanation_cache_hit_rate_ratio",
    "Fraction of LLM explanation requests served from SQLite cache",
)

def update_cache_metrics(cache: FindingCache) -> None:
    CACHE_HIT_RATE.set(cache.hit_rate())
```

---

## 9. Acceptance Criteria

1. `NimBackend.explain` passes `finding.canonical_json()` in the user message
   and returns an `Explanation` with at least one `FixCandidate`.
2. `FakeBackend` never makes network calls; `call_count` increments once per
   `explain` call.
3. Cache hit: calling `explain` twice with the same `Finding` invokes the
   backend exactly once; the second call sets `Explanation.from_cache = True`.
4. Cache miss after TTL: monkeypatching `time.time` past `expires_at` causes a
   re-invocation.
5. When `NIM_API_KEY` is absent and `LLM_BACKEND` is unset, `make_backend`
   returns a `FakeBackend` without raising.
6. Free-form `raw_llm_text` is written to the debug log and never passed to
   `subprocess`, `kubectl`, or any execution layer.
