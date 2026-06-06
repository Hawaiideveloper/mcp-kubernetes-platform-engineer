"""
roadmap.py — Sprint roadmap baseline tracker (PRD §01, Sprint 1).

Provides the canonical three-sprint roadmap as structured data so that CI,
dashboards, and acceptance-test suites can reference it without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class SprintStatus(str, Enum):
    """Lifecycle state of a sprint."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


@dataclass
class WorkItem:
    """A single item of work within a sprint."""

    title: str
    finding_refs: List[str] = field(default_factory=list)
    story_id: str = ""
    done: bool = False


@dataclass
class Sprint:
    """One delivery sprint with goal, exit criteria, and work items."""

    number: int
    name: str
    goal: str
    weeks: str
    exit_criterion: str
    status: SprintStatus = SprintStatus.PLANNED
    items: List[WorkItem] = field(default_factory=list)

    def completion_ratio(self) -> float:
        """Return fraction of items marked done (0.0–1.0)."""
        if not self.items:
            return 0.0
        return sum(1 for i in self.items if i.done) / len(self.items)


@dataclass
class Roadmap:
    """Authoritative three-sprint roadmap for mcp-kubernetes-platform-engineer."""

    sprints: List[Sprint] = field(default_factory=list)

    @classmethod
    def build_baseline(cls) -> "Roadmap":
        """Construct the PRD §01 baseline roadmap."""
        sprint1 = Sprint(
            number=1,
            name="Gut and Rebuild",
            goal=(
                "Replace all stubs with a real Kubernetes client, remove dead code, "
                "retract false claims, and establish a green CI baseline."
            ),
            weeks="1-2",
            exit_criterion=(
                "pytest green on mocked-client unit tests; "
                "kustomize build k8s/ succeeds on a clean clone; "
                "image builds and pushes to GHCR; "
                "no source file contains the string 'stub implementation'."
            ),
            items=[
                WorkItem(
                    "Add kubernetes Python client; implement initialize()",
                    finding_refs=[
                        "mcp-tool:execute_remediation",
                        "mcp-tool:get_recommendations",
                        "mcp-tool:diagnose_cluster_health",
                        "mcp-tool:performance_analysis",
                    ],
                    story_id="US-004",
                ),
                WorkItem(
                    "Trading-namespace hardblock: TRADING_BLOCKED_NAMESPACES + ProtectedNamespaceError",
                    finding_refs=["behavior:trading_ns_hardblock"],
                    story_id="US-001",
                    done=True,
                ),
                WorkItem(
                    "Wire enhanced_tools.py into mcp_server.py; remove dead-code stubs",
                    finding_refs=["src/enhanced_tools.py"],
                    story_id="US-005",
                ),
                WorkItem(
                    "Rewrite false-claim documentation files",
                    finding_refs=[
                        "README.md",
                        "CHANGELOG.md",
                        "GETTING_STARTED.md",
                        "functional_unit_test.md",
                        "coming_soon.md",
                    ],
                    story_id="US-002",
                ),
                WorkItem(
                    "Fix all shell scripts: set -euo pipefail, remove hardcoded paths",
                    finding_refs=[
                        "setup-vscode-k8s.sh",
                        "push-and-deploy.sh",
                        "logs.sh",
                        "stop.sh",
                    ],
                    story_id="US-003",
                ),
                WorkItem(
                    "Fix src/logger.py loguru exc_info misuse",
                    finding_refs=["src/logger.py"],
                    story_id="US-006",
                ),
                WorkItem(
                    "Fix k8s/kustomization.yaml missing .env files; pin image tag",
                    finding_refs=["k8s/kustomization.yaml"],
                    story_id="US-007",
                ),
                WorkItem(
                    "Implement structured append-only AuditLogger",
                    finding_refs=["behavior:audit_log"],
                    story_id="US-001",
                    done=True,
                ),
                WorkItem(
                    "Set up GitHub Actions CI baseline",
                    finding_refs=[],
                    story_id="US-008",
                ),
            ],
            status=SprintStatus.IN_PROGRESS,
        )

        sprint2 = Sprint(
            number=2,
            name="Analyzer Parity",
            goal=(
                "Implement the ~20 k8sgpt-equivalent analyzers using the real "
                "Kubernetes client wired in Sprint 1, backed by NIM inference."
            ),
            weeks="3-5",
            exit_criterion=(
                "kubectl get pods -A | grep -v Running is empty in a staging cluster "
                "after running the analyzer suite against deliberately-injected failures "
                "(one CrashLoopBackOff, one ImagePullBackOff, one Pending PVC) and the "
                "remediator resolves all three within 30 minutes."
            ),
            items=[
                WorkItem("PodAnalyzer", finding_refs=["behavior:analyzer_pod"], story_id="US-009"),
                WorkItem("PVCAnalyzer", finding_refs=["behavior:analyzer_pvc"], story_id="US-010"),
                WorkItem("EventStreamWatcher", finding_refs=["behavior:event_stream_watcher"], story_id="US-011"),
                WorkItem("FindingDeduplicator", finding_refs=["behavior:finding_dedup"], story_id="US-012"),
                WorkItem("FindingSerializer", finding_refs=["behavior:finding_serialization"], story_id="US-013"),
                WorkItem("NIM backend integration", finding_refs=["mcp-tool:get_recommendations"], story_id="US-014"),
            ],
        )

        sprint3 = Sprint(
            number=3,
            name="Differentiators",
            goal=(
                "Implement capabilities beyond k8sgpt: escalation state machine, "
                "vcluster sandbox, GitOps PR gate, and DPO learning loop."
            ),
            weeks="6-8",
            exit_criterion=(
                "A live cluster event (CrashLoopBackOff injected in staging namespace) "
                "triggers the full ladder, heals within 5 minutes as confirmed by the "
                "watchdog, produces a DPO pair emitted to GitHub, and the ibkr-live-trader "
                "namespace returns ProtectedNamespaceError when targeted by execute_remediation."
            ),
            items=[
                WorkItem("RemediationStateMachine + WorklistDB", finding_refs=["behavior:iteration_state_machine"], story_id="US-018"),
                WorkItem("Five-minute watchdog", finding_refs=["behavior:five_min_watchdog"], story_id="US-019"),
                WorkItem("vcluster sandbox protocol", story_id="US-020"),
                WorkItem("GitOps PR gate", finding_refs=["behavior:safety_allowlist"], story_id="US-021"),
                WorkItem("RBAC split: read vs write ServiceAccounts", finding_refs=["behavior:rbac_split"], story_id="US-022"),
                WorkItem("DPO pair extraction", finding_refs=["behavior:dpo_pair_extraction"], story_id="US-023"),
                WorkItem("Image-tag migration remediator", finding_refs=["behavior:image_tag_migration_remediation"], story_id="US-024"),
            ],
        )

        return cls(sprints=[sprint1, sprint2, sprint3])

    def sprint_by_number(self, n: int) -> Sprint | None:
        """Return the sprint with the given number, or None."""
        for s in self.sprints:
            if s.number == n:
                return s
        return None

    def overall_completion(self) -> float:
        """Return fraction of all work items that are done."""
        all_items = [item for s in self.sprints for item in s.items]
        if not all_items:
            return 0.0
        return sum(1 for i in all_items if i.done) / len(all_items)
