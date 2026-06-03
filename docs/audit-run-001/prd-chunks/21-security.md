# PRD Section 21 — Security Hardening

## Overview

Multiple audit agents independently flagged the same concrete security defects across the source code,
shell scripts, and Kubernetes manifests. This section catalogs each issue with file-and-line evidence,
the required patch, and a test that proves the fix is in place. General pod-level hardening is addressed
at the end.

---

## 1. SQL Injection in `github_issues_manager.py`

### Evidence

`src/github_issues_manager.py:488` — multiple agents quote the exact line:

```
search_terms = " OR ".join([f"title LIKE '%{term}%' OR body LIKE '%{term}%'" for term in key_terms])
sql = f"""SELECT ... WHERE ({search_terms})"""
```

`key_terms` comes from the user-supplied `error_message` argument via `_extract_key_terms()` (line 518).
The constructed string is passed directly to `db.execute(sql, (max_results,))` where only the
`LIMIT` clause is parameterized, not the WHERE terms (findings at lines 1446, 1856, 2486, 3186, 3427,
4037 of all-findings.json).

### Patch

Replace the f-string SQL construction with parameterized placeholders:

```python
clauses = ["(title LIKE ? OR body LIKE ?)"] * len(key_terms)
params = [v for t in key_terms for v in (f"%{t}%", f"%{t}%")]
sql = (
    f"SELECT id, title, body, repo, state, labels, url "
    f"FROM github_issues "
    f"WHERE {' OR '.join(clauses)} AND state = 'closed' "
    f"ORDER BY created_at DESC LIMIT ?"
)
params.append(max_results)
async with db.execute(sql, params) as cursor:
    ...
```

Ban raw f-string SQL in CI: add a `ruff` or `flake8-bandit` rule (`S608 — possible SQL injection`)
to the lint step and fail the pipeline on any hit.

### Test

Seed an in-memory SQLite DB with one row whose title is `"normal issue"`. Call
`find_similar_issues(error_message="%' OR '1'='1", max_results=10)`. Assert the result contains
only rows that legitimately match, not every row in the table. Add `bandit -t B608` to the CI
lint step and require zero SQL injection warnings.

---

## 2. Token in `start.sh` Process Arguments

### Evidence

`start.sh:98` (quoted by findings at lines 3086, 3444 of all-findings.json):

```bash
ENV_ARGS="$ENV_ARGS -e GITHUB_TOKEN=$GITHUB_TOKEN"
```

The token is interpolated into the `docker run` argument list. Any process on the host can read it
via `ps aux` or `docker inspect` while the container is starting. Additionally `start.sh:2` uses only
`set -e`, omitting `set -u` and `set -o pipefail`, so an unset `GITHUB_TOKEN` silently expands to an
empty string and is passed without error.

### Patch

1. Change line 2 to `set -euo pipefail`.
2. Write the token to a short-lived temp file and use `--env-file`:

```bash
TMPENV=$(mktemp)
trap 'rm -f "$TMPENV"' EXIT
printf 'GITHUB_TOKEN=%s\n' "$GITHUB_TOKEN" > "$TMPENV"
chmod 600 "$TMPENV"
# Replace -e GITHUB_TOKEN=$GITHUB_TOKEN with:
docker run ... --env-file "$TMPENV" ...
```

3. Alternatively, if the token is already in a `.env` file, pass `--env-file .env` directly and
   remove the shell interpolation entirely.

### Test

After running `start.sh` with `GITHUB_TOKEN=secret`, assert `ps aux | grep -v grep | grep GITHUB_TOKEN`
returns no output. Assert `docker inspect k8s-mcp-server --format '{{json .Args}}'` does not contain
the literal token string. Run `shellcheck start.sh` and assert zero SC2086 (unquoted variable) warnings.

---

## 3. Empty Placeholder `k8s/secret.yaml` Committed to Source Control

### Evidence

`k8s/secret.yaml:13` (findings at lines 1996, 2306, 2796, 3657 of all-findings.json):

```yaml
  GITHUB_TOKEN: ""
```

An empty `data` value in a Kubernetes Secret is valid YAML and passes `kubectl apply` without error.
Any cluster running `kubectl apply -f k8s/` will create a Secret with a blank token, causing all
GitHub API calls to run unauthenticated (60 req/hr rate limit).

### Patch

Remove the `data` block and the inline value entirely. Replace the manifest with a comment block
explaining the out-of-band creation pattern:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kubernetes-mcp-server-secrets
  namespace: mcp-kubernetes
  labels:
    app.kubernetes.io/name: kubernetes-platform-engineer
    app.kubernetes.io/component: mcp-server
