"""
Tests for US-020: CI/CD on albright-runners + image pinning.

Validates that:
- Workflow files exist and are valid YAML
- No workflow uses ubuntu-latest (all must use albright-runners)
- deployment.yaml uses digest-pinned image reference
- deployment.yaml uses IfNotPresent pull policy, not Always
- Pre-commit config exists and references ruff and mypy hooks
- Dependabot config exists and covers pip + github-actions ecosystems
"""

import os
import yaml
# import pytest  # noqa: F401


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKFLOWS_DIR = os.path.join(REPO_ROOT, ".github", "workflows")
DEPLOYMENT_YAML = os.path.join(REPO_ROOT, "k8s", "deployment.yaml")
PRE_COMMIT_CONFIG = os.path.join(REPO_ROOT, ".pre-commit-config.yaml")
DEPENDABOT_CONFIG = os.path.join(REPO_ROOT, ".github", "dependabot.yml")


# ─── Workflow file existence ──────────────────────────────────────────────────

def test_US_020_ci_workflow_exists():
    path = os.path.join(WORKFLOWS_DIR, "ci.yml")
    assert os.path.isfile(path), f"Missing CI workflow: {path}"


def test_US_020_release_workflow_exists():
    path = os.path.join(WORKFLOWS_DIR, "release.yml")
    assert os.path.isfile(path), f"Missing release workflow: {path}"


# ─── Workflow YAML validity ───────────────────────────────────────────────────

def _load_yaml(path: str) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def test_US_020_ci_workflow_valid_yaml():
    path = os.path.join(WORKFLOWS_DIR, "ci.yml")
    data = _load_yaml(path)
    assert isinstance(data, dict), "ci.yml must parse to a dict"


def test_US_020_release_workflow_valid_yaml():
    path = os.path.join(WORKFLOWS_DIR, "release.yml")
    data = _load_yaml(path)
    assert isinstance(data, dict), "release.yml must parse to a dict"


# ─── No ubuntu-latest ────────────────────────────────────────────────────────

def _collect_runs_on(workflow_data: dict) -> list[str]:
    """Collect all runs-on values from a workflow dict."""
    runs_on_list = []
    jobs = workflow_data.get("jobs", {})
    for job_name, job_def in jobs.items():
        runs_on = job_def.get("runs-on", "")
        if isinstance(runs_on, str):
            runs_on_list.append(runs_on)
        elif isinstance(runs_on, list):
            runs_on_list.extend(runs_on)
    return runs_on_list


def test_US_020_ci_no_ubuntu_latest():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    for runner in _collect_runs_on(data):
        assert "ubuntu-latest" not in runner, (
            f"ci.yml must not use ubuntu-latest; found: {runner}"
        )


def test_US_020_release_no_ubuntu_latest():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "release.yml"))
    for runner in _collect_runs_on(data):
        assert "ubuntu-latest" not in runner, (
            f"release.yml must not use ubuntu-latest; found: {runner}"
        )


def test_US_020_ci_uses_albright_runners():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    runners = _collect_runs_on(data)
    assert any("albright-runners" in r for r in runners), (
        "ci.yml must have at least one job on albright-runners"
    )


def test_US_020_release_uses_albright_runners():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "release.yml"))
    runners = _collect_runs_on(data)
    assert any("albright-runners" in r for r in runners), (
        "release.yml must have at least one job on albright-runners"
    )


# ─── CI workflow structure ────────────────────────────────────────────────────

def test_US_020_ci_has_required_jobs():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    jobs = set(data.get("jobs", {}).keys())
    required = {"lint", "type-check", "test", "build-and-scan", "push-main"}
    assert required.issubset(jobs), (
        f"ci.yml missing jobs: {required - jobs}"
    )


def test_US_020_ci_triggers_on_push_and_pr():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    # YAML 1.1: "on" parses as True
    triggers = set((data.get(True) or data.get("on") or {}).keys())
    assert "push" in triggers, "ci.yml must trigger on push"
    assert "pull_request" in triggers, "ci.yml must trigger on pull_request"


def test_US_020_ci_has_trivy_scan_step():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    jobs = data.get("jobs", {})
    build_scan_steps = jobs.get("build-and-scan", {}).get("steps", [])
    step_names = [s.get("name", "") for s in build_scan_steps]
    assert any("trivy" in name.lower() for name in step_names), (
        "build-and-scan job must have a Trivy scan step"
    )


def test_US_020_ci_coverage_gate_present():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "ci.yml"))
    jobs = data.get("jobs", {})
    test_steps = jobs.get("test", {}).get("steps", [])
    step_runs = " ".join(
        s.get("run", "") for s in test_steps if "run" in s
    )
    assert "--cov-fail-under=80" in step_runs, (
        "test job must enforce coverage gate with --cov-fail-under=80"
    )


# ─── Release workflow structure ───────────────────────────────────────────────

def test_US_020_release_triggers_on_semver_tag():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "release.yml"))
    # YAML 1.1: on parses as True boolean
    on_section = data.get(True) or data.get('on') or {}
    tags = on_section.get('push', {}).get('tags', [])
    assert any("v" in t for t in tags), (
        "release.yml must trigger on semver tags (v*.*.*)"
    )


