"""Append-only, local audit events for important Jobsflow state changes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_audit_event(
    jobsearch_root: Path,
    event: str,
    details: dict[str, Any] | None = None,
) -> Path:
    path = Path(jobsearch_root) / "05_Archive" / "audit" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": event,
        "details": details or {},
    }
    data = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    return path