type: Opaque
# DO NOT add secret values here. Create the secret out-of-band:
#
#   kubectl create secret generic kubernetes-mcp-server-secrets \
#     --from-literal=GITHUB_TOKEN="$(cat ~/.github_token)" \
#     -n mcp-kubernetes
#
# Or use SealedSecrets:
#   kubeseal --format yaml < plain-secret.yaml > k8s/sealed-secret.yaml
#
# Or use external-secrets-operator with a SecretStore CR pointing to
# AWS Secrets Manager, Vault, or GCP Secret Manager.
```

Add a CI gate in the lint/validate job:

```bash
if grep -q 'GITHUB_TOKEN: ""' k8s/secret.yaml; then
  echo "ERROR: empty GITHUB_TOKEN placeholder in k8s/secret.yaml — remove the data block"
  exit 1
fi
```

### Test

`kubectl apply -f k8s/secret.yaml --dry-run=client` must succeed. After apply, assert
`kubectl get secret kubernetes-mcp-server-secrets -n mcp-kubernetes -o jsonpath='{.data.GITHUB_TOKEN}'`
returns empty. The CI gate must exit non-zero when `GITHUB_TOKEN: ""` is present.

---

## 4. Hardcoded Private Lab IP `172.100.10.107` in Public Documentation

### Evidence

`VSCODE_K8S_INTEGRATION.md:55`, `:121`, `:166`, `:255` (finding at line 2656 of all-findings.json):

```
curl http://172.100.10.107:30001/health
```

The same IP appears four times in the VS Code integration guide. It also appears in
`diagnostics_manager.py` stub data (finding at line 4000: `'pod_cidr': '172.100.10.0/24'`), and
`README.md:113-133` (finding at line 56: `172.100.10.107:30001`).

### Patch

Replace every occurrence in documentation and stub data with a generic placeholder:

```
http://<NODE_IP>:<NODE_PORT>
```

Where `NODE_IP` and `NODE_PORT` are obtained at runtime:

```bash
export NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
export NODE_PORT=$(kubectl get svc kubernetes-mcp-server-nodeport -n mcp-kubernetes \
  -o jsonpath='{.spec.ports[0].nodePort}')
curl http://${NODE_IP}:${NODE_PORT}/health
```

For diagnostics_manager stub data, replace the hardcoded CIDR `172.100.10.0/24` with
`<cluster-pod-cidr>` or remove the stub entirely when real API calls are implemented.

Add to CI:

```bash
grep -rn '172\.100\.10\.' docs/ README.md VSCODE_K8S_INTEGRATION.md && {
  echo "ERROR: hardcoded private IP found in docs"
  exit 1
}
```

### Test

`grep -r '172\.100\.10\.' docs/ README.md VSCODE_K8S_INTEGRATION.md` must return no matches.
Add this grep as a CI lint step that exits non-zero on any hit.

---

## 5. NodePort Service Without NetworkPolicy

### Evidence

`k8s/service.yaml:37-47` (findings at lines 1336, 1846, 2576 of all-findings.json):

```yaml
spec:
  type: NodePort
  ports:
  - name: http
    port: 3001
    targetPort: http
    nodePort: 30001
