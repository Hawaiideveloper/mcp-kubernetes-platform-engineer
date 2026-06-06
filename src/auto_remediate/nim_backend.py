"""
nim_backend — NIM, Ollama, Fake LLM backends and backend factory (PRD §08).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from .nim_models import Explanation, FixCandidate, FixKind, Finding, LlmBackend

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
2. Rank the candidate fixes from most to least appropriate.
3. Respond ONLY with valid JSON:
   {
     "ranked_candidates": [
       {"rank": 1, "kind": "...", "command_or_diff": "...", "rationale": "..."}
     ],
     "top_pick_rank": 1,
     "summary": "One-sentence plain-English explanation."
   }
"""


def _deterministic_fallback(
    finding: Finding, candidates: list[FixCandidate]
) -> Explanation:
    return Explanation(
        finding_hash=finding.cache_key(),
        summary=f"[no LLM enrichment] {finding.diagnosis[:200]}",
        fix_candidates=candidates,
        raw_llm_text=None,
    )


def _parse_llm_response(
    raw: str, finding: Finding, candidates: list[FixCandidate]
) -> Explanation:
    log.debug("LLM raw output for %s: %s", finding.component_id, raw)
    try:
        data = json.loads(raw)
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
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            base_url=self._endpoint,
            api_key=self._api_key,
            timeout=self._timeout,
            max_retries=self.MAX_RETRIES,
        )

    async def explain(self, finding: Finding) -> Explanation:
        from jinja2 import Template

        from .deterministic_table import lookup_candidates

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


class OllamaBackend:
    """Local Ollama endpoint for development; same interface as NimBackend."""

    def __init__(self, endpoint_url: str = "http://localhost:11434") -> None:
        self._endpoint = endpoint_url
        self._nim = NimBackend(
            endpoint_url=f"{endpoint_url}/v1",
            model=os.environ.get("OLLAMA_MODEL", "llama3"),
            api_key="ollama",
        )

    async def explain(self, finding: Finding) -> Explanation:
        return await self._nim.explain(finding)


class FakeBackend:
    """Deterministic stub for unit tests; never makes network calls."""

    def __init__(self, fixed_summary: str = "test summary") -> None:
        self._summary = fixed_summary
        self.call_count = 0

    async def explain(self, finding: Finding) -> Explanation:
        self.call_count += 1
        from .deterministic_table import lookup_candidates

        candidates = lookup_candidates(finding)
        return Explanation(
            finding_hash=finding.cache_key(),
            summary=self._summary,
            fix_candidates=candidates,
        )


def make_backend(
    cache: object,  # FindingCache — avoid circular import at module level
) -> LlmBackend:
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
