from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from kubernetes.client import AppsV1Api, CoreV1Api

logger = logging.getLogger(__name__)

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass(frozen=True)
class ResourceRef:
    kind: str
    namespace: str
    name: str
    uid: str


@dataclass(frozen=True)
class Evidence:
    events: tuple
    log_tail: str
    status_snapshot: str


@dataclass(frozen=True)
class Finding:
    resource: ResourceRef
    severity: Severity
    category: str
    evidence: Evidence
    suggested_fix_class: str
    root_cause_hypothesis: str

    def fingerprint(self) -> str:
        key = (
            f"{self.resource.kind}/{self.resource.namespace}"
            f"/{self.resource.name}/{self.category}"
        )
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint(),
            "resource": {
                "kind": self.resource.kind,
                "namespace": self.resource.namespace,
                "name": self.resource.name,
                "uid": self.resource.uid,
            },
            "severity": self.severity,
            "category": self.category,
            "evidence": {
                "events": list(self.evidence.events),
                "log_tail": self.evidence.log_tail,
                "status_snapshot": self.evidence.status_snapshot,
            },
            "suggested_fix_class": self.suggested_fix_class,
            "root_cause_hypothesis": self.root_cause_hypothesis,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class BaseAnalyzer(ABC):
    ANALYZER_ID: str = ""

    def __init__(
        self,
        core_v1: CoreV1Api,
        apps_v1: AppsV1Api,
        log_tail_lines: int = 100,
    ) -> None:
        self.core_v1 = core_v1
        self.apps_v1 = apps_v1
        self.log_tail_lines = log_tail_lines

    async def pre_check(self) -> bool:
        return True

    @abstractmethod
    async def analyze(self, namespace: Optional[str] = None) -> List[Finding]: ...

    async def run_safe(self, namespace: Optional[str] = None) -> List[Finding]:
        if not await self.pre_check():
            logger.info("analyzer %s: pre_check failed, skipping", self.ANALYZER_ID)
            return []
        try:
            findings = await self.analyze(namespace)
            seen: set = set()
            deduped: List[Finding] = []
            for f in findings:
                fp = f.fingerprint()
                if fp not in seen:
                    seen.add(fp)
                    deduped.append(f)
            return deduped
        except Exception as exc:
            logger.exception("analyzer %s raised: %s", self.ANALYZER_ID, exc)
            return []
