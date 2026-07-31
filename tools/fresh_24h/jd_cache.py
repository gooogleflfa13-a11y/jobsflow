"""JD full-text cache: URL-keyed, shared between two-pass scoring and material creation.

Saves full JD body so material tools don't re-fetch what the scan already got.
Cache dir: 02_Tracker/jds/cache/<url_sha256[:16]>.json
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from tools.io_utils import atomic_write_json


def jd_cache_dir(root: Path) -> Path:
    d = root / "JobSearch_2026" / "02_Tracker" / "jds" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _url_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def save_jd_cache(
    url: str,
    text: str,
    *,
    source: str,
    root: Path,
) -> dict[str, Any]:
    entry = {
        "url": url,
        "source": source,
        "text": text,
        "chars": len(text),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    cache_dir = jd_cache_dir(root)
    key = _url_key(url)
    path = cache_dir / f"{key}.json"
    atomic_write_json(path, entry)
    return entry


def load_jd_cache(
    url: str,
    root: Path,
    *,
    max_age_days: int = 60,
    min_chars: int = 100,
) -> tuple[str | None, dict[str, Any]]:
    """Return (text, meta) if cache hit and fresh; (None, {}) otherwise."""
    cache_dir = jd_cache_dir(root)
    key = _url_key(url)
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None, {}
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None, {}

    text = entry.get("text") or ""
    if len(text.strip()) < min_chars:
        return None, entry

    fetched_raw = entry.get("fetched_at", "")
    if fetched_raw:
        try:
            fetched = datetime.fromisoformat(fetched_raw.rstrip("Z"))
            age = datetime.now(timezone.utc) - fetched.replace(tzinfo=timezone.utc)
            if age > timedelta(days=max_age_days):
                return None, entry
        except (ValueError, TypeError):
            pass

    return text, entry


def clear_jd_cache(root: Path, older_than_days: int = 90) -> int:
    """Remove stale cache entries. Returns count removed."""
    cache_dir = jd_cache_dir(root)
    now = datetime.now(timezone.utc)
    removed = 0
    for p in cache_dir.glob("*.json"):
        try:
            entry = json.loads(p.read_text(encoding="utf-8"))
            fetched_raw = entry.get("fetched_at", "")
            if fetched_raw:
                fetched = datetime.fromisoformat(fetched_raw.rstrip("Z"))
                age = now - fetched.replace(tzinfo=timezone.utc)
                if age > timedelta(days=older_than_days):
                    p.unlink()
                    removed += 1
        except (json.JSONDecodeError, OSError, ValueError):
            p.unlink()
            removed += 1
    return removed
