"""Append-only admin action log under data/."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_AUDIT_FILE = Path("data/admin_audit.jsonl")


def append_audit(
    actor_id: int,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """
    Args:
     actor_id(int): Admin Telegram user id.
     action(str): Action name (e.g. ``patch``, ``unlog``, ``trigger``).
     payload(dict[str, Any] | None): Extra fields (dates, note, dry_run).

    Returns:
     None
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "action": action,
        **(payload or {}),
    }
    try:
        _AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError as e:
        logger.warning("Failed to append admin audit: %s", e)


def read_audit(limit: int = 20) -> list[dict[str, Any]]:
    """
    Args:
     limit(int): Max most-recent lines to return.

    Returns:
     list[dict[str, Any]]: Newest first.
    """
    if not _AUDIT_FILE.exists():
        return []
    try:
        lines = _AUDIT_FILE.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logger.warning("Failed to read admin audit: %s", e)
        return []
    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return records
