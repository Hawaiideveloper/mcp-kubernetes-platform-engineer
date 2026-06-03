# PRD Section 20 — CI/CD Pipeline (albright-runners) + Image Pinning

## Problem Statement

The repository has no `.github/workflows/` directory. The sole container reference in
`k8s/deployment.yaml` (line 37) uses the `:latest` tag with `imagePullPolicy: Always`,
making deployments non-reproducible and exposing the cluster to silent image replacement.
No pre-commit hooks enforce code quality before pushes. No image vulnerability scanning
exists in any pipeline step.

---

## Deliverable 1: `.github/workflows/ci.yml`

Runs on every push and pull-request targeting `main`. All jobs use the self-hosted
`albright-runners` pool.

```yaml
name: CI

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  lint:
    name: Lint (ruff)
    runs-on: albright-runners
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install lint deps
        run: pip install ruff

      - name: Run ruff
        run: ruff check src/ tests/

  type-check:
    name: Type-check (mypy)
    runs-on: albright-runners
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install deps
        run: pip install -r requirements.txt mypy

      - name: Run mypy
        run: mypy src/ --ignore-missing-imports

  test:
    name: Test (pytest, coverage >= 80%)
    runs-on: albright-runners
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install deps
        run: pip install -r requirements.txt -r requirements-test.txt

      - name: Run pytest with coverage gate
        run: |
          pytest --cov=src --cov-report=term-missing --cov-fail-under=80 tests/

  build-and-scan:
    name: Build image + Trivy scan
    runs-on: albright-runners
    needs: [lint, type-check, test]
    permissions:
      contents: read
      packages: write
      security-events: write
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build image (no push on PR)
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: false
          load: true
          tags: ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:ci-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Scan image with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:ci-${{ github.sha }}"
          format: "sarif"
          output: "trivy-results.sarif"
          severity: "HIGH,CRITICAL"
          exit-code: "1"

      - name: Upload Trivy SARIF
        if: always()
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: "trivy-results.sarif"

  push-main:
    name: Push image to GHCR (main only)
    runs-on: albright-runners
    needs: [build-and-scan]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    permissions:
      contents: read
      packages: write
    outputs:
      digest: ${{ steps.push.outputs.digest }}
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push with digest-stable tag
        id: push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:sha-${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

## Deliverable 2: `.github/workflows/release.yml`

Triggered on semver tags (`v*.*.*`). Pushes both a semver tag and a `sha-<short>` tag,
then pins `k8s/deployment.yaml` to the image digest and opens a commit on `main`.

```yaml
name: Release

on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"

jobs:
  release-image:
    name: Tag, push, and pin digest
    runs-on: albright-runners
    permissions:
      contents: write
      packages: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Derive short SHA
        id: meta
        run: |
          echo "short_sha=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
          echo "tag=${GITHUB_REF_NAME}" >> "$GITHUB_OUTPUT"

      - name: Build and push semver + sha tags
        id: push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:${{ steps.meta.outputs.tag }}
            ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:sha-${{ steps.meta.outputs.short_sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Scan release image with Trivy
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: "ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer:${{ steps.meta.outputs.tag }}"
          format: "table"
          severity: "HIGH,CRITICAL"
          exit-code: "1"

      - name: Pin digest in k8s/deployment.yaml
        run: |
          DIGEST="${{ steps.push.outputs.digest }}"
          REPO="ghcr.io/${{ github.repository_owner }}/mcp-kubernetes-platform-engineer"
          PINNED="${REPO}@${DIGEST}"
          sed -i "s|image: .*mcp-kubernetes-platform-engineer.*|image: ${PINNED}|" k8s/deployment.yaml

      - name: Set imagePullPolicy to IfNotPresent
        run: |
          sed -i "s|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|" k8s/deployment.yaml

      - name: Commit pinned digest
        run: |
          git config user.name "albright-bot"
          git config user.email "bot@albright-labs.io"
          git add k8s/deployment.yaml
          git commit -m "feat(release): pin image digest for ${{ steps.meta.outputs.tag }}"
          git push origin HEAD:main
```

---

## Deliverable 3: Pre-commit Hooks (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
        args: [--ignore-missing-imports]
```

Install with:

```
pip install pre-commit
pre-commit install
```

---

## Deliverable 4: `k8s/deployment.yaml` Image Patch

Replace lines 37-38 in the existing `k8s/deployment.yaml`. Before any release the
placeholder digest must be replaced by the actual digest output from the release workflow
(`steps.push.outputs.digest`).

```yaml
        image: ghcr.io/hawaiideveloper/mcp-kubernetes-platform-engineer@sha256:REPLACE_WITH_DIGEST
        imagePullPolicy: IfNotPresent
```

The release workflow (`release.yml`) performs this substitution automatically on each tag
push. During development, the CI workflow builds and scans the image but does not update
`deployment.yaml`; only a tagged release triggers the pin.

---

## Deliverable 5: Dependabot Config (`.github/dependabot.yml`)

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "python"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
    labels:
      - "dependencies"
      - "github-actions"
```

---

## Verification: Green CI on a Sample PR

1. Create a branch: `git checkout -b feat/sample-pr`
2. Add a trivial passing test to `tests/test_smoke.py`:

```python
def test_import():
    import src.mcp_server  # noqa: F401
    assert True
```

3. Push and open a PR against `main`.
4. Confirm all four CI jobs complete green: `lint`, `type-check`, `test`, `build-and-scan`.
5. The `push-main` job must be skipped (PR context, not a push to `main`).
6. Merge the PR; confirm `push-main` runs and produces a `sha-<full-sha>` tag in GHCR.
7. Push a tag `v0.1.0`; confirm `release.yml` runs, pushes both `v0.1.0` and
   `sha-<short>` tags, scans clean, and commits the pinned digest back to `main`.
8. Inspect `k8s/deployment.yaml` on `main`; verify `image:` contains `@sha256:` and
   `imagePullPolicy: IfNotPresent`.

---

## Acceptance Criteria

- No workflow uses `runs-on: ubuntu-latest`; all use `runs-on: albright-runners`.
- Coverage gate fails the `test` job when coverage drops below 80%.
- Trivy blocks the pipeline on any HIGH or CRITICAL CVE in the built image.
- `k8s/deployment.yaml` never references `:latest` after the first tagged release.
- Dependabot opens weekly PRs for both pip and GitHub Actions dependencies.
- Pre-commit hooks block commits that fail ruff, mypy, trailing-whitespace, or
  end-of-file checks.
- Bot commits in `release.yml` use `albright-bot` identity; no AI attribution appears in
  any commit message.
