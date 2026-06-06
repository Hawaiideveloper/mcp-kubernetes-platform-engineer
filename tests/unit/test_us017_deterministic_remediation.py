"""
Unit tests for US-017: Deterministic Remediation Table.

Tests cover all 10 pure-function fixers plus the dispatch registry.
No external Kubernetes API calls — all state is passed as plain dicts.
"""
import pytest
from src.auto_remediate.deterministic_remediation import (
    Finding,
    FixCandidate,
    ImageTagMigration,
    ProbeTuning,
    OrphanJobCleanup,
    OOMKilledRestartWithBumpProposal,
    PVCResize,
    DNSConfigFix,
    NodeSelectorMismatch,
    TolerationMissing,
    HPAEnableMetricsServer,
    PDBTooStrict,
    KNOWN_MIGRATIONS,
    REGISTRY,
    dispatch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(**kwargs) -> Finding:
    defaults = dict(
        uid="uid-001",
        behavior="test",
        namespace="default",
        resource_kind="Deployment",
        resource_name="my-deploy",
        container_name="app",
        raw={},
    )
    defaults.update(kwargs)
    return Finding(**defaults)


# ---------------------------------------------------------------------------
# 1. ImageTagMigration
# ---------------------------------------------------------------------------

class TestImageTagMigration:
    def test_applies_to_matching(self):
        f = _finding(
            behavior="image_tag_migration_remediation",
            raw={"reason": "ImagePullBackOff", "current_image": "bitnami/kubectl:1.30"},
        )
        assert ImageTagMigration().applies_to(f)

    def test_does_not_apply_wrong_behavior(self):
        f = _finding(behavior="other", raw={"reason": "ImagePullBackOff"})
        assert not ImageTagMigration().applies_to(f)

    def test_does_not_apply_wrong_reason(self):
        f = _finding(
            behavior="image_tag_migration_remediation",
            raw={"reason": "ErrImagePull"},
        )
        assert not ImageTagMigration().applies_to(f)

    def test_generate_fix_known_image(self):
        f = _finding(
            behavior="image_tag_migration_remediation",
            raw={"reason": "ImagePullBackOff", "current_image": "bitnami/kubectl:1.30"},
            container_name="kubectl",
        )
        fix = ImageTagMigration().generate_fix(f, {})
        assert isinstance(fix, FixCandidate)
        assert fix.patch_type == "strategic-merge"
        assert "registry.k8s.io/kubectl:v1.30.12" in str(fix.payload)
        assert not fix.requires_review

    def test_generate_fix_unknown_image_raises(self):
        f = _finding(
            behavior="image_tag_migration_remediation",
            raw={"reason": "ImagePullBackOff", "current_image": "unknown/image:latest"},
        )
        with pytest.raises(ValueError, match="No migration mapping"):
            ImageTagMigration().generate_fix(f, {})

    def test_all_known_migrations_resolve(self):
        handler = ImageTagMigration()
        for old_img, new_img in KNOWN_MIGRATIONS.items():
            f = _finding(
                behavior="image_tag_migration_remediation",
                raw={"reason": "ImagePullBackOff", "current_image": old_img},
            )
            fix = handler.generate_fix(f, {})
            assert new_img in str(fix.payload)


# ---------------------------------------------------------------------------
# 2. ProbeTuning
# ---------------------------------------------------------------------------

class TestProbeTuning:
    def test_applies_to(self):
        f = _finding(behavior="probe_tuning_remediation")
        assert ProbeTuning().applies_to(f)

    def test_does_not_apply(self):
        f = _finding(behavior="something_else")
        assert not ProbeTuning().applies_to(f)

    def test_generate_fix_http_probe(self):
        f = _finding(
            behavior="probe_tuning_remediation",
            container_name="web",
            raw={"existing_liveness_probe": {"httpGet": {"path": "/health", "port": 8080}}},
        )
        fix = ProbeTuning().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"
        payload = fix.payload
        assert isinstance(payload, dict)
        containers = payload["spec"]["template"]["spec"]["containers"]
        assert containers[0]["startupProbe"]["failureThreshold"] == 30

    def test_generate_fix_no_existing_probe(self):
        f = _finding(behavior="probe_tuning_remediation", container_name="svc", raw={})
        fix = ProbeTuning().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"


# ---------------------------------------------------------------------------
# 3. OrphanJobCleanup
# ---------------------------------------------------------------------------

class TestOrphanJobCleanup:
    def test_applies_to(self):
        f = _finding(behavior="orphan_job_remediation", resource_kind="Job")
        assert OrphanJobCleanup().applies_to(f)

    def test_does_not_apply_wrong_kind(self):
        f = _finding(behavior="orphan_job_remediation", resource_kind="Deployment")
        assert not OrphanJobCleanup().applies_to(f)

    def test_generate_fix(self):
        f = _finding(
            behavior="orphan_job_remediation",
            resource_kind="Job",
            resource_name="stale-job",
            namespace="batch",
        )
        fix = OrphanJobCleanup().generate_fix(f, {})
        assert fix.patch_type == "kubectl-cmd"
        assert "stale-job" in str(fix.payload)
        assert fix.requires_review


# ---------------------------------------------------------------------------
# 4. OOMKilledRestartWithBumpProposal
# ---------------------------------------------------------------------------

class TestOOMKilledRestartWithBumpProposal:
    def test_applies_to(self):
        f = _finding(raw={"reason": "OOMKilled"})
        assert OOMKilledRestartWithBumpProposal().applies_to(f)

    def test_does_not_apply(self):
        f = _finding(raw={"reason": "Completed"})
        assert not OOMKilledRestartWithBumpProposal().applies_to(f)

    def test_generate_fix_default_bump(self):
        # 512 MiB in bytes
        mem_bytes = 512 * 2**20
        f = _finding(
            raw={"reason": "OOMKilled", "current_memory_limit_bytes": mem_bytes},
            container_name="worker",
        )
        fix = OOMKilledRestartWithBumpProposal().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"
        assert fix.requires_review
        desc = fix.description
        assert "512Mi" in desc
        assert "665Mi" in desc  # 512 * 1.30 = 665.6 -> 665

    def test_generate_fix_custom_bump(self):
        mem_bytes = 1024 * 2**20  # 1 GiB
        f = _finding(
            raw={"reason": "OOMKilled", "current_memory_limit_bytes": mem_bytes, "bump_percent": 50},
            container_name="heavy",
        )
        fix = OOMKilledRestartWithBumpProposal().generate_fix(f, {})
        assert "1536Mi" in fix.description  # 1024 * 1.5


# ---------------------------------------------------------------------------
# 5. PVCResize
# ---------------------------------------------------------------------------

class TestPVCResize:
    def test_applies_to(self):
        f = _finding(
            resource_kind="PersistentVolumeClaim",
            raw={"storage_class_allow_expansion": True, "usage_percent": 90},
        )
        assert PVCResize().applies_to(f)

    def test_does_not_apply_no_expansion(self):
        f = _finding(
            resource_kind="PersistentVolumeClaim",
            raw={"storage_class_allow_expansion": False, "usage_percent": 90},
        )
        assert not PVCResize().applies_to(f)

    def test_does_not_apply_low_usage(self):
        f = _finding(
            resource_kind="PersistentVolumeClaim",
            raw={"storage_class_allow_expansion": True, "usage_percent": 70},
        )
        assert not PVCResize().applies_to(f)

    def test_generate_fix_default_growth(self):
        f = _finding(
            resource_kind="PersistentVolumeClaim",
            resource_name="data-pvc",
            raw={"storage_class_allow_expansion": True, "usage_percent": 90, "capacity_gi": 10},
        )
        fix = PVCResize().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"
        assert "15Gi" in str(fix.payload)  # 10 * 1.5 = 15


# ---------------------------------------------------------------------------
# 6. DNSConfigFix
# ---------------------------------------------------------------------------

class TestDNSConfigFix:
    def test_applies_to(self):
        f = _finding(behavior="dns_resolution_failure")
        assert DNSConfigFix().applies_to(f)

    def test_generate_fix_default_dns(self):
        f = _finding(behavior="dns_resolution_failure", namespace="prod", resource_name="api")
        fix = DNSConfigFix().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"
        spec = fix.payload["spec"]["template"]["spec"]  # type: ignore[index]
        assert spec["dnsPolicy"] == "ClusterFirst"
        assert "10.96.0.10" in spec["dnsConfig"]["nameservers"]

    def test_generate_fix_custom_dns(self):
        f = _finding(behavior="dns_resolution_failure", namespace="prod", resource_name="api")
        fix = DNSConfigFix().generate_fix(f, {"cluster_dns_ip": "10.0.0.53"})
        spec = fix.payload["spec"]["template"]["spec"]  # type: ignore[index]
        assert "10.0.0.53" in spec["dnsConfig"]["nameservers"]


# ---------------------------------------------------------------------------
# 7. NodeSelectorMismatch
# ---------------------------------------------------------------------------

class TestNodeSelectorMismatch:
    def test_applies_to(self):
        f = _finding(raw={"reason": "Unschedulable", "message": "MatchNodeSelector"})
        assert NodeSelectorMismatch().applies_to(f)

    def test_does_not_apply(self):
        f = _finding(raw={"reason": "Unschedulable", "message": "InsufficientCPU"})
        assert not NodeSelectorMismatch().applies_to(f)

    def test_generate_fix(self):
        f = _finding(
            raw={
                "reason": "Unschedulable",
                "message": "MatchNodeSelector",
                "mismatched_label_key": "topology.zone",
            }
        )
        state = {"node_label_values": {"topology.zone": ["us-east-1a", "us-east-1b"]}}
        fix = NodeSelectorMismatch().generate_fix(f, state)
        assert "us-east-1a" in str(fix.payload)
        assert fix.requires_review

    def test_generate_fix_no_nodes_raises(self):
        f = _finding(
            raw={
                "reason": "Unschedulable",
                "message": "MatchNodeSelector",
                "mismatched_label_key": "topology.zone",
            }
        )
        with pytest.raises(ValueError, match="No nodes carry label"):
            NodeSelectorMismatch().generate_fix(f, {})


# ---------------------------------------------------------------------------
# 8. TolerationMissing
# ---------------------------------------------------------------------------

class TestTolerationMissing:
    def test_applies_to(self):
        f = _finding(raw={"reason": "Unschedulable", "message": "had untolerated taint"})
        assert TolerationMissing().applies_to(f)

    def test_does_not_apply(self):
        f = _finding(raw={"reason": "Unschedulable", "message": "InsufficientMemory"})
        assert not TolerationMissing().applies_to(f)

    def test_generate_fix(self):
        f = _finding(
            raw={
                "reason": "Unschedulable",
                "message": "had untolerated taint",
                "blocking_taint": {"key": "gpu", "effect": "NoSchedule", "value": "true"},
            }
        )
        fix = TolerationMissing().generate_fix(f, {})
        assert fix.patch_type == "strategic-merge"
        tolerations = fix.payload["spec"]["template"]["spec"]["tolerations"]  # type: ignore[index]
        assert tolerations[0]["key"] == "gpu"
        assert fix.requires_review


# ---------------------------------------------------------------------------
# 9. HPAEnableMetricsServer
# ---------------------------------------------------------------------------

class TestHPAEnableMetricsServer:
    def test_applies_to(self):
        f = _finding(
            resource_kind="HorizontalPodAutoscaler",
            raw={"message": "unable to get metrics for resource cpu"},
        )
        assert HPAEnableMetricsServer().applies_to(f)

    def test_does_not_apply_wrong_kind(self):
        f = _finding(
            resource_kind="Deployment",
            raw={"message": "unable to get metrics for resource cpu"},
        )
        assert not HPAEnableMetricsServer().applies_to(f)

    def test_generate_fix_install(self):
        f = _finding(
            resource_kind="HorizontalPodAutoscaler",
            raw={"message": "unable to get metrics for resource cpu"},
        )
        fix = HPAEnableMetricsServer().generate_fix(f, {"metrics_server_deployed": False})
        assert "kubectl apply -f" in str(fix.payload)

    def test_generate_fix_rbac_repair(self):
        f = _finding(
            resource_kind="HorizontalPodAutoscaler",
            raw={"message": "unable to get metrics for resource cpu"},
        )
        fix = HPAEnableMetricsServer().generate_fix(f, {"metrics_server_deployed": True})
        assert "clusterrolebinding" in str(fix.payload)


# ---------------------------------------------------------------------------
# 10. PDBTooStrict
# ---------------------------------------------------------------------------

class TestPDBTooStrict:
    def test_applies_to(self):
        f = _finding(resource_kind="PodDisruptionBudget", raw={"disruptions_allowed": 0})
        assert PDBTooStrict().applies_to(f)

    def test_does_not_apply_has_budget(self):
        f = _finding(resource_kind="PodDisruptionBudget", raw={"disruptions_allowed": 1})
        assert not PDBTooStrict().applies_to(f)

    def test_generate_fix(self):
        f = _finding(
            resource_kind="PodDisruptionBudget",
            resource_name="api-pdb",
            raw={"disruptions_allowed": 0, "matched_pods": 3},
        )
        fix = PDBTooStrict().generate_fix(f, {})
        assert fix.payload["spec"]["minAvailable"] == 2  # type: ignore[index]
        assert fix.requires_review

    def test_generate_fix_single_replica_raises(self):
        f = _finding(
            resource_kind="PodDisruptionBudget",
            resource_name="lonely-pdb",
            raw={"disruptions_allowed": 0, "matched_pods": 1},
        )
        with pytest.raises(ValueError, match="Scale up"):
            PDBTooStrict().generate_fix(f, {})


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_dispatch_image_tag(self):
        f = _finding(
            behavior="image_tag_migration_remediation",
            raw={"reason": "ImagePullBackOff", "current_image": "bitnami/kubectl:1.29"},
        )
        result = dispatch(f, {})
        assert result is not None
        assert "registry.k8s.io" in str(result.payload)

    def test_dispatch_orphan_job(self):
        f = _finding(behavior="orphan_job_remediation", resource_kind="Job")
        result = dispatch(f, {})
        assert result is not None
        assert result.patch_type == "kubectl-cmd"

    def test_dispatch_no_match_returns_none(self):
        f = _finding(behavior="unknown_behavior", raw={})
        result = dispatch(f, {})
        assert result is None

    def test_registry_has_ten_handlers(self):
        assert len(REGISTRY) == 10

    def test_dispatch_pvc_resize(self):
        f = _finding(
            resource_kind="PersistentVolumeClaim",
            resource_name="logs-pvc",
            raw={"storage_class_allow_expansion": True, "usage_percent": 92, "capacity_gi": 20},
        )
        result = dispatch(f, {})
        assert result is not None
        assert "30Gi" in str(result.payload)  # 20 * 1.5
