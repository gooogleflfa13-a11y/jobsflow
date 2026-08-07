#!/usr/bin/env python3
"""Batch markers for fresh_24h sheet: 本轮新增 / 批次 / 入表时间.

After each daily or temp scan:
  1. Previous 本轮新增=是 → 否；入表时间 从具体时刻改为「较早入表」；去掉米色底
  2. New rows: 本轮新增=是 + batch_id + 具体入表时间 + 米色底
  3. Sort: 是 first, then CareerOps分数 desc
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

# User-facing label when a row is no longer the newest batch
EARLIER_ENTRY_LABEL = "较早入表"

# Beige highlight for 本轮新增=是 (Google Sheets RGB 0–1)
BEIGE_RGB = {"red": 1.0, "green": 0.95, "blue": 0.8}  # soft beige / 浅米色


def hkt_now_str() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M HKT")


def make_batch_id(mode: str = "temp", when: datetime | None = None) -> str:
    dt = when or datetime.now(timezone.utc)
    hkt = dt + timedelta(hours=8)
    # dt is often naive UTC-ish; prefer explicit UTC
    if dt.tzinfo is None:
        hkt = dt.replace(tzinfo=timezone.utc) + timedelta(hours=8)
    else:
        hkt = dt.astimezone(timezone(timedelta(hours=8)))
    tag = "temp" if mode in {"temp", "临时", "temporary"} else "daily"
    return f"{tag}_{hkt.strftime('%Y-%m-%d_%H%M')}"


def demote_previous_batch(rows: list[dict[str, Any]]) -> None:
    """Previous 本轮 → 否; replace concrete 入表时间 with 较早入表."""
    for r in rows:
        was_new = (r.get("本轮新增") or "") == "是"
        r["本轮新增"] = "否"
        # Only rewrite 入表时间 when it looks like a concrete timestamp (or was 本轮)
        entered = (r.get("入表时间") or "").strip()
        if was_new or (entered and entered != EARLIER_ENTRY_LABEL and "HKT" in entered):
            r["入表时间"] = EARLIER_ENTRY_LABEL
        elif not entered:
            r["入表时间"] = EARLIER_ENTRY_LABEL


def mark_new_rows(
    rows: list[dict[str, Any]],
    *,
    batch_id: str,
    entered_at: str | None = None,
) -> None:
    entered = entered_at or hkt_now_str()
    for r in rows:
        r["本轮新增"] = "是"
        r["批次"] = batch_id
        r["入表时间"] = entered


def sort_fresh_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """本轮新增 first, then by score desc."""

    def key(r: dict[str, Any]) -> tuple:
        is_new = 0 if (r.get("本轮新增") or "") == "是" else 1
        try:
            score = -float(r.get("CareerOps分数") or 0)
        except ValueError:
            score = 0.0
        entered = r.get("入表时间") or ""
        # concrete times sort before 较早入表 within same group
        is_earlier = 1 if entered == EARLIER_ENTRY_LABEL else 0
        return (is_new, score, is_earlier, entered)

    out = sorted(rows, key=key)
    for i, r in enumerate(out, start=2):
        r["行号"] = str(i)
    return out


def ensure_batch_columns(row: dict[str, Any]) -> dict[str, Any]:
    row.setdefault("本轮新增", "否")
    row.setdefault("批次", row.get("批次") or "")
    row.setdefault("入表时间", row.get("入表时间") or "")
    return row


def write_entered_registry(
    rows: list[dict[str, Any]],
    *,
    tracker_dir: str | Path,
    batch_id: str | None = None,
) -> Path | None:
    """Persist the officially allocated sheet IDs (岗位编号) to a local registry.

    Google Sheets is the authoritative source for IDs allocated on push; the
    scored CSVs only carry pre-push prefix IDs (e.g. TMP).  Material tooling
    (build_jobs_json / find_tracker_row) consults this registry as a fallback so
    a pushed row can be resolved even before the next scan writes it locally.

    Registry shape (append + dedupe by 岗位编号):
      {
        "schema_version": 1,
        "updated_at": "...HKT",
        "entries": {
          "D0-020": {"id": "D0-020", "url": "...", "title": "...",
                      "company": "...", "batch": "...", "entered_at": "..."}
        }
      }
    """
    from pathlib import Path

    tracker = Path(tracker_dir)
    if not tracker.is_dir():
        return None
    reg_path = tracker / "entered_ids.json"

    existing: dict[str, Any] = {"schema_version": 1, "updated_at": "", "entries": {}}
    try:
        raw = json.loads(reg_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("entries"), dict):
            existing = raw
    except (OSError, ValueError):
        pass

    entries = existing.setdefault("entries", {})
    now = hkt_now_str()
    for r in rows:
        jid = str(r.get("岗位编号") or "").strip()
        url = str(r.get("链接") or r.get("url") or "").strip()
        title = str(r.get("职位") or r.get("title") or "").strip()
        company = str(r.get("公司") or r.get("company") or "").strip()
        if not jid:
            continue
        entries[jid] = {
            "id": jid,
            "url": url,
            "title": title,
            "company": company,
            "lane": str(r.get("简历版本") or r.get("lane") or "").strip()[:1].upper(),
            "batch": str(r.get("批次") or batch_id or ""),
            "entered_at": str(r.get("入表时间") or now),
        }
    existing["updated_at"] = now

    from tools.io_utils import atomic_write_json

    atomic_write_json(reg_path, existing)
    return reg_path
