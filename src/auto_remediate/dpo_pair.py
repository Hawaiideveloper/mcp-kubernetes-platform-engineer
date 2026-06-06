"""
dpo_pair.py — DPO pair schema and GitHub issue emission (PRD §05).

Defines Pydantic models for preference pairs and a helper that files
labeled GitHub issues so corey-coder can harvest them for fine-tuning.
"""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_REDACT_PATTERN = re.compile(
    r"(token|secret|password|key)=\S+",
    re.IGNORECASE,
)


def redact(line: str) -> str:
    """Replace secret-bearing values in a single line."""
    return _REDACT_PATTERN.sub(r"\1=[REDACTED]", line)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RemediationAction(BaseModel):
    action_type: str = Field(
        description="Kubernetes operation attempted, e.g. 'pod_restart', 'image_patch'."
    )
    command: str = Field(
        description="Exact kubectl / API call issued, redacted of secrets."
    )
    outcome: str = Field(
        description="Short outcome string: 'crashloop_recurred', 'timeout', 'api_error'."
    )
    duration_seconds: float = Field(
        description="Wall-clock seconds from action issue to outcome observed."
    )


class DpoPairContext(BaseModel):
    events: list[str] = Field(
        description=(
            "kubectl get events output lines for the target resource, "
            "redacted of secret-bearing tokens."
        )
    )
    logs: list[str] = Field(
        description=(
            "Last 50 lines of container logs at detection time, "
            "redacted of any line matching (token|secret|password|key)=\\S+."
        )
    )
    probe_state: dict[str, Any] = Field(
        description=(
            "Liveness/readiness probe status at detection: "
            "{'liveness': 'Failing', 'readiness': 'Failing', 'last_probe_time': '<iso>'}."
        )
    )
    namespace: str = Field(description="Kubernetes namespace of the affected resource.")
    kind: str = Field(description="Kubernetes resource kind, e.g. 'Deployment', 'Pod'.")


class DpoPairMeta(BaseModel):
    sandbox_verified: bool = Field(
        description="True if the chosen action was first validated in a kind/sandbox cluster."
    )
    prod_applied: bool = Field(
        description="True if the chosen action was applied to the production cluster."
    )
    time_to_fix_seconds: float = Field(
        description=(
            "Total elapsed seconds from symptom detection to verified healed state, "
            "covering all rejected attempts plus the chosen action."
        )
    )
    session_id: str = Field(
        description="UUID of the RemediationSession that produced this pair."
    )
    remediator_version: str = Field(
        description="Semver of the auto-remediator at the time of the session."
    )


class DpoPair(BaseModel):
    prompt: str = Field(
        description=(
            "Full cluster state at detection time: pod status, recent events, "
            "probe failure messages, and resource spec. "
            "This is the LLM input during inference."
        )
    )
    chosen: RemediationAction = Field(
        description="The single action that healed the cluster (verified by watchdog)."
    )
    rejected: list[RemediationAction] = Field(
        description=(
            "Ordered list of actions tried before the chosen action, "
            "each with its failure outcome. Must contain at least one entry."
        )
    )
    context: DpoPairContext = Field(
        description="Supporting evidence captured at detection time."
    )
    verification: str = Field(
        description=(
            "Raw kubectl output proving the healed state, e.g. "
            "'NAME   READY  STATUS   RESTARTS  AGE\\nnginx  1/1    Running  0         2m'."
        )
    )
    meta: DpoPairMeta = Field(
        description="Provenance and timing metadata for dataset curation."
    )


# ---------------------------------------------------------------------------
# Redaction helpers for full pairs
# ---------------------------------------------------------------------------

_TRADING_NAMESPACES: frozenset[str] = frozenset(
    {"brightflow-live", "ibkr-real-money-gateway", "daxxon-trading"}
)


def _redact_action(action: RemediationAction) -> RemediationAction:
    return action.model_copy(update={"command": redact(action.command)})


def redact_pair(pair: DpoPair) -> DpoPair:
    """Return a new DpoPair with all sensitive values redacted."""
    return pair.model_copy(
        update={
            "chosen": _redact_action(pair.chosen),
            "rejected": [_redact_action(r) for r in pair.rejected],
            "context": pair.context.model_copy(
                update={
                    "events": [redact(e) for e in pair.context.events],
                    "logs": [redact(lg) for lg in pair.context.logs],
                }
            ),
            "verification": redact(pair.verification),
        }
    )


# ---------------------------------------------------------------------------
# Emit guard
# ---------------------------------------------------------------------------


class DpoEmitSkipped(Exception):
    """Raised (not filed) when emission must be suppressed."""


