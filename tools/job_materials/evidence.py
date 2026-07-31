"""Load fact evidence from 00_Profile + lane masters for fact-check."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.job_materials.paths import is_archived_path, load_lanes, masters_dir, profile_dir


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_evidence_blob(root: Path, lane: str | None = None) -> str:
    """Concatenate profile + runtime résumé + lane references for discovery.

    This broad blob is useful for drafting, but it is not the independent
    source used by the base factcheck because it includes generated documents.
    """
    parts: list[str] = []
    pd = profile_dir(root)
    for name in (
        "master_bullets.md",
        "ai_skill_line.txt",
        "README.md",
    ):
        parts.append(_read(pd / name))
    # Setup writes the user's imported CV here.  Keep the glob date-agnostic so
    # a fresh clone never depends on a historical private filename.
    parts.append(_read(pd / "resume_runtime" / "resume.txt"))
    for facts_path in sorted(pd.glob("facts_*")):
        if facts_path.is_file() and not is_archived_path(facts_path):
            parts.append(_read(facts_path))

    md = masters_dir(root)
    lanes = load_lanes(root)
    # shared bullets if any
    for p in sorted(md.glob("**/cl_skeleton_*.md")):
        if is_archived_path(p):
            continue
        if lane:
            folder = lanes.get(lane.upper(), {}).get("folder", "")
            if folder and folder not in str(p):
                continue
        parts.append(_read(p))
    for p in sorted(md.glob("**/linkedin_llmo_*.md")):
        if is_archived_path(p):
            continue
        if lane:
            folder = lanes.get(lane.upper(), {}).get("folder", "")
            if folder and folder not in str(p):
                continue
        parts.append(_read(p)[:15000])
    for p in sorted(md.glob("**/README.md")):
        if is_archived_path(p):
            continue
        if "01_Masters" in str(p) and p.parent.name.startswith(("A_", "B_", "C_", "D_", "E_", "F_")):
            if lane:
                folder = lanes.get(lane.upper(), {}).get("folder", "")
                if folder and p.parent.name != folder:
                    continue
            parts.append(_read(p)[:8000])

    return "\n".join(parts)


def load_fact_records(root: Path) -> list[dict[str, Any]]:
    """Load independent, user-confirmed evidence nodes.

    Generated CVs, cover letters and LinkedIn drafts are excluded by design.
    Missing or invalid records return an empty list so callers can fail closed.
    """
    path = profile_dir(root) / "fact_evidence.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return []
    return [
        record
        for record in records
        if isinstance(record, dict) and record.get("evidence_id") and record.get("claim")
    ]


def load_fact_evidence(root: Path) -> str:
    """Load only independent fact material for grounding and factcheck.

    Active master files are intentionally excluded. Otherwise a generated
    claim could prove itself simply because the same sentence appears in a
    generated source document.
    """
    pd = profile_dir(root)
    parts = [_read(pd / "fact_evidence.json")]
    for facts_path in sorted(pd.glob("facts_*")):
        if facts_path.is_file() and not is_archived_path(facts_path):
            parts.append(_read(facts_path))
    parts.extend([_read(pd / "master_bullets.md"), _read(pd / "ai_skill_line.txt")])
    return "\n".join(part for part in parts if part)


def extract_bullets_from_markdown(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(("- ", "• ", "* ")):
            body = s[2:].strip()
            if (
                len(body) > 40
                and "从现有" not in body
                and "可选" not in body[:6]
                and not re.search(r"\bAI\b", body, re.IGNORECASE)
            ):
                out.append(body)
    return out


def lane_seed_bullets(root: Path, lane: str) -> list[str]:
    """Prefer independent fact material + lane skeleton for base material pool."""
    blob = load_fact_evidence(root)
    # Historical cl_skeleton files are templates, not current fact evidence;
    # including them reintroduces superseded competency lists into the base.
    bullets = extract_bullets_from_markdown(blob)
    # Plain-text/PDF imports often have no Markdown bullets. The imported
    # résumé is an independent user source, so preserve substantive lines as
    # candidate claims rather than silently producing an empty base.
    resume_text = _read(profile_dir(root) / "resume_runtime" / "resume.txt")
    for paragraph in re.split(r"\n\s*\n|\n", resume_text):
        candidate = re.sub(r"\s+", " ", paragraph).strip(" -*•\t")
        if len(candidate) > 40 and candidate not in bullets:
            bullets.append(candidate)
    # also pull module section from master_bullets if tagged
    mb = _read(profile_dir(root) / "master_bullets.md")
    bullets.extend(extract_bullets_from_markdown(mb))
    # dedupe
    seen = set()
    out = []
    for b in bullets:
        k = b.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(b)
    return out


def tokens(text: str) -> set[str]:
    return {
        t.lower()
        for t in re.findall(
            r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff\+\#\./-]{2,40}", text or ""
        )
    }
