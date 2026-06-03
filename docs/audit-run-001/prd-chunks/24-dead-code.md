# PRD Section 24 — Dead Code Removal

## Kill List

### 1. `src/mcp_server.py.bak`

**Evidence.** Plain backup copy of the live `src/mcp_server.py` created by an
editor or manual `cp`. Confirmed by `grep -c 'def ' src/mcp_server.py.bak`
returning the same handler count as the live file. No import in any Python file
points to this path; `.bak` extensions are not loadable by the Python import
system.

**Action.**
```bash
rm src/mcp_server.py.bak
```

**Verification.**
```bash
git grep mcp_server.py.bak   # must return nothing
ls src/mcp_server.py.bak 2>&1 | grep 'No such file'
```

---

### 2. `src/mcp_server_backup.py`

**Evidence.** Second manual backup, loadable by Python. Contains a reference to
`enhanced_documentation_search` (line 34, line 86) which does not exist in `src/`.
`mcp_server.py` does not import `mcp_server_backup`; `grep -rn mcp_server_backup
src/` returns zero hits outside the file itself.

**Action.**
```bash
rm src/mcp_server_backup.py
```

**Verification.**
```bash
git grep mcp_server_backup   # must return nothing
```

---

### 3. `src/enhanced_tools.py` (36 Tool schema definitions)

**Evidence.** File defines two public functions — `get_enhanced_kubectl_tools()`
and `get_enhanced_helm_tools()` — returning a combined 36 `mcp.types.Tool`
objects. `grep -rn "enhanced_tools\|get_enhanced_kubectl_tools\|get_enhanced_helm_tools" src/`
returns zero hits in any file other than `enhanced_tools.py` itself. The live
`mcp_server.py` does not import the module; none of the 36 schemas are registered
with the MCP dispatch table.

**Options.**

- **Option A (recommended for Sprint 1) — delete.** Removes 854 lines of dead
  schema surface and eliminates the false impression that these tools are
  available to callers.
- **Option B — wire up.** Each schema requires a corresponding handler and a real
  `kubectl` or `helm` subprocess call. This is Sprint 2 work, not Sprint 1.

**Recommendation.** Delete in Sprint 1. Reintroduce a new `kubectl_tools.py` in
Sprint 2 with handlers wired end-to-end against the analyzer framework (see
PRD sections 09 and 17). Do not revive this file; start fresh so the schema
set matches what is actually implemented.

**Action.**
```bash
rm src/enhanced_tools.py
```

**Verification.**
```bash
git grep enhanced_tools   # must return nothing
python -c "import sys; sys.path.insert(0,'src'); import mcp_server"  # must not raise ImportError
```

---

### 4. `src/kubectl_manager.py`

**Evidence.** Imported in `mcp_server.py` lines 32 and 73:
```
from kubectl_manager import KubectlManager
self.kubectl_manager = KubectlManager(non_destructive_mode=...)
```
The object is instantiated but never referenced again in the file. `grep -n
"kubectl_manager\." src/mcp_server.py` returns no method calls; no tool handler
passes work to it. The manager is allocated and then silently discarded at
runtime.

**Action (Sprint 1).** Remove the import and instantiation lines, then delete the
file.
```bash
# Step 1: remove dead wiring in mcp_server.py (lines 32 and 73)
# Step 2:
rm src/kubectl_manager.py
```

**Verification.**
```bash
git grep kubectl_manager   # must return nothing after wiring is removed
python -c "import sys; sys.path.insert(0,'src'); import mcp_server"  # clean import
```

---

### 5. `src/helm_manager.py`

**Evidence.** Identical situation to `kubectl_manager.py`. Imported at lines 33
and 74 of `mcp_server.py`, instantiated as `self.helm_manager`, never called
anywhere else in the file. `grep -n "helm_manager\." src/mcp_server.py` returns
no method invocations.

**Action (Sprint 1).** Remove import and instantiation lines, then delete.
```bash
# Step 1: remove dead wiring in mcp_server.py (lines 33 and 74)
# Step 2:
rm src/helm_manager.py
```

**Verification.**
```bash
git grep helm_manager   # must return nothing after wiring is removed
```

---

### 6. `data/github_issues.db`