def test_US_020_release_pins_digest_in_deployment():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "release.yml"))
    jobs = data.get("jobs", {})
    steps = jobs.get("release-image", {}).get("steps", [])
    all_run = " ".join(s.get("run", "") for s in steps if "run" in s)
    assert "deployment.yaml" in all_run, (
        "release.yml must update k8s/deployment.yaml with the pinned digest"
    )
    assert "DIGEST" in all_run or "digest" in all_run.lower(), (
        "release.yml must reference digest when pinning"
    )


def test_US_020_release_uses_albright_bot_identity():
    data = _load_yaml(os.path.join(WORKFLOWS_DIR, "release.yml"))
    jobs = data.get("jobs", {})
    steps = jobs.get("release-image", {}).get("steps", [])
    all_run = " ".join(s.get("run", "") for s in steps if "run" in s)
    assert "albright-bot" in all_run, (
        "release.yml must set git user.name to albright-bot before committing"
    )


# ─── deployment.yaml image pinning ───────────────────────────────────────────

def _load_deployment() -> dict:
    with open(DEPLOYMENT_YAML) as fh:
        return yaml.safe_load(fh)


def test_US_020_deployment_no_latest_tag():
    data = _load_deployment()
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    for c in containers:
        image = c.get("image", "")
        assert ":latest" not in image, (
            f"deployment.yaml must not use :latest; found: {image}"
        )


def test_US_020_deployment_pull_policy_not_always():
    data = _load_deployment()
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    for c in containers:
        policy = c.get("imagePullPolicy", "")
        assert policy != "Always", (
            "deployment.yaml imagePullPolicy must not be Always"
        )


def test_US_020_deployment_pull_policy_is_if_not_present():
    data = _load_deployment()
    containers = (
        data.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    assert containers, "deployment.yaml must have at least one container"
    for c in containers:
        assert c.get("imagePullPolicy") == "IfNotPresent", (
            f"Expected IfNotPresent, got: {c.get('imagePullPolicy')}"
        )


# ─── Pre-commit config ────────────────────────────────────────────────────────

def test_US_020_pre_commit_config_exists():
    assert os.path.isfile(PRE_COMMIT_CONFIG), (
        f"Missing .pre-commit-config.yaml at {PRE_COMMIT_CONFIG}"
    )


def test_US_020_pre_commit_config_valid_yaml():
    data = _load_yaml(PRE_COMMIT_CONFIG)
    assert isinstance(data, dict), ".pre-commit-config.yaml must parse to a dict"


def test_US_020_pre_commit_has_ruff():
    data = _load_yaml(PRE_COMMIT_CONFIG)
    repos = data.get("repos", [])
    hook_ids = [
        hook.get("id", "")
        for repo in repos
        for hook in repo.get("hooks", [])
    ]
    assert "ruff" in hook_ids, ".pre-commit-config.yaml must include ruff hook"


def test_US_020_pre_commit_has_mypy():
    data = _load_yaml(PRE_COMMIT_CONFIG)
    repos = data.get("repos", [])
    hook_ids = [
        hook.get("id", "")
        for repo in repos
        for hook in repo.get("hooks", [])
    ]
    assert "mypy" in hook_ids, ".pre-commit-config.yaml must include mypy hook"


# ─── Dependabot config ────────────────────────────────────────────────────────

def test_US_020_dependabot_exists():
    assert os.path.isfile(DEPENDABOT_CONFIG), (
        f"Missing .github/dependabot.yml at {DEPENDABOT_CONFIG}"
    )


def test_US_020_dependabot_valid_yaml():
    data = _load_yaml(DEPENDABOT_CONFIG)
    assert isinstance(data, dict), "dependabot.yml must parse to a dict"


def test_US_020_dependabot_covers_pip():
    data = _load_yaml(DEPENDABOT_CONFIG)
    ecosystems = [u.get("package-ecosystem", "") for u in data.get("updates", [])]
    assert "pip" in ecosystems, "dependabot.yml must have pip ecosystem"


def test_US_020_dependabot_covers_github_actions():
    data = _load_yaml(DEPENDABOT_CONFIG)
    ecosystems = [u.get("package-ecosystem", "") for u in data.get("updates", [])]
    assert "github-actions" in ecosystems, (
        "dependabot.yml must have github-actions ecosystem"
    )


def test_US_020_dependabot_weekly_schedule():
    data = _load_yaml(DEPENDABOT_CONFIG)
    intervals = [
        u.get("schedule", {}).get("interval", "")
        for u in data.get("updates", [])
    ]
    assert all(i == "weekly" for i in intervals if i), (
        "dependabot.yml must use weekly schedule for all ecosystems"
    )


# ─── No secrets in workflow files ────────────────────────────────────────────

def test_US_020_no_hardcoded_secrets_in_ci():
    path = os.path.join(WORKFLOWS_DIR, "ci.yml")
    with open(path) as fh:
        content = fh.read()
    import re
    pattern = r'(token|secret|password|api_key)\s*[:=]\s*["\047][A-Za-z0-9]{6,}'
    matches = re.findall(pattern, content, re.IGNORECASE)
    assert not matches, f"ci.yml contains hardcoded secrets: {matches}"


def test_US_020_no_hardcoded_secrets_in_release():
    path = os.path.join(WORKFLOWS_DIR, "release.yml")
    with open(path) as fh:
        content = fh.read()
    import re
    pattern = r'(token|secret|password|api_key)\s*[:=]\s*["\047][A-Za-z0-9]{6,}'
    matches = re.findall(pattern, content, re.IGNORECASE)
    assert not matches, f"release.yml contains hardcoded secrets: {matches}"
