"""Resolve JobSearch_2026 roots."""

from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JS = REPO / "JobSearch_2026"
ARCHIVE_DIR_NAMES = {"_archive", "archive", "archives"}


def is_archived_path(path: Path) -> bool:
    """Return True when a path is inside an explicit archive directory.

    Version governance is a product invariant: active selectors must not pick a
    submitted/old document merely because it has the newest filesystem mtime.
    """
    return any(part.casefold() in ARCHIVE_DIR_NAMES for part in Path(path).parts)


def jobsearch_root() -> Path:
    env = os.environ.get("JOBSEARCH_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return JS.resolve()


def profile_dir(root: Path | None = None) -> Path:
    return (root or jobsearch_root()) / "00_Profile"


def masters_dir(root: Path | None = None) -> Path:
    return (root or jobsearch_root()) / "01_Masters"


def tracker_dir(root: Path | None = None) -> Path:
    return (root or jobsearch_root()) / "02_Tracker"


def jds_dir(root: Path | None = None) -> Path:
    d = tracker_dir(root) / "jds"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bases_runtime_dir(root: Path | None = None) -> Path:
    """Runtime fact-check state for A–F bases (does not overwrite master DOCX)."""
    d = (root or jobsearch_root()) / "00_Profile" / "bases_runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


# Industry-neutral fallback. Private setup can replace labels and emphasis.
LANES: dict[str, dict[str, str]] = {
    "A": {"folder": "A_track", "label": "Core target", "emphasis": "core,target"},
    "B": {"folder": "B_track", "label": "Adjacent target", "emphasis": "adjacent,target"},
    "C": {"folder": "C_track", "label": "Skill-adjacent", "emphasis": "skills,transferable"},
    "D": {"folder": "D_track", "label": "Industry-adjacent", "emphasis": "industry,domain"},
    "E": {"folder": "E_track", "label": "Exploration", "emphasis": "exploration,opportunity"},
    "F": {"folder": "F_track", "label": "Other", "emphasis": "general,other"},
}


def load_lanes(root: Path | None = None) -> dict[str, dict[str, str]]:
    """Resolve A–F metadata from private setup and existing private folders."""
    root = root or jobsearch_root()
    lanes = {letter: dict(meta) for letter, meta in LANES.items()}
    path = profile_dir(root) / "queries.json"
    try:
        import json

        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        value = {}
    profile = value.get("scoring_profile") if isinstance(value, dict) else {}
    if not isinstance(profile, dict):
        profile = {}
    mapping = profile.get("track_mapping")
    if isinstance(mapping, dict):
        for letter in lanes:
            label = str(mapping.get(letter) or "").strip()
            if label:
                lanes[letter]["label"] = label
    for rule in profile.get("track_rules") or []:
        if not isinstance(rule, dict):
            continue
        letter = str(rule.get("letter") or "").upper()
        patterns = [
            str(item).strip()
            for item in rule.get("patterns") or []
            if str(item).strip()
        ]
        if letter in lanes and patterns:
            lanes[letter]["emphasis"] = ",".join(patterns)

    master_root = masters_dir(root)
    if master_root.is_dir():
        for letter in lanes:
            existing = sorted(
                path for path in master_root.glob(f"{letter}_*") if path.is_dir()
            )
            if existing:
                lanes[letter]["folder"] = existing[0].name
    return lanes


def lane_masters_folder(lane: str, root: Path | None = None) -> Path | None:
    meta = load_lanes(root).get((lane or "").upper())
    if not meta:
        return None
    return masters_dir(root) / meta["folder"]


def find_latest_master_docx(lane: str, root: Path | None = None) -> Path | None:
    """
    Latest CV master DOCX for a lane: master_*_v*.docx under 01_Masters/<folder>/.
    Excludes cl_master_*. Prefers newest mtime among matches.
    """
    folder = lane_masters_folder(lane, root)
    if not folder or not folder.is_dir():
        return None
    candidates = [
        p
        for p in folder.glob("master_*_v*.docx")
        if p.is_file()
        and not is_archived_path(p)
        and not p.name.startswith("~$")
        and "cl_master" not in p.name
    ]
    if not candidates:
        # fallback: any master_*.docx that looks like a CV master
        candidates = [
            p
            for p in folder.glob("master_*.docx")
            if p.is_file()
            and not is_archived_path(p)
            and not p.name.startswith("~$")
            and "cl_master" not in p.name
        ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_latest_cl_master_docx(lane: str, root: Path | None = None) -> Path | None:
    folder = lane_masters_folder(lane, root)
    if not folder or not folder.is_dir():
        return None
    candidates = [
        p
        for p in folder.glob("cl_master_*_v*.docx")
        if p.is_file() and not is_archived_path(p) and not p.name.startswith("~$")
    ]
    if not candidates:
        candidates = [
            p
            for p in folder.glob("cl_master_*.docx")
            if p.is_file() and not is_archived_path(p) and not p.name.startswith("~$")
        ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]
