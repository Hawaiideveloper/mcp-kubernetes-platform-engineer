"""Applier action audit logger (US-019, §18 schema).

Every write action taken by the applier ServiceAccount must produce a structured
audit record before the action proceeds. If the pre-action log write fails, the
action must not proceed. If the post-action log write fails, the session is marked
degraded and a critical alert is raised.

The APPLIER_SERVICE_ACCOUNT_NAME environment variable is authoritative for the
service_account field. It is never derived from the mounted token at runtime.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

logger = logging.getLogger(__name__)

ResourceKind = Literal["Deployment", "Service", "ConfigMap", "PVC", "Pod"]
Verb = Literal["patch", "update", "delete"]
Result = Literal["success", "error"]


def _service_account_name() -> str:
    """Return the applier SA name from the environment (authoritative source)."""
    name = os.environ.get("APPLIER_SERVICE_ACCOUNT_NAME", "auto-remediate-applier")
    if not name:
        raise RuntimeError(
            "APPLIER_SERVICE_ACCOUNT_NAME is not set; cannot emit audit record."
        )
    return name


def build_audit_record(
    *,
    namespace: str,
    resource_kind: ResourceKind,
    resource_name: str,
    verb: Verb,
    dry_run: bool,
    session_id: str,
    result: Result,
    error_detail: str | None = None,
) -> dict[str, Any]:
    """Build a structured audit record for an applier action.

    The service_account field is sourced from APPLIER_SERVICE_ACCOUNT_NAME
    and is never omitted or null.
    """
    return {
        "event": "applier_action",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "service_account": _service_account_name(),
        "namespace": namespace,
        "resource_kind": resource_kind,
        "resource_name": resource_name,
        "verb": verb,
        "dry_run": dry_run,
        "session_id": session_id,
        "result": result,
        "error_detail": error_detail,
    }


class ApplierAuditLogger:
    """Wraps applier write operations with mandatory pre/post audit logging.

    Usage::

        audit = ApplierAuditLogger(session_id="abc-123")
        with audit.record(namespace="ns", kind="Deployment", name="app", verb="patch"):
            k8s_client.patch_namespaced_deployment(...)
    """

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id: str = session_id or str(uuid.uuid4())
        self._degraded: bool = False

    @property
    def is_degraded(self) -> bool:
        """True if a post-action log write has failed during this session."""
        return self._degraded

    def _emit(self, record: dict[str, Any]) -> None:
        """Write a JSON audit record to the structured logger."""
        logger.info(json.dumps(record))

    def pre_action_log(
        self,
        *,
        namespace: str,
        resource_kind: ResourceKind,
        resource_name: str,
        verb: Verb,
        dry_run: bool,
    ) -> None:
        """Emit a pre-action audit record.

        Raises RuntimeError if the log write fails; callers must NOT proceed
        with the action when this raises.
        """
        record = build_audit_record(
            namespace=namespace,
            resource_kind=resource_kind,
            resource_name=resource_name,
            verb=verb,
            dry_run=dry_run,
            session_id=self.session_id,
            result="success",
            error_detail="pre-action",
        )
        try:
            self._emit(record)
        except Exception as exc:
            raise RuntimeError(
                f"Pre-action audit log failed for {verb} {resource_kind}/{resource_name} "
                f"in {namespace}: {exc}. Action will not proceed."
            ) from exc

    def post_action_log(
        self,
        *,
        namespace: str,
        resource_kind: ResourceKind,
        resource_name: str,
        verb: Verb,
        dry_run: bool,
        result: Result,
        error_detail: str | None = None,
    ) -> None:
        """Emit a post-action audit record.

        If the log write fails after the action has been taken, the session is
        marked degraded and a critical alert is surfaced. Does not raise.
        """
        record = build_audit_record(
            namespace=namespace,
            resource_kind=resource_kind,
            resource_name=resource_name,
            verb=verb,
            dry_run=dry_run,
            session_id=self.session_id,
            result=result,
            error_detail=error_detail,
        )
        try:
            self._emit(record)
        except Exception as exc:
            self._degraded = True
            logger.critical(
                "CRITICAL: post-action audit log failed — session marked degraded. "
                "Manual audit required. error=%s session_id=%s",
                exc,
                self.session_id,
            )
