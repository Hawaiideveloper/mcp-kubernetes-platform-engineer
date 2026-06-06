"""Topological sort helper + canonical task seed for audit-run worklist."""
from __future__ import annotations

from collections import deque
from typing import Any


def topological_sort(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kahn's algorithm. tasks[i]['id'] is a stable integer (1-based).

    Raises ValueError on cycles.
    """
    id_to_task = {t["id"]: t for t in tasks}
    in_degree: dict[int, int] = {t["id"]: 0 for t in tasks}
    dependents: dict[int, list[int]] = {t["id"]: [] for t in tasks}

    for t in tasks:
        for blocker_id in t.get("blockers", []):
            in_degree[t["id"]] += 1
            dependents[blocker_id].append(t["id"])

    queue: deque[int] = deque(
        tid for tid, deg in sorted(in_degree.items()) if deg == 0
    )
    ordered: list[dict[str, Any]] = []

    while queue:
        tid = queue.popleft()
        ordered.append(id_to_task[tid])
        for dep in sorted(dependents[tid]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    if len(ordered) != len(tasks):
        cycle = [
            t["id"]
            for t in tasks
            if t["id"] not in {o["id"] for o in ordered}
        ]
        raise ValueError(f"Dependency cycle detected among task ids: {cycle}")

    return ordered


# Canonical seed payload (PRD §7 table — stable ids used as blocker refs)
CANONICAL_TASKS: list[dict[str, Any]] = [
    {
        "id": 1,
        "prd_section": "09",
        "title": "Implement BaseAnalyzer + Finding dataclass",
        "blockers": [],
        "deliverable_paths": ["src/analyzers/base.py", "tests/analyzers/test_base.py"],
    },
    {
        "id": 2,
        "prd_section": "09",
        "title": "Implement PodAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/pod_analyzer.py",
            "tests/analyzers/test_pod_analyzer.py",
        ],
    },
    {
        "id": 3,
        "prd_section": "10",
        "title": "Implement DeploymentAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/deployment_analyzer.py",
            "tests/analyzers/test_deployment_analyzer.py",
        ],
    },
    {
        "id": 4,
        "prd_section": "11",
        "title": "Implement NodeAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/node_analyzer.py",
            "tests/analyzers/test_node_analyzer.py",
        ],
    },
    {
        "id": 5,
        "prd_section": "12",
        "title": "Implement ServiceAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/service_analyzer.py",
            "tests/analyzers/test_service_analyzer.py",
        ],
    },
    {
        "id": 6,
        "prd_section": "13",
        "title": "Implement PVCAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/pvc_analyzer.py",
            "tests/analyzers/test_pvc_analyzer.py",
        ],
    },
    {
        "id": 7,
        "prd_section": "14",
        "title": "Implement IngressAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/ingress_analyzer.py",
            "tests/analyzers/test_ingress_analyzer.py",
        ],
    },
    {
        "id": 8,
        "prd_section": "15",
        "title": "Implement CronJobAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/cronjob_analyzer.py",
            "tests/analyzers/test_cronjob_analyzer.py",
        ],
    },
    {
        "id": 9,
        "prd_section": "16",
        "title": "Implement NetworkPolicyAnalyzer",
        "blockers": [1],
        "deliverable_paths": [
            "src/analyzers/network_policy_analyzer.py",
            "tests/analyzers/test_network_policy_analyzer.py",
        ],
    },
    {
        "id": 10,
        "prd_section": "03",
        "title": "Implement RestartFirstLadder remediator",
        "blockers": [],
        "deliverable_paths": [
            "src/remediators/restart_ladder.py",
            "tests/remediators/test_restart_ladder.py",
        ],
    },
    {
        "id": 11,
        "prd_section": "17",
        "title": "Implement deterministic remediation table + dispatch",
        "blockers": [1, 10],
        "deliverable_paths": [
            "src/remediators/table.py",
            "tests/remediators/test_table.py",
        ],
    },
    {
        "id": 12,
        "prd_section": "04",
        "title": "Implement five-minute watchdog asyncio task",
        "blockers": [2, 10],
        "deliverable_paths": ["src/watchdog.py", "tests/test_watchdog.py"],
    },
    {
        "id": 13,
        "prd_section": "05",
        "title": "Implement DPO pair extraction",
        "blockers": [2, 11],
        "deliverable_paths": ["src/dpo_extractor.py", "tests/test_dpo_extractor.py"],
    },
    {
        "id": 14,
        "prd_section": "06",
        "title": "Implement trading namespace hardblock",
        "blockers": [],
        "deliverable_paths": [
            "src/hardblock.py",
            "tests/test_hardblock.py",
            "src/config.py",
        ],
    },
    {
        "id": 15,
        "prd_section": "18",
        "title": "Implement vcluster sandbox execution pipeline",
        "blockers": [11],
        "deliverable_paths": ["src/sandbox.py", "tests/test_sandbox.py"],
    },
    {
        "id": 16,
        "prd_section": "19",
        "title": "Implement RBAC split (read/write service accounts)",
        "blockers": [],
        "deliverable_paths": [
            "src/rbac.py",
            "k8s/rbac.yaml",
            "tests/test_rbac.py",
        ],
    },
    {
        "id": 17,
        "prd_section": "20",
        "title": "Implement CI/CD workflow (ci.yml + image pinning)",
        "blockers": [],
        "deliverable_paths": [
            ".github/workflows/ci.yml",
            "k8s/deployment.yaml",
        ],
    },
    {
        "id": 18,
        "prd_section": "21",
        "title": "Implement audit log (JSONL append-only)",
        "blockers": [14, 16],
        "deliverable_paths": ["src/audit_log.py", "tests/test_audit_log.py"],
    },
    {
        "id": 19,
        "prd_section": "25",
        "title": "Implement WorklistDB + atomic claim",
        "blockers": [],
        "deliverable_paths": [
            "src/worklist.py",
            "src/worklist_seed.py",
            "tests/test_worklist.py",
        ],
    },
    {
        "id": 20,
        "prd_section": "08",
        "title": "Implement event stream watcher",
        "blockers": [2],
        "deliverable_paths": [
            "src/watchers/event_watcher.py",
            "tests/watchers/test_event_watcher.py",
        ],
    },
    {
        "id": 21,
        "prd_section": "07",
        "title": "Implement GitOps PR generation",
        "blockers": [11, 15],
        "deliverable_paths": ["src/gitops.py", "tests/test_gitops.py"],
    },
    {
        "id": 22,
        "prd_section": "02",
        "title": "Implement finding deduplication",
        "blockers": [1],
        "deliverable_paths": ["src/dedup.py", "tests/test_dedup.py"],
    },
    {
        "id": 23,
        "prd_section": "D0",
        "title": "Wire-up: seed worklist from PRD task table",
        "blockers": [19],
        "deliverable_paths": ["scripts/seed_worklist.py"],
    },
    {
        "id": 24,
        "prd_section": "D1",
        "title": "Wire-up: plug analyzers into mcp_server.py dispatch",
        "blockers": [2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 16, 18, 20, 22],
        "deliverable_paths": ["src/mcp_server.py"],
    },
    {
        "id": 25,
        "prd_section": "22",
        "title": "Implement acceptance-criteria gate (done_check.py)",
        "blockers": [17, 24],
        "deliverable_paths": [
            "src/done_check.py",
            "tests/test_done_check.py",
        ],
    },
]