```

No NetworkPolicy exists in `k8s/` that restricts ingress to this port. The MCP server has
cluster-scoped read access via its ServiceAccount; unrestricted access to port 30001 from any
host on the node network is unacceptable.

### Patch

Create `k8s/networkpolicy.yaml` with two resources:

1. A default-deny policy (`podSelector: {}`, `policyTypes: [Ingress]`) that blocks all ingress
   to the `mcp-kubernetes` namespace by default.
2. A targeted allow policy scoped to `app.kubernetes.io/name: kubernetes-platform-engineer` pods,
   permitting ingress on TCP 3001 only from the `ingress-nginx` namespace (matched by
   `namespaceSelector: kubernetes.io/metadata.name: ingress-nginx`).

Optionally remove the NodePort service entirely and rely on ClusterIP plus `kubectl port-forward`
for developer access. If NodePort is retained, document the required host-level firewall rule
restricting access to trusted CIDRs on port 30001.

### Test

Deploy to a test cluster. Run a `curlimages/curl` pod in the `default` namespace (no matching
namespace label) targeting port 3001. Assert the connection times out or is refused. Run
`kube-score score k8s/networkpolicy.yaml` and assert no critical findings.

---

## 6. `setup-vscode-k8s.sh` Hardcodes Broken Path

### Evidence

`setup-vscode-k8s.sh:77` and `:89` (findings at lines 36, 276, 3877, 3967 of all-findings.json):

```python
with open("/Users/hawaiidevelopergmail.com/Library/Application Support/Code/User/settings.json", 'r')
```

The path has two bugs: the `@` is missing (should be `hawaiideveloper@gmail.com` is the email but
`hawaiideveloper` is the username), and the heredoc uses `<< 'EOF'` (single-quoted, line 72) which
prevents `$SETTINGS_FILE` from expanding. The variable is correctly computed at line 8-9 using
`$HOME` but is never used inside the Python block.

### Patch

1. Pass `SETTINGS_FILE` as an environment variable into the Python block. Change the invocation
   from `python3 << 'EOF'` to `SETTINGS_FILE="$SETTINGS_FILE" python3 - <<'PYEOF'` and inside
   the Python code use `settings_file = os.environ["SETTINGS_FILE"]` in both `open()` calls.
   Remove the two hardcoded literal paths entirely.
2. Add `set -euo pipefail` at line 3 if not already present.
3. Add a path-existence check before the Python block:
   `[[ -f "$SETTINGS_FILE" ]] || { echo "VS Code settings not found at $SETTINGS_FILE"; exit 1; }`

### Test

Set `HOME=/tmp/testuser`; create the settings file at the expected path; run `setup-vscode-k8s.sh`.
Assert writes go to `/tmp/testuser/Library/Application Support/Code/User/settings.json`.
Assert `grep -r 'hawaiidevelopergmail' /tmp/testuser/` returns no matches.
Run `shellcheck setup-vscode-k8s.sh` and assert zero warnings.

---

## 7. `update.sh` Silently Swallows Errors

### Evidence

`update.sh:1-6` — `set -e` only, no `set -u` or `set -o pipefail`. Git pull failure is masked
with `|| echo` (finding at line 1876 of all-findings.json). `./stop.sh` and `./start.sh` exit
codes are not checked; a failed restart still prints success (finding at line 2037).

### Patch

```bash
#!/usr/bin/env bash
set -euo pipefail

git pull origin main || { echo "ERROR: git pull failed"; exit 1; }

[[ -x ./stop.sh ]] || { echo "ERROR: stop.sh not found or not executable"; exit 1; }
./stop.sh

[[ -x ./start.sh ]] || { echo "ERROR: start.sh not found or not executable"; exit 1; }
./start.sh

echo "Update complete and server restarted."
```

Remove any `|| true` or `2>/dev/null` patterns that suppress error propagation.

### Test

Run `update.sh` from a non-git directory; assert it exits non-zero and prints an error message,
not "Update complete". Replace `start.sh` with a script that exits 1; assert `update.sh` also
exits non-zero. Run `shellcheck update.sh` and assert zero SC2069/SC2039 warnings.

---

## 8. `logger.py` Invalid Loguru API Signature Drops Stack Traces

### Evidence

`src/logger.py:173` and `:181` (finding at line 266 of all-findings.json):

```python
logger.bind(...).error(f'K8s Error...', exc_info=error)
```

Loguru's `.error()` method does not accept an `exc_info` keyword argument; that parameter belongs
to `logging.Logger`. Passing it to loguru silently discards the exception traceback.

### Patch

```python
# Before (line 173):
logger.bind(component="k8s", operation=operation).error(
    f"K8s Error [{error_type}]: {error_message}", exc_info=error
)

# After:
logger.bind(component="k8s", operation=operation).opt(exception=error).error(
    f"K8s Error [{error_type}]: {error_message}"
)
```

Apply the same change to `log_diagnostic_error` at line 181. Also:
- Remove the unused `console = Console()` at line 39 and the `from rich.console import Console`
  import (finding at lines 1773, 2016 of all-findings.json).
- Fix the return type annotation at line 112: `-> logger` should be `-> "loguru.Logger"`.

### Test

Add a loguru sink to a `StringIO` buffer. Call `log_k8s_error("test_op", ValueError("test error"))`.
Assert the buffer output contains `"Traceback"` and `"ValueError"`. This test fails before the fix
(`.error(exc_info=)` silently discards the traceback) and passes after (`.opt(exception=).error()`
attaches it). Run `mypy src/logger.py` and assert zero type errors after the return annotation fix.

---

## 9. General Pod Security Hardening

### 9.1 Pod Security Admission Baseline Label on Namespace

`k8s/namespace.yaml:1-9` carries no Pod Security Admission labels (finding at lines 2087, 2366
of all-findings.json). The namespace inherits the cluster-default permissive policy.

Required addition:

```yaml
metadata:
  name: mcp-kubernetes
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/warn: restricted
    pod-security.kubernetes.io/audit: restricted
    app.kubernetes.io/name: kubernetes-platform-engineer
```

Start with `baseline` for `enforce` and `restricted` for `warn`/`audit` to surface violations
before tightening to `restricted` enforcement.

### 9.2 Container Security Context Audit

`k8s/deployment.yaml` already sets (lines 31-33, 89-93):

```yaml
securityContext:           # pod-level
  runAsNonRoot: true
  runAsUser: 1001
  runAsGroup: 1001
  fsGroup: 1001
