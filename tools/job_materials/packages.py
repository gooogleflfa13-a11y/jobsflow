"""Resolve and create on-demand material packages from local tracker rows.

Search and scoring deliberately stop at tracker/CSV output.  Materials need a
stable package boundary, so this module is the single writer for the initial
``01_Masters/<lane>/<tier>/<job-id>_*`` directory and its job snapshot.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from tools.io_utils import atomic_write_json, atomic_write_text
from tools.job_materials.manifest import (
    build_job_manifest,
    derive_tier,
    refresh_job_manifest,
    write_job_manifest,
)
from tools.job_materials.paths import is_archived_path, load_lanes, masters_dir


def _safe_component(value: str, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._ -]+", "_", text)
    text = re.sub(r"[ _]+", "_", text).strip("._")
    return (text or fallback)[:80]


def _tracker_files(root: Path) -> list[Path]:
    tracker = root / "02_Tracker"
    if not tracker.is_dir():
        return []
    paths = [p for p in tracker.rglob("*.csv") if p.is_file()]

    def key(path: Path) -> tuple[int, float, str]:
        # The main apply list is authoritative; scored/candidate exports are a
        # useful fallback when the user selected a row before promoting it.
        priority = 0 if path.name.startswith("hk_apply_list_") else 1
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return priority, -mtime, path.name

    return sorted(paths, key=key)


def _registry_row(root: Path, job_id: str) -> dict[str, str] | None:
    """Fallback lookup in the push-written entered_ids registry.

    Google Sheets is the authoritative source for IDs allocated on push; the
    scored CSVs only carry pre-push prefix IDs (e.g. TMP).  This registry lets
    material tooling resolve a pushed row even before the next scan writes it
    locally.
    """
    wanted = str(job_id or "").strip()
    if not wanted:
        return None
    reg = root / "02_Tracker" / "entered_ids.json"
    try:
        raw = json.loads(reg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entries = raw.get("entries") if isinstance(raw, dict) else None
    if not isinstance(entries, dict):
        return None
    entry = entries.get(wanted)
    if not isinstance(entry, dict):
        return None
    return {
        "岗位编号": str(entry.get("id") or wanted),
        "职位": str(entry.get("title") or ""),
        "公司": str(entry.get("company") or ""),
        "链接": str(entry.get("url") or ""),
        "简历版本": str(entry.get("lane") or "").strip()[:1].upper(),
        "批次": str(entry.get("batch") or ""),
        "入表时间": str(entry.get("entered_at") or ""),
    }


def find_tracker_row(root: Path, job_id: str) -> tuple[dict[str, str], Path] | None:
    """Return the newest exact tracker row for ``job_id``.

    The push-written entered_ids registry is consulted FIRST: it holds the
    officially allocated IDs (e.g. D0-020 -> current job) and is authoritative
    over historical CSVs, where the same ID may have been reused by an older,
    unrelated posting.  CSV files remain the fallback for pre-push rows.
    """
    wanted = str(job_id or "").strip()
    if not wanted:
        return None
    reg_row = _registry_row(root, wanted)
    if reg_row:
        return reg_row, root / "02_Tracker" / "entered_ids.json"
    for path in _tracker_files(root):
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    if str(row.get("岗位编号") or row.get("job_id") or "").strip() == wanted:
                        return {str(k): str(v or "") for k, v in row.items()}, path
        except (OSError, csv.Error, UnicodeError):
            continue
    return None


def _existing_package(root: Path, job_id: str) -> Path | None:
    base = masters_dir(root)
    if not base.is_dir():
        return None
    matches = sorted(
        (
            p
            for p in base.rglob(f"{job_id}_*")
            if p.is_dir() and not is_archived_path(p)
        ),
        key=lambda p: str(p),
    )
    return matches[0].resolve() if matches else None


def _lane_for_row(root: Path, row: dict[str, str]) -> str:
    raw = (row.get("简历版本") or row.get("lane") or "").strip().upper()
    match = re.match(r"([A-G])", raw)
    if match:
        return match.group(1)
    track = (row.get("赛道") or "").strip().upper()
    match = re.match(r"([A-G])", track)
    return match.group(1) if match else "F"


def _snapshot(job_id: str, row: dict[str, str], *, tracker_path: Path, lane: str) -> str:
    role = (row.get("职位") or row.get("title") or "").strip() or "未命名职位"
    company = (row.get("公司") or row.get("company") or "").strip() or "未披露公司"
    publisher = (
        row.get("发布者")
        or row.get("publisher")
        or row.get("发布者名称")
        or row.get("publisher_name")
        or company
    ).strip() or company
    publisher_type = (
        row.get("发布者类型")
        or row.get("publisher_type")
        or "unknown"
    ).strip().lower() or "unknown"
    employer = (
        row.get("用人公司")
        or row.get("employer")
        or row.get("employer_name")
        or ""
    ).strip()
    tier = (row.get("层级") or row.get("tier") or "待审").strip() or "待审"
    source = (row.get("来源") or row.get("source") or "").strip()
    url = (row.get("链接") or row.get("url") or "").strip()
    salary = (row.get("薪资") or row.get("salary") or "").strip()
    lines = [
        f"# {job_id} — {role} @ {company}",
        "",
        f"Role: {role}",
        f"Company: {company}",
        f"Publisher: {publisher}",
        f"Publisher Type: {publisher_type}",
        f"Employer: {employer or '—'}",
        f"Lane: {lane}",
        f"Tier: {tier}",
        f"Source: {source or 'unknown'}",
        f"URL: {url or '—'}",
        f"Salary: {salary or '—'}",
        f"Tracker: {tracker_path.as_posix()}",
        "",
        "This snapshot was created from a local tracker row. Verify the URL and paste",
        "the complete JD with `python3 -m tools.job_materials jd set` before tailoring.",
        "",
    ]
    return "\n".join(lines)


def create_package_from_tracker(root: Path, job_id: str) -> Path:
    """Create a material package for a selected local tracker row.

    Existing packages are returned unchanged.  The function never fabricates a
    package without a matching row because that would sever the job-id contract.
    """
    existing = _existing_package(root, job_id)
    if existing:
        found = find_tracker_row(root, job_id)
        if found:
            row, tracker_path = found
            refresh_job_manifest(
                root=root,
                package=existing,
                row=row,
                tracker_path=tracker_path,
            )
        return existing

    found = find_tracker_row(root, job_id)
    if not found:
        raise LookupError(
            f"job_id={job_id} is not present in local tracker CSVs under {root / '02_Tracker'}"
        )
    row, tracker_path = found
    lane = _lane_for_row(root, row)
    lanes = load_lanes(root)
    lane_folder = lanes.get(lane, {}).get("folder") or f"{lane}_track"
    # The numeric tier in a stable job ID is authoritative.  A stale tracker
    # display value must not silently route a C0/D0 package into 一级/二级.
    tier = _safe_component(
        derive_tier(job_id, row.get("层级") or "").get("label") or "待审",
        fallback="待审",
    )
    company = _safe_component(
        row.get("公司") or row.get("company") or "未披露公司", fallback="未披露公司"
    )
    package = masters_dir(root) / lane_folder / tier / f"{job_id}_未投_{company}"
    package.mkdir(parents=True, exist_ok=True)
    publisher = (
        row.get("发布者")
        or row.get("publisher")
        or row.get("发布者名称")
        or row.get("publisher_name")
        or row.get("公司")
        or row.get("company")
        or "未披露公司"
    ).strip() or "未披露公司"
    publisher_type = (
        row.get("发布者类型") or row.get("publisher_type") or "unknown"
    ).strip().lower() or "unknown"
    employer = (
        row.get("用人公司")
        or row.get("employer")
        or row.get("employer_name")
        or ""
    ).strip()
    atomic_write_text(package / "job_snapshot.md", _snapshot(job_id, row, tracker_path=tracker_path, lane=lane))
    atomic_write_json(
        package / "tracker_row.json",
        {
            "job_id": job_id,
            "lane": lane,
            "publisher_name": publisher,
            "publisher_type": publisher_type,
            "employer_name": employer,
            "tracker_path": str(tracker_path),
            "row": row,
        },
    )
    write_job_manifest(
        package,
        build_job_manifest(
            root=root,
            package=package,
            row=row,
            tracker_path=tracker_path,
        ),
    )
    return package.resolve()


def resolve_package(root: Path, job_id: str) -> Path:
    """Resolve an existing package or create one from its tracker row."""
    return create_package_from_tracker(root, job_id)