**Evidence.** Committed SQLite binary (409+ bytes, grows unbounded as issues are
indexed). Binary blobs in git history inflate clone size for every future
contributor and cannot be meaningfully diffed. The file belongs on a sidecar
volume, not in source control.

**Action.**
```bash
# Remove from working tree and index
git rm --cached data/github_issues.db
rm -f data/github_issues.db

# Prevent re-commit
echo 'data/github_issues.db' >> .gitignore
echo 'data/*.db'            >> .gitignore

# Scrub from history (requires git-filter-repo)
git filter-repo --path data/github_issues.db --invert-paths
```

**Verification.**
```bash
git log --all --full-history -- data/github_issues.db  # must return nothing after filter-repo
git grep github_issues.db -- .gitignore               # must return the added line
```

Any code that opens `data/github_issues.db` at startup must accept the path from
`GITHUB_ISSUES_DB_PATH` so the CI pod can mount it from a PVC.

---

### 7. `tests/__init__.py`

**Evidence.** File contains 15 lines including a docstring claiming "390 tests
across 5 categories" and `__version__ = "1.0.0"`. The 390-test count is
unverified (see CHANGELOG audit in PRD section for false claims). The
`tests/production/` and `tests/unit/` subdirectories each use their own
`conftest.py`; no test file imports `tests` as a package.

**Decision rule.** If `python -m pytest --collect-only` discovers all tests after
removing the file, delete it. If collection breaks, keep it but strip the false
`__version__` and 390-test claim.

**Action.**
```bash
mv tests/__init__.py /tmp/__init__.py.bak
python -m pytest --collect-only   # if tests found, proceed with removal
# file already removed by mv; rm the bak if confirmed clean
```

**Verification.**
```bash
git grep 'tests/__init__'   # no explicit imports
python -m pytest --collect-only 2>&1 | grep -v 'no tests ran'
```

---

### 8. Duplicate getting-started docs — keep one, delete the other

**Evidence.** Two files exist at repo root: `GettingStarted.md` (68 lines) and
`GETTING_STARTED.md` (230 lines). The longer file is the authoritative version;
multiple reviewers flagged the duplication as a navigation hazard.

**Action.** Delete the shorter file; keep `GETTING_STARTED.md`.
```bash
rm GettingStarted.md
grep -rn 'GettingStarted\.md' . --include='*.md'  # update any inbound links
```

**Verification.**
```bash
ls GettingStarted.md 2>&1 | grep 'No such file'
grep -rn 'GettingStarted\.md' . --include='*.md'  # must return nothing
```

---

### 9. `Dockerfile` — `COPY docs/` against a path that does not exist

**Evidence.** `Dockerfile` line 78:
```
COPY docs/ ./docs/
```
The `docs/` directory at repo root is absent from the image build context (the
directory contains only `audit-run-001/` and `kubernetes-reference-docs/`, which
are development artifacts, not runtime dependencies). Docker BuildKit will fail
with `COPY failed: file not found in build context` if `docs/` is ever missing
or excluded via `.dockerignore`.

**Action (recommended).** Remove lines 77-78 (the comment and `COPY docs/` line).
The MCP server reads no file from `docs/` at runtime; no Python module imports
from that path.
```bash
# Delete Dockerfile lines 77-78
```

**Verification.**
```bash
docker build -t mcp-k8s-test .   # must exit 0
grep 'COPY docs' Dockerfile       # must return nothing
```

---

## Sprint Assignment

| Item | Sprint | Owner |
|------|--------|-------|
| Delete `.bak` and `_backup.py` | Sprint 1 | any |
| Delete `enhanced_tools.py` | Sprint 1 | any |
| Remove `kubectl_manager` and `helm_manager` dead wiring + delete files | Sprint 1 | backend lead |
| Remove `data/github_issues.db` + add `.gitignore` + run `filter-repo` | Sprint 1 | repo owner |
| Resolve `tests/__init__.py` | Sprint 1 | test lead |
| Delete `GettingStarted.md` | Sprint 1 | any |
| Fix `Dockerfile` `COPY docs/` line | Sprint 1 | any |
| New `kubectl_tools.py` with wired handlers | Sprint 2 | backend lead |
