"""
pr_generator.py — GitOps Auto-PR Generation (PRD §16).

Every proposed fix is expressed as a manifest diff committed to a GitOps repo.
Authentication is handled by GH_TOKEN env var via the gh CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DETERMINISTIC_FIX_CLASSES: frozenset[str] = frozenset(
    {"probe-fix", "resource-limit", "image-tag", "replica-count", "annotation-patch"}
)

TRADING_NAMESPACES: frozenset[str] = frozenset(
    {"ibkr-live-trader", "daxxon-trading", "brightflow-live"}
)

IDEMPOTENCY_MARKER = "<!-- auto-remediate:finding_id={fid} fix_id={xid} -->"

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "safety.yaml"


@dataclass
class Finding:
    finding_id: str
    severity: str
    namespace: str
    kind: str
    name: str
    fix_class: str
    events_block: str = ""
    logs_block: str = ""
    manifest_diff: str = ""


@dataclass
class SandboxResult:
    verdict: str
    sandbox_log_url: str = ""
    smoke_test_output: str = ""


@dataclass
class PRResult:
    pr_url: str
    pr_number: int
    was_existing: bool
    auto_merge_eligible: bool


def _load_gitops_config() -> dict[str, Any]:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("gitops", {})


def _repo_for_namespace(namespace: str, cfg: dict[str, Any]) -> tuple[str, str, str, str]:
    overrides: dict[str, Any] = cfg.get("repo_overrides", {})
    if namespace in overrides:
        ov = overrides[namespace]
        return (
            ov.get("repo", cfg.get("default_repo", "")),
            ov.get("base_branch", cfg.get("default_base_branch", "main")),
            ov.get("policy", "auto-merge"),
            ov.get("assignee", ""),
        )
    return (
        cfg.get("default_repo", ""),
        cfg.get("default_base_branch", "main"),
        "auto-merge",
        "",
    )


_MAX_TITLE = 120


def _build_title(finding: Finding) -> str:
    ns = finding.namespace
    kind = finding.kind.lower()
    name = finding.name
    fix_class = finding.fix_class
    prefix = f"[auto-remediate] ns/{ns} {kind}/"
    suffix = f": {fix_class}"
    max_name = _MAX_TITLE - len(prefix) - len(suffix)
    if len(name) > max_name:
        name = name[: max(0, max_name - 3)] + "..."
    return f"{prefix}{name}{suffix}"


_BODY_TEMPLATE = (
    "## Auto-Remediation Report\n\n"
    "**Finding ID:** `{finding_id}`\n"
    "**Severity:** `{severity}`\n"
    "**Namespace:** `{namespace}`\n"
    "**Resource:** `{kind}/{name}`\n"
    "**Fix class:** `{fix_class}`\n"
    "**Sandbox verified:** `{sandbox_green}`\n\n"
    "---\n\n"
    "## Evidence\n\n"
    "### Kubernetes Events\n\n"
    "```\n{events_block}\n```\n\n"
    "### Relevant Logs (last 100 lines)\n\n"
    "```\n{logs_block}\n```\n\n"
    "---\n\n"
    "## Proposed Manifest Diff\n\n"
    "```diff\n{manifest_diff}\n```\n\n"
    "---\n\n"
    "## Sandbox Run\n\n"
    "**Sandbox log:** {sandbox_log_url}\n\n"
    "**Smoke-test result:**\n\n"
    "```\n{smoke_test_output}\n```\n\n"
    "**Verdict:** {sandbox_verdict}\n\n"
    "---\n\n"
    "## Review Checklist\n\n"
    "- [ ] Diff is consistent with described fix class\n"
    "- [ ] No unrelated files changed\n"
    "- [ ] Smoke-test output confirms the symptom is resolved\n"
    "- [ ] Change is safe to apply to the live namespace\n\n"
    "{idempotency_key}\n"
)


def _build_body(finding: Finding, fix_id: str, sandbox: SandboxResult) -> str:
    return _BODY_TEMPLATE.format(
        finding_id=finding.finding_id,
        severity=finding.severity,
        namespace=finding.namespace,
        kind=finding.kind,
        name=finding.name,
        fix_class=finding.fix_class,
        sandbox_green=str(sandbox.verdict == "healed"),
        events_block=finding.events_block or "(none)",
        logs_block=finding.logs_block or "(none)",
        manifest_diff=finding.manifest_diff or "(empty diff)",
        sandbox_log_url=sandbox.sandbox_log_url or "N/A",
        smoke_test_output=sandbox.smoke_test_output or "(none)",
        sandbox_verdict=sandbox.verdict,
        idempotency_key=IDEMPOTENCY_MARKER.format(fid=finding.finding_id, xid=fix_id),
    )


def find_existing_pr(repo: str, finding_id: str, fix_id: str) -> dict[str, Any] | None:
    marker = IDEMPOTENCY_MARKER.format(fid=finding_id, xid=fix_id)
    result = subprocess.run(  # noqa: S603
        [  # noqa: S607
            "gh", "pr", "list",  # noqa: S607
            "--repo", repo,
            "--state", "open",
            "--search", f'"{marker}" in:body',
            "--json", "number,url",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    prs: list[dict[str, Any]] = json.loads(result.stdout or "[]")
    return prs[0] if prs else None


def _ensure_labels(
    repo: str,
    finding: Finding,
    sandbox: SandboxResult,
    extra: list[str],
) -> list[str]:
    labels: list[str] = [
        "auto-remediate",
        f"severity/{finding.severity}",
        f"fix-class/{finding.fix_class}",
    ]
    if sandbox.verdict == "healed":
        labels.append("sandbox-verified/true")
    else:
        labels.append("sandbox-verified/false")
    labels.extend(extra)
    for label in labels:
        subprocess.run(  # noqa: S603
            ["gh", "label", "create", label, "--force", "--repo", repo],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    return labels


def _is_auto_merge_eligible(
    finding: Finding,
    sandbox: SandboxResult,
    policy: str,
) -> bool:
    if policy == "pr-only":
        return False
    if finding.namespace in TRADING_NAMESPACES:
        return False
    if sandbox.verdict != "healed":
        return False
    if finding.fix_class not in DETERMINISTIC_FIX_CLASSES:
        return False
    allowed_env = os.environ.get("ALLOWED_AUTO_MERGE_NAMESPACES", "")
    allowed = {ns.strip() for ns in allowed_env.split(",") if ns.strip()}
    if not allowed:
        return False
    if finding.namespace not in allowed:
        return False
    return True


async def create_remediation_pr(
    finding: Finding,
    fix_id: str,
    sandbox: SandboxResult,
    dry_run: bool = False,
) -> PRResult:
    if not dry_run:
        dry_run = os.environ.get("GITOPS_DRY_RUN", "").lower() == "true"

    cfg = _load_gitops_config()
    repo, base_branch, policy, assignee = _repo_for_namespace(finding.namespace, cfg)

    title = _build_title(finding)
    body = _build_body(finding, fix_id, sandbox)

    if dry_run:
        sys.stdout.write(f"{title}\n\n{body}\n")
        return PRResult(
            pr_url="dry-run://not-created",
            pr_number=0,
            was_existing=False,
            auto_merge_eligible=False,
        )

    auto_merge = _is_auto_merge_eligible(finding, sandbox, policy)

    is_trading = finding.namespace in TRADING_NAMESPACES or policy == "pr-only"
    extra_labels: list[str] = []
    if is_trading or not auto_merge:
        extra_labels.append("human-review-required")

    existing = find_existing_pr(repo, finding.finding_id, fix_id)
    if existing:
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).isoformat()
        comment = (
            f"**Re-run at {timestamp}**\n\n"
            f"Sandbox verdict: {sandbox.verdict}\n"
            f"Auto-merge eligible: {auto_merge}\n"
        )
        subprocess.run(  # noqa: S603
            ["gh", "pr", "comment", str(existing["number"]),  # noqa: S607
             "--body", comment, "--repo", repo],
            capture_output=True, text=True, check=True,
        )
        return PRResult(
            pr_url=existing["url"],
            pr_number=existing["number"],
            was_existing=True,
            auto_merge_eligible=auto_merge,
        )

    _ensure_labels(repo, finding, sandbox, extra_labels)

    branch_name = f"auto-remediate/{finding.finding_id}-{fix_id}"
    create_cmd = [
        "gh", "pr", "create",
        "--repo", repo,
        "--base", base_branch,
        "--head", branch_name,
        "--title", title,
        "--body", body,
    ]
    for lbl in (["auto-remediate", f"severity/{finding.severity}",
                  f"fix-class/{finding.fix_class}"] + extra_labels):
        create_cmd += ["--label", lbl]

    pr_out = subprocess.run(  # noqa: S603
        create_cmd, capture_output=True, text=True, check=True,
    )
    pr_url = pr_out.stdout.strip()
    pr_number_str = pr_url.rstrip("/").split("/")[-1]
    pr_number = int(pr_number_str) if pr_number_str.isdigit() else 0

    if is_trading and assignee:
        subprocess.run(  # noqa: S603
            ["gh", "pr", "edit", str(pr_number),  # noqa: S607
             "--add-assignee", assignee, "--repo", repo],
            capture_output=True, text=True, check=False,
        )

    if auto_merge:
        subprocess.run(  # noqa: S603
            ["gh", "pr", "merge", "--auto", "--squash", "--delete-branch",  # noqa: S607
             str(pr_number), "--repo", repo],
            capture_output=True, text=True, check=False,
        )

    return PRResult(
        pr_url=pr_url,
        pr_number=pr_number,
        was_existing=False,
        auto_merge_eligible=auto_merge,
    )
