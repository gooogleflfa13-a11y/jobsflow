"""Local CSV tracker merge used by ``push --local-only``."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from tools.fresh_24h.batch_mark import demote_previous_batch, mark_new_rows, sort_fresh_rows
from tools.fresh_24h.tracker_schema import merge_tracker_headers
from tools.io_utils import atomic_write_stream
from tools.spreadsheet_safety import neutralize_spreadsheet_formula


def latest_tracker_path(repo: Path, base_headers: Iterable[str]) -> Path:
    tracker_dir = Path(repo) / "JobSearch_2026" / "02_Tracker"
    tracker_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted(tracker_dir.glob("hk_apply_list_*.csv"), reverse=True)
    if paths:
        return paths[0]
    path = tracker_dir / f"hk_apply_list_{date.today().isoformat()}.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerow(list(base_headers))
    return path


def read_tracker(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def merge_scored_rows(
    repo: Path,
    scored_rows: list[dict[str, Any]],
    *,
    base_headers: Iterable[str],
    pass_extra: Iterable[str] = (),
    mode: str = "temp",
) -> tuple[Path, int]:
    """Merge scored rows into the user's main local CSV, preserving history."""
    path = latest_tracker_path(repo, base_headers)
    existing_header, existing = read_tracker(path)
    headers = merge_tracker_headers(base_headers, repo, additional=pass_extra)
    for name in existing_header:
        if name and name not in headers:
            headers.append(name)
    demote_previous_batch(existing)

    existing_ids = {str(row.get("岗位编号") or "").strip() for row in existing}
    existing_urls = {str(row.get("链接") or "").strip() for row in existing}
    new_rows: list[dict[str, Any]] = []
    for raw in scored_rows:
        row = dict(raw)
        job_id = str(row.get("岗位编号") or "").strip()
        url = str(row.get("链接") or "").strip()
        if (job_id and job_id in existing_ids) or (url and url in existing_urls):
            continue
        for name in headers:
            row.setdefault(name, "")
        new_rows.append(row)
        if job_id:
            existing_ids.add(job_id)
        if url:
            existing_urls.add(url)

    mark_new_rows(new_rows, batch_id=f"{mode}_{date.today().isoformat()}")
    combined = sort_fresh_rows(existing + new_rows)

    def write_rows(handle) -> None:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in combined:
            writer.writerow(
                {
                    name: neutralize_spreadsheet_formula(row.get(name, ""))
                    for name in headers
                }
            )

    atomic_write_stream(path, write_rows, encoding="utf-8-sig", newline="")
    return path, len(new_rows)
