# PRD Section 05 — DPO Pair Issue Schema for corey-coder Ingest

**Repo:** mcp-kubernetes-platform-engineer  
**Source finding:** `behavior:dpo_pair_extraction` (severity: medium, fix_class: design)  
**Owner:** auto-remediator pipeline

---

## 1. Background

Every time the auto-remediator exhausts its cheap remediation path (e.g., pod restart,
rollout restart) and ultimately heals the cluster via an expensive path (image correction,
resource-limit patch, HPA reconfiguration), that session contains a naturally labelled
preference pair:

- **Rejected:** the sequence of actions that were tried and failed.
- **Chosen:** the action sequence that produced a verified healed state.

These pairs are filed as GitHub issues so the nightly `corey-coder` MCP audit loop can
harvest them, build a JSONL dataset, and feed a fine-tune run.

---

## 2. Pydantic Model — `DpoPair`

```python
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


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
```

---

## 3. GitHub Issue — Title Format

```
[DPO] <component>: <symptom> -> <fix-class>
```

**Examples:**

```
[DPO] payments/nginx: CrashLoopBackOff -> image_patch
[DPO] monitoring/prometheus: OOMKilled -> resource_limit_increase
[DPO] infra/coredns: NodeNotReady -> kubelet_restart
```

Rules:
- `<component>` is `<namespace>/<workload-name>`.
- `<symptom>` is the human-readable condition observed at detection (no codes).
- `<fix-class>` maps directly to `chosen.action_type`.

---

## 4. Issue Body Template

The following block is the verbatim contract that `corey-coder` MCP reads.
Do not alter field names or section headers without a matching consumer-side update.

````markdown
<!-- dpo-pair-schema-version: 1 -->

## Prompt

```
{{ dpo_pair.prompt }}
```

## Chosen Action

- **type:** {{ dpo_pair.chosen.action_type }}
- **command:** `{{ dpo_pair.chosen.command }}`
- **outcome:** {{ dpo_pair.chosen.outcome }}
- **duration_seconds:** {{ dpo_pair.chosen.duration_seconds }}

## Rejected Actions

{% for r in dpo_pair.rejected %}
### Attempt {{ loop.index }}

- **type:** {{ r.action_type }}
- **command:** `{{ r.command }}`
- **outcome:** {{ r.outcome }}
- **duration_seconds:** {{ r.duration_seconds }}

{% endfor %}

## Context

**Namespace:** {{ dpo_pair.context.namespace }}  
**Kind:** {{ dpo_pair.context.kind }}  
**Probe state:** {{ dpo_pair.context.probe_state | tojson }}

### Events

```
{{ dpo_pair.context.events | join('\n') }}
```

### Logs (at detection)

```
{{ dpo_pair.context.logs | join('\n') }}
```

## Verification (post-heal kubectl output)

```
{{ dpo_pair.verification }}
```

## Meta

```json
{{ dpo_pair.meta | tojson(indent=2) }}
```
````

---

## 5. Labels

Every filed issue carries this exact label set:

| Label | Purpose |
|---|---|
| `dpo-pair` | Primary harvest filter for corey-coder MCP |
| `auto-remediation` | Groups all remediator-generated issues |
| `corey-coder-ingest` | Signals dataset-ready status; remove to suppress ingest |
| `ns/<namespace>` | Namespace scoping, e.g. `ns/payments` |
| `kind/<kind>` | Resource kind, e.g. `kind/Deployment` |

The labels `ns/*` and `kind/*` are created on demand if they do not exist.

---

## 6. Where Issues Are Filed

**Default:** `mcp-kubernetes-platform-engineer` issues (this repo).

**Override via config:**

```yaml
# config/dpo.yaml
dpo_issue_repo: "AlbrightLaboratories/corey-coders"   # optional override
dpo_enabled: true
```

If `dpo_issue_repo` is absent or empty, the remediator resolves the repo from the
`GITHUB_REPOSITORY` environment variable set in CI, falling back to a hardcoded
`AlbrightLaboratories/mcp-kubernetes-platform-engineer`.

---

## 7. Privacy and Safety — Redaction

Before any log line or event string is embedded in the issue body, apply:

```python
import re

_REDACT_PATTERN = re.compile(
    r'(token|secret|password|key)=\S+',
    re.IGNORECASE,
)

def redact(line: str) -> str:
    return _REDACT_PATTERN.sub(r'\1=[REDACTED]', line)
```

- Applied to: `context.events`, `context.logs`, `chosen.command`, all `rejected[*].command`.
- The `verification` (post-heal kubectl output) is also passed through `redact()`.
- Redaction runs before serialization; the raw values never leave the process.

---

## 8. What NOT to Capture

Do not file a DPO issue when any of the following conditions is true:

1. **Trading namespace.** The namespace matches any of:
   `brightflow-live`, `ibkr-real-money-gateway`, `daxxon-trading`.
   These namespaces contain sensitive order-flow state. Hard-skip regardless of config.

2. **Single action only.** `len(session.rejected_actions) == 0`.
   A pair requires at least one rejected attempt. Without it there is no preference
   signal; filing would pollute the dataset with uncontested examples.

3. **Session not in DONE state.** Partial sessions contain incomplete evidence;
   only emit after the watchdog confirms healed.

4. **Dry-run mode.** When the remediator runs with `dry_run=True`, no issue is filed
   (no real cluster change occurred, so the chosen action is not verified).

---

## 9. corey-coder Consumer Contract

The `corey-coder` MCP nightly audit/repair/run loop (per project memory) polls
`mcp-kubernetes-platform-engineer` issues with label `corey-coder-ingest` and
`dpo-pair`. For each open issue it:

1. Parses the issue body between the `<!-- dpo-pair-schema-version: 1 -->` marker
   and extracts the `Prompt`, `Chosen Action`, `Rejected Actions`, and `Meta` sections.
2. Validates the extracted data against `DpoPair` (schema version must match).
3. Appends one JSONL record per pair to `datasets/dpo/dpo-<YYYY-MM-DD>.jsonl`
   in the `corey-coders` repo.
4. Closes the issue with label `dpo-ingested` and removes `corey-coder-ingest` to
   prevent double-ingest.
5. After accumulating 50+ records, triggers the fine-tune run via the NVIDIA NIM
   endpoint configured in `corey-coders/config/nim.yaml`.

**Schema version bumps** require a coordinated change to both the issue body template
(this PRD section) and the corey-coder parser. Bump `dpo-pair-schema-version` in the
HTML comment and in `corey-coders/src/dpo_ingester.py:SUPPORTED_VERSIONS`.

---

*Section 05 of 25 — DPO Pair Issue Schema for corey-coder Ingest*
