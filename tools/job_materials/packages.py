"""Resolve and create on-demand material packages from local tracker rows.

Search and scoring deliberately stop at tracker/CSV output.  Materials need a
stable package boundary, so this module is the single writer for the initial
``01_Masters/<lane>/<tier>/<job-id>_*`` directory and its job snapshot.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from tools.io_utils import atomic_write_json, atomic_write_text
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


def find_tracker_row(root: Path, job_id: str) -> tuple[dict[str, str], Path] | None:
    """Return the newest exact tracker row for ``job_id``."""
    wanted = str(job_id or "").strip()
    if not wanted:
        return None
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
    match = re.match(r"([A-F])", raw)
    if match:
        return match.group(1)
    track = (row.get("赛道") or "").strip().upper()
    match = re.match(r"([A-F])", track)
    return match.group(1) if match else "F"


def _snapshot(job_id: str, row: dict[str, str], *, tracker_path: Path, lane: str) -> str:
    role = (row.get("职位") or row.get("title") or "").strip() or "未命名职位"
    company = (row.get("公司") or row.get("company") or "").strip() or "未披露公司"
    tier = (row.get("层级") or row.get("tier") or "待审").strip() or "待审"
    source = (row.get("来源") or row.get("source") or "").strip()
    url = (row.get("链接") or row.get("url") or "").strip()
    salary = (row.get("薪资") or row.get("salary") or "").strip()
    lines = [
        f"# {job_id} — {role} @ {company}",
        "",
        f"Role: {role}",
        f"Company: {company}",
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
    tier = _safe_component(row.get("层级") or "待审", fallback="待审")
    company = _safe_component(
        row.get("公司") or row.get("company") or "未披露公司", fallback="未披露公司"
    )
    package = masters_dir(root) / lane_folder / tier / f"{job_id}_未投_{company}"
    package.mkdir(parents=True, exist_ok=True)
    atomic_write_text(package / "job_snapshot.md", _snapshot(job_id, row, tracker_path=tracker_path, lane=lane))
    atomic_write_json(
        package / "tracker_row.json",
        {
            "job_id": job_id,
            "lane": lane,
            "tracker_path": str(tracker_path),
            "row": row,
        },
    )
    return package.resolve()


def resolve_package(root: Path, job_id: str) -> Path:
    """Resolve an existing package or create one from its tracker row."""
    return create_package_from_tracker(root, job_id)