containers:
- securityContext:         # container-level
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: false   # <-- must be true
    capabilities:
      drop:
      - ALL
```

`runAsNonRoot: true` and `allowPrivilegeEscalation: false` are present. `capabilities.drop: [ALL]`
is present. **`readOnlyRootFilesystem: false` must be changed to `true`** (findings at lines 976,
1226, 3417, 4047 of all-findings.json). The app writes to `/app/data` (PVC-backed) and `/app/logs`
(emptyDir) which are already mounted; no writes to the root filesystem are required.

Required change to `k8s/deployment.yaml:90`:

```yaml
    readOnlyRootFilesystem: true
```

Add a seccomp profile at the pod level:

```yaml
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1001
    runAsGroup: 1001
    fsGroup: 1001
    seccompProfile:
      type: RuntimeDefault
```

### 9.3 Remove Invalid KUBECONFIG Environment Variable

`k8s/deployment.yaml:49-50` sets `KUBECONFIG` to the service account directory, not a file
(findings at lines 976, 1226, 3417, 4047 of all-findings.json):

```yaml
- name: KUBECONFIG
  value: "/var/run/secrets/kubernetes.io/serviceaccount"
```

This path is a directory. The Python `kubernetes` client auto-detects in-cluster credentials from
`KUBERNETES_SERVICE_HOST` and the projected service account token mount; `KUBECONFIG` is not needed
and setting it to a directory causes client initialization to fail. Remove these two lines entirely.

### 9.4 Capabilities Policy

`capabilities.drop: [ALL]` is already present in `deployment.yaml:92-93`. No capabilities should
be added back for the MCP server process. If a future capability is required (e.g., `NET_BIND_SERVICE`
for privileged ports), it must be documented in this PRD section with a justification comment in
the manifest before the capability is added.

### 9.5 `helm_manager.py` Password in Subprocess Args

`helm_manager.py:298-301` (finding at line 2516 of all-findings.json):

```python
args.extend(['--password', password])
```

Helm registry passwords passed as subprocess positional arguments are visible in `ps aux`. Pass
credentials via environment variable instead:

```python
env = {**os.environ, 'HELM_REGISTRY_PASSWORD': password}
args.extend(['--password-stdin'])
proc = subprocess.run(args, input=password.encode(), env=env, ...)
```

Or use `helm registry login` with `--password-stdin` and pipe the password via stdin:

```python
subprocess.run(
    ['helm', 'registry', 'login', registry, '--username', username, '--password-stdin'],
    input=password.encode(),
    check=True,
)
```

### Tests for Section 9

- **9.1**: `kubectl get namespace mcp-kubernetes -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}'` returns `baseline`.
- **9.2**: `kubectl get deployment kubernetes-mcp-server -n mcp-kubernetes -o jsonpath='{.spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem}'` returns `true`.
- **9.3**: No env entry named `KUBECONFIG` in the container spec; assert via jsonpath.
- **9.4**: `capabilities.drop[0]` is `ALL`; already present, assert no regression.
- **9.5**: `grep -n "'--password'" src/helm_manager.py | grep -v stdin` returns no matches.

---

## Summary of Required Changes

| # | File | Change |
|---|------|--------|
| 1 | `src/github_issues_manager.py:488` | Replace f-string SQL with parameterized placeholders |
| 2 | `start.sh:98` | Pass `GITHUB_TOKEN` via `--env-file` temp file, not inline arg |
| 3 | `k8s/secret.yaml:13` | Remove `data` block; document out-of-band creation |
| 4 | `VSCODE_K8S_INTEGRATION.md:55,121,166,255` | Replace `172.100.10.107` with `<NODE_IP>` |
| 5 | `k8s/networkpolicy.yaml` (new) | Default-deny + allow-from-ingress NetworkPolicy |
| 6 | `setup-vscode-k8s.sh:72,77,89` | Use `$SETTINGS_FILE` env var, not hardcoded path |
| 7 | `update.sh:1-6` | Add `set -euo pipefail`; explicit error checks |
| 8 | `src/logger.py:173,181` | Replace `exc_info=` with `.opt(exception=).error()` |
| 9a | `k8s/namespace.yaml` | Add Pod Security Admission baseline/restricted labels |
| 9b | `k8s/deployment.yaml:90` | Set `readOnlyRootFilesystem: true` |
| 9c | `k8s/deployment.yaml:49-50` | Remove `KUBECONFIG` env var |
| 9d | `k8s/deployment.yaml` | Add `seccompProfile: RuntimeDefault` |
| 9e | `src/helm_manager.py:298-301` | Use `--password-stdin` instead of positional arg |
