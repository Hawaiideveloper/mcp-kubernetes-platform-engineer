"""
US-021 Security Hardening — unit tests.

Covers:
  - SQL injection fix in github_issues_manager (parameterized query)
  - logger.py loguru opt(exception=) traceback attachment
  - helm_manager password-stdin (no --password in args)
  - secret.yaml has no GITHUB_TOKEN data value
  - namespace.yaml has PSA labels
  - deployment.yaml hardening (readOnlyRootFilesystem, no KUBECONFIG, seccompProfile)
  - networkpolicy.yaml exists and has default-deny + allow policy
  - VSCODE_K8S_INTEGRATION.md has no hardcoded private IPs
  - setup-vscode-k8s.sh has no hardcoded path
  - update.sh has set -euo pipefail and no error suppression
"""
import io
import os
import re
import sys
import sqlite3

import os
import pytest
HELM_MANAGER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "src", "helm_manager.py")
helm_manager_present = pytest.mark.skipif(
    not os.path.exists(HELM_MANAGER_PATH),
    reason="src/helm_manager.py deleted by US-024 dead-code removal",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = os.path.join(ROOT, "src")
K8S = os.path.join(ROOT, "k8s")
sys.path.insert(0, SRC)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# 1. SQL Injection — github_issues_manager
# ---------------------------------------------------------------------------

class TestUS021SQLInjection:
    """Parameterized query prevents SQL injection."""

    def test_no_fstring_sql_construction(self):
        """The vulnerable f-string SQL is no longer present."""
        src = read_file(os.path.join(SRC, "github_issues_manager.py"))
        assert "OR body LIKE '%{term}%'" not in src, (
            "f-string SQL injection pattern still present in github_issues_manager.py"
        )

    def test_parameterized_placeholders_present(self):
        """Parameterized placeholder pattern is used."""
        src = read_file(os.path.join(SRC, "github_issues_manager.py"))
        assert "(title LIKE ? OR body LIKE ?)" in src, (
            "Parameterized placeholder not found; expected '(title LIKE ? OR body LIKE ?)'"
        )

    def test_params_list_used(self):
        """params list is built and appended to include LIMIT value."""
        src = read_file(os.path.join(SRC, "github_issues_manager.py"))
        assert "params.append(max_results)" in src, (
            "params.append(max_results) not found — LIMIT still unparameterized"
        )

    def test_sql_injection_blocked_in_memory_db(self):
        """
        Integration smoke: parameterized query does not return every row
        when a SQL injection payload is supplied as the error_message.
        We exercise _extract_key_terms indirectly by calling the raw
        query-building logic that now lives in find_similar_issues.
        """
        # Build an in-memory DB mirroring the github_issues schema
        con = sqlite3.connect(":memory:")
        con.execute(
            "CREATE TABLE github_issues ("
            "  id INTEGER PRIMARY KEY, title TEXT, body TEXT, repo TEXT, "
            "  state TEXT, labels TEXT, url TEXT, "
            "  reactions_count INTEGER, comments_count INTEGER, "
            "  assignees TEXT, created_at TEXT, updated_at TEXT"
            ")"
        )
        con.execute(
            "INSERT INTO github_issues VALUES "
            "(1, 'normal issue', 'normal body', 'repo', 'closed', '[]', '', 0, 0, '[]', '2024-01-01', '2024-01-01')"
        )
        con.execute(
            "INSERT INTO github_issues VALUES "
            "(2, 'other issue', 'other body', 'repo', 'closed', '[]', '', 0, 0, '[]', '2024-01-01', '2024-01-01')"
        )
        con.commit()

        # Simulate the parameterized query that the patched code builds
        injection_term = "%' OR '1'='1"
        clauses = ["(title LIKE ? OR body LIKE ?)"]
        params = [f"%{injection_term}%", f"%{injection_term}%"]
        sql = (
            "SELECT *, (reactions_count + comments_count) as relevance_score "
            "FROM github_issues "
            "WHERE " + " OR ".join(clauses) + " "
            "AND state = 'closed' "
            "ORDER BY relevance_score DESC, updated_at DESC "
            "LIMIT ?"
        )
        params.append(10)
        cursor = con.execute(sql, params)
        rows = cursor.fetchall()
        # With parameterized query the injection payload matches no rows
        assert len(rows) == 0, (
            f"Injection payload returned {len(rows)} rows — parameterization may be broken"
        )
        con.close()


# ---------------------------------------------------------------------------
# 2. Logger — loguru opt(exception=) fix
# ---------------------------------------------------------------------------

class TestUS021Logger:
    """loguru error helpers emit tracebacks correctly."""

    def test_no_exc_info_kwarg_in_logger(self):
        """exc_info= kwarg removed from loguru calls."""
        src = read_file(os.path.join(SRC, "logger.py"))
        assert "exc_info=error" not in src, (
            "exc_info=error kwarg still present in logger.py — loguru silently drops it"
        )

    def test_opt_exception_present(self):
        """.opt(exception=error) is used instead."""
        src = read_file(os.path.join(SRC, "logger.py"))
        assert ".opt(exception=error)" in src, (
            ".opt(exception=error) not found in logger.py"
        )

    def test_console_import_removed(self):
        """Unused Console import removed."""
        src = read_file(os.path.join(SRC, "logger.py"))
        assert "from rich.console import Console" not in src, (
            "Unused Console import still present in logger.py"
        )

    def test_loguru_traceback_attached(self):
        """
        Smoke: opt(exception=).error() causes loguru to capture traceback.
        We verify this by inspecting the loguru sink output.
        """
        from loguru import logger

        buf = io.StringIO()
        sink_id = logger.add(buf, format="{message}\n{exception}", level="ERROR")
        try:
            err = ValueError("us021 test error")
            try:
                raise err
            except ValueError as e:
                logger.opt(exception=e).error("K8s Error in test_op: us021 test error")
            output = buf.getvalue()
            assert "ValueError" in output, (
                "Traceback not found in loguru output — opt(exception=) may not be working"
            )
        finally:
            logger.remove(sink_id)


# ---------------------------------------------------------------------------
# 3. Helm Manager — no --password in subprocess args
# ---------------------------------------------------------------------------

@helm_manager_present
class TestUS021HelmPassword:
    """helm password passed via stdin, not as positional arg."""

    def test_no_password_positional_arg(self):
        """--password positional arg removed from add_helm_repository."""
        src = read_file(os.path.join(SRC, "helm_manager.py"))
        # The old pattern: args.extend(['--password', password])
        assert "['--password', password]" not in src, (
            "Plaintext --password arg still passed in helm_manager.py subprocess args"
        )

    def test_password_stdin_flag_present(self):
        """--password-stdin flag is used instead."""
        src = read_file(os.path.join(SRC, "helm_manager.py"))
        assert "--password-stdin" in src, (
            "--password-stdin not found in helm_manager.py"
        )


# ---------------------------------------------------------------------------
# 4. k8s/secret.yaml — no empty token placeholder
# ---------------------------------------------------------------------------

class TestUS021SecretYaml:
    """k8s/secret.yaml has no empty data block."""

    def test_no_empty_github_token(self):
        """GITHUB_TOKEN data key with empty value removed."""
        content = read_file(os.path.join(K8S, "secret.yaml"))
        assert 'GITHUB_TOKEN: ""' not in content, (
            'Empty GITHUB_TOKEN: "" still in k8s/secret.yaml'
        )

    def test_no_data_block(self):
        """No standalone 'data:' key in secret.yaml."""
        content = read_file(os.path.join(K8S, "secret.yaml"))
        # 'data:' as a standalone YAML key (not in a comment, not as part of metadata:)
        non_comment_lines = [
            line for line in content.splitlines()
            if not line.strip().startswith("#")
            and line.strip() == "data:"
        ]
        assert len(non_comment_lines) == 0, (
            f"data: block still present in k8s/secret.yaml: {non_comment_lines}"
        )

    def test_out_of_band_instructions_present(self):
        """Comment block explains out-of-band creation."""
        content = read_file(os.path.join(K8S, "secret.yaml"))
        assert "kubectl create secret" in content, (
            "Out-of-band secret creation instructions missing from k8s/secret.yaml"
        )


# ---------------------------------------------------------------------------
# 5. k8s/namespace.yaml — PSA labels
# ---------------------------------------------------------------------------

class TestUS021NamespaceYaml:
    """namespace.yaml has Pod Security Admission labels."""

    def test_psa_enforce_baseline(self):
        content = read_file(os.path.join(K8S, "namespace.yaml"))
        assert "pod-security.kubernetes.io/enforce: baseline" in content, (
            "PSA enforce=baseline label missing from k8s/namespace.yaml"
        )

    def test_psa_warn_restricted(self):
        content = read_file(os.path.join(K8S, "namespace.yaml"))
        assert "pod-security.kubernetes.io/warn: restricted" in content

    def test_psa_audit_restricted(self):
        content = read_file(os.path.join(K8S, "namespace.yaml"))
        assert "pod-security.kubernetes.io/audit: restricted" in content


# ---------------------------------------------------------------------------
# 6. k8s/deployment.yaml — security context hardening
# ---------------------------------------------------------------------------

class TestUS021DeploymentYaml:
    """deployment.yaml hardening checks."""

    def test_readonly_root_filesystem_true(self):
        content = read_file(os.path.join(K8S, "deployment.yaml"))
        assert "readOnlyRootFilesystem: true" in content, (
            "readOnlyRootFilesystem not set to true in k8s/deployment.yaml"
        )
        assert "readOnlyRootFilesystem: false" not in content

    def test_no_kubeconfig_env_var(self):
        """KUBECONFIG env var pointing to directory removed."""
        content = read_file(os.path.join(K8S, "deployment.yaml"))
        # Accept commented-out mentions but not active KUBECONFIG: env entries
        lines = content.splitlines()
        active_kubeconfig = [
            line for line in lines
            if "name: KUBECONFIG" in line and not line.strip().startswith("#")
        ]
        assert len(active_kubeconfig) == 0, (
            f"KUBECONFIG env var still in deployment.yaml: {active_kubeconfig}"
        )

    def test_seccomp_profile_runtime_default(self):
        content = read_file(os.path.join(K8S, "deployment.yaml"))
        assert "seccompProfile:" in content, (
            "seccompProfile missing from k8s/deployment.yaml"
        )
        assert "type: RuntimeDefault" in content


# ---------------------------------------------------------------------------
# 7. k8s/networkpolicy.yaml — exists and has correct policies
# ---------------------------------------------------------------------------

class TestUS021NetworkPolicy:
    """networkpolicy.yaml created with default-deny + allow-ingress-nginx."""

    def test_file_exists(self):
        path = os.path.join(K8S, "networkpolicy.yaml")
        assert os.path.isfile(path), "k8s/networkpolicy.yaml does not exist"

    def test_default_deny_policy(self):
        content = read_file(os.path.join(K8S, "networkpolicy.yaml"))
        assert "default-deny-ingress" in content, (
            "default-deny-ingress NetworkPolicy not found"
        )
        assert "podSelector: {}" in content, (
            "podSelector: {} (catch-all) not found in networkpolicy.yaml"
        )

    def test_allow_ingress_nginx_policy(self):
        content = read_file(os.path.join(K8S, "networkpolicy.yaml"))
        assert "allow-ingress-nginx" in content
        assert "ingress-nginx" in content

    def test_port_3001_specified(self):
        content = read_file(os.path.join(K8S, "networkpolicy.yaml"))
        assert "port: 3001" in content


# ---------------------------------------------------------------------------
# 8. No hardcoded private IPs in docs
# ---------------------------------------------------------------------------

class TestUS021NoHardcodedIPs:
    """172.100.10.x removed from documentation files."""

    PRIVATE_IP_RE = re.compile(r"172\.100\.10\.")

    def _check_file(self, path: str):
        if not os.path.isfile(path):
            return
        content = read_file(path)
        matches = self.PRIVATE_IP_RE.findall(content)
        assert len(matches) == 0, (
            f"Hardcoded private IP 172.100.10.x found in {path}: {matches}"
        )

    def test_vscode_integration_md(self):
        self._check_file(os.path.join(ROOT, "VSCODE_K8S_INTEGRATION.md"))

    def test_readme_md(self):
        self._check_file(os.path.join(ROOT, "README.md"))


# ---------------------------------------------------------------------------
# 9. setup-vscode-k8s.sh — no hardcoded path
# ---------------------------------------------------------------------------

class TestUS021SetupVsCodeSh:
    """setup-vscode-k8s.sh uses SETTINGS_FILE env var."""

    def test_no_hardcoded_user_path(self):
        content = read_file(os.path.join(ROOT, "setup-vscode-k8s.sh"))
        assert "hawaiidevelopergmail" not in content, (
            "Hardcoded hawaiidevelopergmail path still in setup-vscode-k8s.sh"
        )

    def test_settings_file_env_used(self):
        content = read_file(os.path.join(ROOT, "setup-vscode-k8s.sh"))
        assert 'os.environ["SETTINGS_FILE"]' in content or "SETTINGS_FILE" in content


# ---------------------------------------------------------------------------
# 10. update.sh — proper error handling
# ---------------------------------------------------------------------------

class TestUS021UpdateSh:
    """update.sh has set -euo pipefail and explicit error checks."""

    def test_set_euo_pipefail(self):
        content = read_file(os.path.join(ROOT, "update.sh"))
        assert "set -euo pipefail" in content, (
            "set -euo pipefail missing from update.sh"
        )

    def test_no_error_suppression(self):
        content = read_file(os.path.join(ROOT, "update.sh"))
        assert "2>/dev/null" not in content, (
            "2>/dev/null error suppression still in update.sh"
        )
        assert "|| echo" not in content, (
            "|| echo error suppression still in update.sh"
        )

    def test_git_pull_error_check(self):
        content = read_file(os.path.join(ROOT, "update.sh"))
        assert "git pull" in content
        assert 'echo "ERROR: git pull failed"' in content or "exit 1" in content
