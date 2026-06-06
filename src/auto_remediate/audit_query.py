"""
audit_query.py — PRD §18.4 read-only query API for the audit log viewer.

Filters: ns, since, until, finding_id. Returns newest-first, max 500.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


async def query_audit_log(
    log_path: str,
    ns: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    finding_id: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Read audit.jsonl and apply filters. Returns newest-first, limit <= 500.

    At least one filter must be provided.
    Raises ValueError if no filter is given or limit > 500.
    """
    if limit > 500:
        raise ValueError("limit cannot exceed 500")
    if not any([ns, since, until, finding_id]):
        raise ValueError("At least one filter (ns, since, until, finding_id) must be provided")

    path = Path(log_path)
    if not path.exists():
        return []

    results: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue

            ts = rec.get("timestamp", "")

            # Apply since / until bounds
            if since and ts < since:
                continue
            if until and ts > until:
                continue

            # Apply namespace filter
            if ns:
                target = rec.get("target", {})
                if isinstance(target, dict):
                    if target.get("namespace") != ns:
                        continue
                else:
                    continue

            # Apply finding_id filter
            if finding_id and rec.get("finding_id") != finding_id:
                continue

            results.append(rec)

    # Newest first
    results.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return results[:limit]
