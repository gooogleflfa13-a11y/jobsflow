"""Load fact evidence from 00_Profile + lane masters for fact-check."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from tools.job_materials.paths import load_lanes, masters_dir, profile_dir


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def load_evidence_blob(root: Path, lane: str | None = None) -> str:
    """Concatenate profile + runtime résumé + lane masters for grounding."""
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
        if facts_path.is_file():
            parts.append(_read(facts_path))

    md = masters_dir(root)
    lanes = load_lanes(root)
    # shared bullets if any
    for p in sorted(md.glob("**/cl_skeleton_*.md")):
        if lane:
            folder = lanes.get(lane.upper(), {}).get("folder", "")
            if folder and folder not in str(p):
                continue
        parts.append(_read(p))
    for p in sorted(md.glob("**/linkedin_llmo_*.md")):
        if lane:
            folder = lanes.get(lane.upper(), {}).get("folder", "")
            if folder and folder not in str(p):
                continue
        parts.append(_read(p)[:15000])
    for p in sorted(md.glob("**/README.md")):
        if "01_Masters" in str(p) and p.parent.name.startswith(("A_", "B_", "C_", "D_", "E_", "F_")):
            if lane:
                folder = lanes.get(lane.upper(), {}).get("folder", "")
                if folder and p.parent.name != folder:
                    continue
            parts.append(_read(p)[:8000])

    return "\n".join(parts)


def extract_bullets_from_markdown(text: str) -> list[str]:
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(("- ", "• ", "* ")):
            body = s[2:].strip()
            if len(body) > 40 and "从现有" not in body and "可选" not in body[:6]:
                out.append(body)
    return out


def lane_seed_bullets(root: Path, lane: str) -> list[str]:
    """Prefer master_bullets + lane skeleton for base material pool."""
    blob = load_evidence_blob(root, lane=lane)
    bullets = extract_bullets_from_markdown(blob)
    # Plain-text/PDF imports often have no Markdown bullets.  Treat substantive
    # paragraphs as evidence candidates while retaining the same fact-check
    # gate; no claim is invented, it is copied from the imported résumé.
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
