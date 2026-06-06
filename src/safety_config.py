"""
Safety configuration loader for trading namespace hardblock.

Loads and validates config/safety.yaml. Server refuses to start if
the file is missing or unparseable.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml


@dataclass
class NamespaceSet:
    """Exact names plus fnmatch patterns for a namespace category."""
    exact: List[str] = field(default_factory=list)
    pattern: List[str] = field(default_factory=list)


@dataclass
class OverrideConfig:
    """Human-only override escape hatch — automation must never set enabled=True."""
    enabled: bool = False
    authorized_pr_label: str = "force-apply"
    authorized_by: str = ""
    expires_at: str = ""


@dataclass
class SafetyConfig:
    """Parsed and validated representation of config/safety.yaml."""
    trading_namespaces: NamespaceSet
    system_namespaces: NamespaceSet
    stateless_web_namespaces: NamespaceSet
    batch_namespaces: NamespaceSet
    default_policy: str
    override: OverrideConfig

    @classmethod
    def load(cls, path: str | None = None) -> "SafetyConfig":
        """
        Load SafetyConfig from YAML file.

        Raises RuntimeError if file is missing or unparseable.
        Env var SAFETY_CONFIG_PATH overrides the default path.
        """
        config_path = path or os.environ.get(
            "SAFETY_CONFIG_PATH",
            str(Path(__file__).parent.parent / "config" / "safety.yaml"),
        )
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh)
        except FileNotFoundError:
            raise RuntimeError(
                f"Safety config not found at {config_path!r}. "
                "Server cannot start without a valid safety.yaml."
            )
        except yaml.YAMLError as exc:
            raise RuntimeError(
                f"Safety config at {config_path!r} is unparseable: {exc}"
            )

        if not isinstance(raw, dict):
            raise RuntimeError(
                f"Safety config at {config_path!r} must be a YAML mapping."
            )

        def _ns_set(key: str) -> NamespaceSet:
            section = raw.get(key, {}) or {}
            return NamespaceSet(
                exact=list(section.get("exact", []) or []),
                pattern=list(section.get("pattern", []) or []),
            )

        ov_raw = raw.get("override", {}) or {}
        override = OverrideConfig(
            enabled=bool(ov_raw.get("enabled", False)),
            authorized_pr_label=str(ov_raw.get("authorized_pr_label", "force-apply")),
            authorized_by=str(ov_raw.get("authorized_by", "") or ""),
            expires_at=str(ov_raw.get("expires_at", "") or ""),
        )

        return cls(
            trading_namespaces=_ns_set("trading_namespaces"),
            system_namespaces=_ns_set("system_namespaces"),
            stateless_web_namespaces=_ns_set("stateless_web_namespaces"),
            batch_namespaces=_ns_set("batch_namespaces"),
            default_policy=str(raw.get("default_policy", "pr_required")),
            override=override,
        )
