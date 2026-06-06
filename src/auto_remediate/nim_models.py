"""
nim_models — data models for NIM LLM backend (PRD §08).

Finding, FixCandidate, Explanation, FixKind, LlmBackend protocol.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, runtime_checkable


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
    schema_version: int = 1

    def canonical_json(self) -> str:
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
    command_or_diff: str
    rationale: str
    rank: int
    source: str  # "llm" | "deterministic"


@dataclass
class Explanation:
    finding_hash: str
    summary: str
    fix_candidates: list[FixCandidate]
    raw_llm_text: Optional[str] = None
    from_cache: bool = False


@runtime_checkable
class LlmBackend(Protocol):
    """Pluggable LLM backend. Implementations must be async-safe."""

    async def explain(self, finding: Finding) -> Explanation:
        ...
