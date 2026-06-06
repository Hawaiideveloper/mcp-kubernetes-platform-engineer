"""
root_cause.py — PRD §18.3.2 root-cause hash computation.
"""

from __future__ import annotations

import hashlib
import re


def root_cause_hash(raw_message: str) -> str:
    """
    Normalize a finding message to a stable dedup key.

    Removes pod/node UIDs, IP addresses, and timestamps so
    two semantically identical findings hash to the same value.
    """
    s = raw_message.lower()
    # Remove UUIDs (8-4-4-4-12 format)
    s = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<uid>', s)
    # Remove IPv4 addresses
    s = re.sub(r'\b\d{1,3}(\.\d{1,3}){3}\b', '<ip>', s)
    # Remove ISO timestamps (YYYY-MM-DDTHH:MM:SS)
    s = re.sub(r'\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}', '<ts>', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return hashlib.sha256(s.encode()).hexdigest()