def check_emit_allowed(
    pair: DpoPair,
    *,
    dry_run: bool = False,
    session_done: bool = True,
) -> None:
    """
    Validate that the pair may be filed as a GitHub issue.

    Raises:
        DpoEmitSkipped: If any suppression condition applies.
    """
    ns = pair.context.namespace
    if ns in _TRADING_NAMESPACES:
        raise DpoEmitSkipped(f"namespace '{ns}' is in the trading hard-skip list")
    if not pair.rejected:
        raise DpoEmitSkipped("no rejected actions — not a preference pair")
    if not session_done:
        raise DpoEmitSkipped("session is not in DONE state")
    if dry_run:
        raise DpoEmitSkipped("dry_run=True — no real cluster change occurred")


# ---------------------------------------------------------------------------
# Issue body rendering
# ---------------------------------------------------------------------------

_BODY_TEMPLATE = """\
<!-- dpo-pair-schema-version: 1 -->

## Prompt

```
{prompt}
```

## Chosen Action

- **type:** {chosen_type}
- **command:** `{chosen_command}`
- **outcome:** {chosen_outcome}
- **duration_seconds:** {chosen_duration}

## Rejected Actions

{rejected_section}

## Context

**Namespace:** {namespace}  
**Kind:** {kind}  
**Probe state:** {probe_state}

### Events

```
{events}
```

### Logs (at detection)

```
{logs}
```

## Verification (post-heal kubectl output)

```
{verification}
```

## Meta

```json
{meta_json}
```
"""


def _render_rejected(rejected: list[RemediationAction]) -> str:
    parts: list[str] = []
    for i, r in enumerate(rejected, start=1):
        parts.append(
            f"### Attempt {i}\n\n"
            f"- **type:** {r.action_type}\n"
            f"- **command:** `{r.command}`\n"
            f"- **outcome:** {r.outcome}\n"
            f"- **duration_seconds:** {r.duration_seconds}\n"
        )
    return "\n".join(parts)


def render_issue_body(pair: DpoPair) -> str:
    """Render the Markdown issue body from a DpoPair."""
    import json

    safe = redact_pair(pair)
    return _BODY_TEMPLATE.format(
        prompt=safe.prompt,
        chosen_type=safe.chosen.action_type,
        chosen_command=safe.chosen.command,
        chosen_outcome=safe.chosen.outcome,
        chosen_duration=safe.chosen.duration_seconds,
        rejected_section=_render_rejected(safe.rejected),
        namespace=safe.context.namespace,
        kind=safe.context.kind,
        probe_state=json.dumps(safe.context.probe_state),
        events="\n".join(safe.context.events),
        logs="\n".join(safe.context.logs),
        verification=safe.verification,
        meta_json=json.dumps(safe.meta.model_dump(), indent=2),
    )


def build_issue_title(pair: DpoPair) -> str:
    """Return '[DPO] <namespace>/<workload>: <symptom> -> <fix-class>' title."""
    component = f"{pair.context.namespace}/{pair.prompt.split()[0] if pair.prompt else 'unknown'}"
    symptom = pair.rejected[-1].outcome if pair.rejected else "unknown"
    fix_class = pair.chosen.action_type
    return f"[DPO] {component}: {symptom} -> {fix_class}"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

_DEFAULT_REPO = "AlbrightLaboratories/mcp-kubernetes-platform-engineer"


def resolve_dpo_repo(config_path: str | None = None) -> tuple[str, bool]:
    """
    Return (repo_slug, dpo_enabled) from config/dpo.yaml or env fallback.

    Falls back to GITHUB_REPOSITORY env var, then the hardcoded default.
    """
    try:
        import yaml  # type: ignore[import-untyped]

        cfg_file = config_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "config", "dpo.yaml"
        )
        with open(cfg_file) as fh:
            cfg = yaml.safe_load(fh) or {}
        repo = cfg.get("dpo_issue_repo") or os.environ.get(
            "GITHUB_REPOSITORY", _DEFAULT_REPO
        )
        enabled = bool(cfg.get("dpo_enabled", True))
        return repo, enabled
    except FileNotFoundError:
        repo = os.environ.get("GITHUB_REPOSITORY", _DEFAULT_REPO)
        return repo, True


# ---------------------------------------------------------------------------
# Label builder
# ---------------------------------------------------------------------------

_BASE_LABELS = ["dpo-pair", "auto-remediation", "corey-coder-ingest"]


def build_labels(pair: DpoPair) -> list[str]:
    """Return the full label list for the issue."""
    labels = list(_BASE_LABELS)
    labels.append(f"ns/{pair.context.namespace}")
    labels.append(f"kind/{pair.context.kind}")
    return labels
