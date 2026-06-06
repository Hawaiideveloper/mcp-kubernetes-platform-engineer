"""
US-024: Dead-code removal tests.

Validates that the deleted files are gone, mcp_server.py imports cleanly,
and GITHUB_ISSUES_DB_PATH env-var override works.
"""
import os
import sys
import pytest

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def _src(path: str) -> str:
    return os.path.join(SRC_DIR, path)


# ---------------------------------------------------------------------------
# 1. Deleted-file assertions
# ---------------------------------------------------------------------------

def test_bak_file_deleted():
    assert not os.path.exists(_src("mcp_server.py.bak"))


def test_backup_py_deleted():
    assert not os.path.exists(_src("mcp_server_backup.py"))


def test_enhanced_tools_deleted():
    assert not os.path.exists(_src("enhanced_tools.py"))


def test_kubectl_manager_deleted():
    assert not os.path.exists(_src("kubectl_manager.py"))


def test_helm_manager_deleted():
    assert not os.path.exists(_src("helm_manager.py"))


def test_getting_started_duplicate_deleted():
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    assert not os.path.exists(os.path.join(repo_root, "GettingStarted.md"))


# ---------------------------------------------------------------------------
# 2. mcp_server.py has no dead imports
# ---------------------------------------------------------------------------

def test_mcp_server_no_dead_imports():
    with open(_src("mcp_server.py")) as f:
        source = f.read()
    assert "kubectl_manager" not in source
    assert "helm_manager" not in source
    assert "enhanced_tools" not in source


# ---------------------------------------------------------------------------
# 3. GITHUB_ISSUES_DB_PATH env-var support present in source
# ---------------------------------------------------------------------------

def test_github_issues_manager_env_var_support():
    with open(_src("github_issues_manager.py")) as f:
        source = f.read()
    assert "GITHUB_ISSUES_DB_PATH" in source


def test_github_issues_manager_uses_env_path(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("GITHUB_ISSUES_DB_PATH", db_path)
    monkeypatch.syspath_prepend(SRC_DIR)
    if "github_issues_manager" in sys.modules:
        del sys.modules["github_issues_manager"]
    from github_issues_manager import GitHubIssuesManager  # type: ignore

    class FakeCfg:
        github_token = None
        github_repo = None

    mgr = GitHubIssuesManager(FakeCfg())
    assert mgr.db_path == db_path


# ---------------------------------------------------------------------------
# 4. Dockerfile does not copy docs/
# ---------------------------------------------------------------------------

def test_dockerfile_no_copy_docs():
    repo_root = os.path.join(os.path.dirname(__file__), "..", "..")
    dockerfile = os.path.join(repo_root, "Dockerfile")
    if not os.path.exists(dockerfile):
        pytest.skip("Dockerfile not found")
    with open(dockerfile) as f:
        content = f.read()
    assert "COPY docs/" not in content
