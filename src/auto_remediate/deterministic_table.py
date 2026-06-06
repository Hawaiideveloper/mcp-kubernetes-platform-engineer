"""
deterministic_table — rule-based FixCandidate lookup table (PRD §08).

Maps finding (kind, severity) to deterministic FixCandidate objects used as
LLM context and as fallback when no LLM enrichment is available.
"""
from __future__ import annotations

from .nim_models import FixCandidate, FixKind, Finding


def lookup_candidates(finding: Finding) -> list[FixCandidate]:
    """Return deterministic fix candidates for a finding."""
    kind = finding.kind.lower()
    candidates: list[FixCandidate] = []

    if "crashloop" in kind or "crash" in kind:
        ns = (
            finding.component_id.split("/")[0]
            if "/" in finding.component_id
            else "default"
        )
        candidates.append(
            FixCandidate(
                kind=FixKind.ROLLOUT_RESTART,
                command_or_diff=(
                    f"kubectl rollout restart deploy/{finding.component_id} -n {ns}"
                ),
                rationale="Restart the deployment to clear transient crash state.",
                rank=1,
                source="deterministic",
            )
        )

    if "rbac" in kind or "permission" in kind or "unauthorized" in kind:
        candidates.append(
            FixCandidate(
                kind=FixKind.MANIFEST_DIFF,
                command_or_diff=(
                    "# Review RBAC bindings:\n"
                    f"kubectl get rolebindings,clusterrolebindings -A | grep {finding.component_id}"
                ),
                rationale="Audit RBAC bindings to identify excess permissions.",
                rank=1,
                source="deterministic",
            )
        )

    if "scale" in kind or "replica" in kind:
        candidates.append(
            FixCandidate(
                kind=FixKind.SCALE,
                command_or_diff=(
                    f"kubectl scale deploy/{finding.component_id} --replicas=1"
                ),
                rationale="Scale deployment to desired replica count.",
                rank=1,
                source="deterministic",
            )
        )

    if "label" in kind:
        candidates.append(
            FixCandidate(
                kind=FixKind.LABEL_EDIT,
                command_or_diff=(
                    f"kubectl label pod -l app={finding.component_id} "
                    "managed-by=platform-engineer --overwrite"
                ),
                rationale="Apply standard labels for resource ownership tracking.",
                rank=1,
                source="deterministic",
            )
        )

    if not candidates:
        candidates.append(
            FixCandidate(
                kind=FixKind.KUBECTL_PATCH,
                command_or_diff=(
                    f"kubectl describe {finding.component_id} 2>&1 | head -40"
                ),
                rationale="Inspect the resource to determine the appropriate fix.",
                rank=1,
                source="deterministic",
            )
        )

    return candidates
