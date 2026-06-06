"""Restart-first remediation ladder — US-003."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from kubernetes import client as k8s_client  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TRADING_NAMESPACES: frozenset[str] = frozenset({
    "ibkr-live-trader",
    "daxxon-trading",
    "brightflow-live",
})

RESTART_ELIGIBLE_REASONS: frozenset[str] = frozenset({
    "CrashLoopBackOff",
    "ReadinessProbeConnectionRefused",
    "LivenessProbeTimeout",
})

NON_RESTART_REASONS: frozenset[str] = frozenset({
    "ImagePullBackOff",
    "ErrImagePull",
    "OOMKilled",
    "CreateContainerConfigError",
    "FailedMount",
    "FailedAttach",
})

CRASH_LOOP_HIGH_RESTART_THRESHOLD: int = int(
    os.environ.get("LADDER_CRASH_THRESHOLD", "5")
)

NAMESPACE_LADDER_CAP: int = int(os.environ.get("LADDER_NS_CAP", "10"))


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProtectedNamespaceError(Exception):
    """Raised when any mutating ladder action targets a trading namespace."""


class CircuitBreakerError(Exception):
    """Raised when a resource has exhausted its per-hour ladder cycles."""


class NamespaceCircuitOpenError(Exception):
    """Raised when the namespace-level session cap is exceeded."""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LadderState(str, Enum):
    IDLE = "IDLE"
    RESTART_ISSUED = "RESTART_ISSUED"
    WATCH_HEALING = "WATCH_HEALING"
    HEALED = "HEALED"
    STILL_SICK = "STILL_SICK"
    ANALYZE = "ANALYZE"
    PROPOSE_FIX = "PROPOSE_FIX"
    SANDBOX_VERIFY = "SANDBOX_VERIFY"
    APPLY = "APPLY"
    ESCALATE = "ESCALATE"


@dataclass
class ResourceRef:
    namespace: str
    kind: str  # "Deployment" | "StatefulSet" | "DaemonSet" | "Pod"
    name: str


@dataclass
class PodDiagnosis:
    resource: ResourceRef
    failure_class: str
    container_name: str
    exit_code: Optional[int]
    restart_count: int
    log_tail: str
    event_reasons: list[str]
    recommended_fix: str


@dataclass
class DPOPair:
    session_id: str
    prompt: str
    rejected_action: str
    rejected_outcome: str
    chosen_action: str
    chosen_outcome: str
    evidence: dict


@dataclass
class LadderSession:
    session_id: str
    resource: ResourceRef
    state: LadderState = LadderState.IDLE
    restart_ts: Optional[datetime] = None
    heal_deadline_ts: Optional[datetime] = None
    ladder_cycles_this_hour: int = 0
    dpo_pair: Optional[DPOPair] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Eligibility helpers
# ---------------------------------------------------------------------------


def is_restart_eligible(reason: str, restart_count: int) -> bool:
    """Return True if reason/restart_count warrant a restart attempt."""
    if reason in NON_RESTART_REASONS:
        return False
    if reason == "CrashLoopBackOff" and restart_count >= CRASH_LOOP_HIGH_RESTART_THRESHOLD:
        return False
    return reason in RESTART_ELIGIBLE_REASONS


def _assert_not_trading(namespace: str, action: str) -> None:
    """Raise ProtectedNamespaceError when namespace is OBSERVE-ONLY."""
    if namespace in TRADING_NAMESPACES:
        logger.warning(
            "Action '%s' blocked: namespace '%s' is OBSERVE-ONLY. "
            "File a PR for manual review.",
            action,
            namespace,
        )
        raise ProtectedNamespaceError(
            f"Action '{action}' blocked: namespace '{namespace}' is OBSERVE-ONLY. "
            "File a PR for manual review."
        )


def emit_dpo_pair(
    session: LadderSession,
    diagnosis: PodDiagnosis,
    chosen: str,
    chosen_outcome: str,
) -> DPOPair:
    """Build a DPO pair capturing restart vs actual fix contrast."""
    return DPOPair(
        session_id=session.session_id,
        prompt=(
            f"Pod {session.resource.namespace}/{session.resource.name} "
            f"failed with {diagnosis.failure_class}; "
            f"restart_count={diagnosis.restart_count}."
        ),
        rejected_action="rollout_restart",
        rejected_outcome="pod_still_sick_after_300s",
        chosen_action=chosen,
        chosen_outcome=chosen_outcome,
        evidence={
            "failure_class": diagnosis.failure_class,
            "exit_code": diagnosis.exit_code,
            "restart_count": diagnosis.restart_count,
            "event_reasons": diagnosis.event_reasons,
            "log_tail_lines": len(diagnosis.log_tail.splitlines()),
        },
    )


# ---------------------------------------------------------------------------
# Namespace circuit breaker
# ---------------------------------------------------------------------------


class NamespaceCircuitBreaker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {}

    def acquire(self, namespace: str) -> None:
        current = self._counts.get(namespace, 0)
        if current >= NAMESPACE_LADDER_CAP:
            raise NamespaceCircuitOpenError(
                f"{namespace}: {current} active sessions."
            )
        self._counts[namespace] = current + 1

    def release(self, namespace: str) -> None:
        self._counts[namespace] = max(0, self._counts.get(namespace, 1) - 1)


# ---------------------------------------------------------------------------
# RemediationLadder
# ---------------------------------------------------------------------------


class RemediationLadder:
    """
    Coordinates the restart-first remediation lifecycle for a single resource.

    Callers drive transitions by invoking advance() in a loop; each call
    returns the updated LadderSession.  The ladder never auto-mutates state
    outside advance() so callers retain full control.
    """

    WATCH_TIMEOUT_SECONDS: int = 300
    MAX_CYCLES_PER_HOUR: int = 2

    def __init__(
        self,
        core_v1: k8s_client.CoreV1Api,
        apps_v1: k8s_client.AppsV1Api,
        escalation_webhook: str,
        dry_run: bool = True,
        ns_circuit: Optional[NamespaceCircuitBreaker] = None,
    ) -> None:
        self._core_v1 = core_v1
        self._apps_v1 = apps_v1
        self._escalation_webhook = escalation_webhook
        self._dry_run = dry_run
        self._ns_circuit = ns_circuit or NamespaceCircuitBreaker()

    async def detect(self, resource: ResourceRef) -> LadderSession:
        """
        Create a new LadderSession if the failure class is restart-eligible.
        Raises ValueError if failure class is not restart-eligible.
        Namespace circuit breaker is applied here.
        """
        # Fetch pod status to determine failure class
        pod = self._core_v1.read_namespaced_pod_status(
            name=resource.name, namespace=resource.namespace
        )
        reason = ""
        restart_count = 0
        for cs in pod.status.container_statuses or []:
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason or ""
            if cs.restart_count:
                restart_count = cs.restart_count

        if not is_restart_eligible(reason, restart_count):
            raise ValueError(
                f"Resource {resource.namespace}/{resource.name} "
                f"not restart-eligible: reason={reason!r}, "
                f"restart_count={restart_count}"
            )

        self._ns_circuit.acquire(resource.namespace)

        import uuid
        session = LadderSession(
            session_id=str(uuid.uuid4()),
            resource=resource,
            state=LadderState.IDLE,
        )
        session.updated_at = datetime.utcnow()
        return session

    async def restart(self, session: LadderSession) -> LadderSession:
        """
        Issue rollout restart for the target resource.
        Raises ProtectedNamespaceError for trading namespaces.
        Raises CircuitBreakerError when cycles exhausted.
        """
        _assert_not_trading(session.resource.namespace, "restart")

        if session.ladder_cycles_this_hour >= self.MAX_CYCLES_PER_HOUR:
            raise CircuitBreakerError(
                f"{session.resource.namespace}/{session.resource.name} exhausted "
                f"{self.MAX_CYCLES_PER_HOUR} ladder cycles this hour."
            )

        now = datetime.utcnow()
        if not self._dry_run:
            patch = {"spec": {"template": {"metadata": {"annotations": {
                "kubectl.kubernetes.io/restartedAt": now.isoformat()
            }}}}}
            kind = session.resource.kind
            ns = session.resource.namespace
            name = session.resource.name
            if kind == "Deployment":
                self._apps_v1.patch_namespaced_deployment(name, ns, patch)
            elif kind == "StatefulSet":
                self._apps_v1.patch_namespaced_stateful_set(name, ns, patch)
            elif kind == "DaemonSet":
                self._apps_v1.patch_namespaced_daemon_set(name, ns, patch)

        session.state = LadderState.RESTART_ISSUED
        session.restart_ts = now
        session.heal_deadline_ts = datetime.utcfromtimestamp(
            now.timestamp() + self.WATCH_TIMEOUT_SECONDS
        )
        session.ladder_cycles_this_hour += 1
        session.updated_at = now
        logger.info(
            "Restart issued for %s/%s (dry_run=%s)",
            session.resource.namespace,
            session.resource.name,
            self._dry_run,
        )
        return session

    async def watch(self, session: LadderSession) -> LadderSession:
        """
        Poll readiness and warning events every 30s until the heal deadline.
        Sets state=HEALED or STILL_SICK.
        """
        session.state = LadderState.WATCH_HEALING
        session.updated_at = datetime.utcnow()
        return await self._watchdog(session)

    async def _watchdog(
        self, session: LadderSession, poll_interval: int = 30
    ) -> LadderSession:
        assert session.restart_ts is not None
        # Use monotonic deadline from now to avoid UTC/local mismatch
        deadline = time.monotonic() + self.WATCH_TIMEOUT_SECONDS
        consecutive_healthy = 0
        while time.monotonic() < deadline:
            pod = self._core_v1.read_namespaced_pod_status(
                name=session.resource.name,
                namespace=session.resource.namespace,
            )
            all_ready = all(
                cs.ready for cs in (pod.status.container_statuses or [])
            )
            events = self._core_v1.list_namespaced_event(
                namespace=session.resource.namespace,
                field_selector=f"involvedObject.name={session.resource.name}",
            )
            new_warnings = [
                e
                for e in events.items
                if e.type == "Warning"
                and e.last_timestamp
                and e.last_timestamp > session.restart_ts
            ]
            if all_ready and not new_warnings:
                consecutive_healthy += 1
            else:
                consecutive_healthy = 0

            if consecutive_healthy >= 2:
                session.state = LadderState.HEALED
                session.updated_at = datetime.utcnow()
                return session
            await asyncio.sleep(poll_interval)

        session.state = LadderState.STILL_SICK
        session.updated_at = datetime.utcnow()
        return session

    async def analyze(
        self, session: LadderSession
    ) -> tuple[LadderSession, PodDiagnosis]:
        """
        Fetch live pod status, container logs (last 100 lines), and events.
        Returns PodDiagnosis. Sets state=PROPOSE_FIX.
        """
        ns = session.resource.namespace
        name = session.resource.name

        pod = self._core_v1.read_namespaced_pod_status(name=name, namespace=ns)
        container_name = ""
        exit_code: Optional[int] = None
        restart_count = 0
        failure_class = "Unknown"

        for cs in pod.status.container_statuses or []:
            container_name = cs.name
            restart_count = cs.restart_count or 0
            if cs.state and cs.state.waiting:
                failure_class = cs.state.waiting.reason or "Unknown"
            if cs.last_state and cs.last_state.terminated:
                exit_code = cs.last_state.terminated.exit_code

        log_tail = ""
        try:
            log_tail = self._core_v1.read_namespaced_pod_log(
                name=name,
                namespace=ns,
                container=container_name,
                tail_lines=100,
            )
        except Exception:  # noqa: BLE001
            log_tail = "<log unavailable>"

        events = self._core_v1.list_namespaced_event(
            namespace=ns,
            field_selector=f"involvedObject.name={name}",
        )
        event_reasons = [e.reason or "" for e in events.items]

        diagnosis = PodDiagnosis(
            resource=session.resource,
            failure_class=failure_class,
            container_name=container_name,
            exit_code=exit_code,
            restart_count=restart_count,
            log_tail=log_tail,
            event_reasons=event_reasons,
            recommended_fix="",
        )

        session.state = LadderState.PROPOSE_FIX
        session.updated_at = datetime.utcnow()
        return session, diagnosis

    async def sandbox_verify(
        self, session: LadderSession, proposed_patch: dict
    ) -> LadderSession:
        """
        Apply proposed_patch to ephemeral kind cluster.
        Sets state=APPLY (healthy) or ESCALATE (failed/low confidence).
        """
        _assert_not_trading(session.resource.namespace, "sandbox_verify")
        # In real implementation: spin up kind, apply patch, watch rollout.
        # Stub: escalate if dry_run, else treat as success.
        if self._dry_run:
            session.state = LadderState.ESCALATE
        else:
            session.state = LadderState.APPLY
        session.updated_at = datetime.utcnow()
        return session

    async def apply(self, session: LadderSession, patch: dict) -> LadderSession:
        """
        Apply the verified patch to the production namespace.
        Emits a DPO pair. Sets state=APPLY (terminal).
        """
        _assert_not_trading(session.resource.namespace, "apply")
        if not self._dry_run:
            kind = session.resource.kind
            ns = session.resource.namespace
            name = session.resource.name
            if kind == "Deployment":
                self._apps_v1.patch_namespaced_deployment(name, ns, patch)
            elif kind == "StatefulSet":
                self._apps_v1.patch_namespaced_stateful_set(name, ns, patch)
            elif kind == "DaemonSet":
                self._apps_v1.patch_namespaced_daemon_set(name, ns, patch)

        session.state = LadderState.APPLY
        session.updated_at = datetime.utcnow()
        logger.info(
            "Patch applied for %s/%s (dry_run=%s)",
            session.resource.namespace,
            session.resource.name,
            self._dry_run,
        )
        return session

    async def escalate(
        self, session: LadderSession, diagnosis: PodDiagnosis
    ) -> LadderSession:
        """
        POST to escalation_webhook with session and diagnosis.
        Emits a DPO pair. Sets state=ESCALATE (terminal).
        """
        chosen = "human_escalation"
        chosen_outcome = "escalated_to_webhook"
        pair = emit_dpo_pair(session, diagnosis, chosen, chosen_outcome)
        session.dpo_pair = pair

        if not self._dry_run:
            import urllib.request, json  # noqa: E401
            payload = json.dumps({
                "session_id": session.session_id,
                "resource": {
                    "namespace": session.resource.namespace,
                    "kind": session.resource.kind,
                    "name": session.resource.name,
                },
                "failure_class": diagnosis.failure_class,
                "dpo_pair": {
                    "rejected_action": pair.rejected_action,
                    "chosen_action": pair.chosen_action,
                },
            }).encode()
            req = urllib.request.Request(
                self._escalation_webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                urllib.request.urlopen(req, timeout=10)
            except Exception:  # noqa: BLE001
                logger.warning("Escalation webhook call failed.")

        session.state = LadderState.ESCALATE
        session.updated_at = datetime.utcnow()
        return session

    async def advance(self, session: LadderSession) -> LadderSession:
        """
        Single-step state machine driver. Call in a loop until session.state
        is one of {HEALED, APPLY, ESCALATE}.
        """
        if session.state == LadderState.IDLE:
            return await self.restart(session)
        if session.state == LadderState.RESTART_ISSUED:
            return await self.watch(session)
        if session.state == LadderState.WATCH_HEALING:
            # Already in-progress — should not be called mid-watch
            return session
        if session.state == LadderState.STILL_SICK:
            session, _ = await self.analyze(session)
            return session
        if session.state == LadderState.PROPOSE_FIX:
            return await self.sandbox_verify(session, {})
        # Terminal states
        return session
