"""CI check: no applier Role/RoleBinding in trading namespaces (US-019).

Run at pull-request time via:
    python3 -m auto_remediate.rbac_ci_check [--path k8s/rbac]

Exits non-zero if any file targeting a trading namespace contains an
auto-remediate-applier Role or RoleBinding.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from auto_remediate.rbac_identities import TRADING_NAMESPACES

# Match any namespace: <value> line (indented or not)
_NS_PATTERN = re.compile(r"namespace:\s+(\S+)", re.MULTILINE)


def check_file(path: Path) -> list[str]:
    """Return a list of violation messages for *path*, or empty list if clean."""
    text = path.read_text(encoding="utf-8")
    violations: list[str] = []

    # Only inspect files that reference the applier role/rolebinding name
    if "auto-remediate-applier" not in text:
        return violations

    for match in _NS_PATTERN.finditer(text):
        ns = match.group(1)
        if ns in TRADING_NAMESPACES:
            violations.append(
                f"{path}: applier identity references trading namespace '{ns}'"
            )

    return violations


def check_directory(root: Path) -> int:
    """Check all YAML files under *root*. Returns exit code (0 = pass)."""
    violations: list[str] = []
    for yaml_path in root.rglob("*.yaml"):
        violations.extend(check_file(yaml_path))
    for yaml_path in root.rglob("*.yml"):
        violations.extend(check_file(yaml_path))

    if violations:
        for v in violations:
            print(f"FAIL: {v}", file=sys.stderr)
        print(
            f"\n{len(violations)} violation(s) found. "
            "Applier bindings in trading namespaces are prohibited.",
            file=sys.stderr,
        )
        return 1

    print("OK: no applier bindings found in trading namespaces.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default="k8s/rbac",
        help="Directory to search for YAML files (default: k8s/rbac)",
    )
    args = parser.parse_args(argv)
    return check_directory(Path(args.path))


if __name__ == "__main__":
    sys.exit(main())
