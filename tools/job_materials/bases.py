"""
A–F role-type bases for JobSearch_2026.

PREMISE:
- Different lanes (A–F) MUST have different emphasis (already true in 01_Masters).
- Fact-check against 00_Profile + master text is REQUIRED before trusting a base for tailor.
- Per-JD tailor does NOT re-run full fact audit.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from tools.job_materials.evidence import lane_seed_bullets, load_evidence_blob, tokens
from tools.job_materials.paths import LANES, bases_runtime_dir, load_lanes, masters_dir


def hkt_now() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M HKT")


def base_file(root: Path, lane: str) -> Path:
    return bases_runtime_dir(root) / f"{lane.upper()}.json"


def list_bases(root: Path) -> list[dict[str, Any]]:
    out = []
    for lane, meta in load_lanes(root).items():
        p = base_file(root, lane)
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
        else:
            out.append(
                {
                    "base_id": lane,
                    "label": meta["label"],
                    "emphasis": meta["emphasis"].split(","),
                    "factcheck": {"status": "missing"},
                    "folder": meta["folder"],
                }
            )
    return out


def sync_base_from_masters(root: Path, lane: str) -> dict[str, Any]:
    """Build runtime base from lane config + evidence bullets (emphasis-ranked)."""
    lane = lane.upper()
    meta = load_lanes(root)[lane]
    emp = [e.strip().lower() for e in meta["emphasis"].split(",") if e.strip()]
    bullets = lane_seed_bullets(root, lane)

    def score(b: str) -> int:
        t = b.lower()
        return sum(1 for e in emp if e in t)

    ranked = sorted(bullets, key=score, reverse=True)
    top = [b for b in ranked if score(b) > 0][:8]
    rest = [b for b in ranked if b not in top][:4]
    chosen = (top + rest)[:10] or ranked[:6]

    # skills-ish tokens from emphasis that appear in evidence
    blob = load_evidence_blob(root, lane=lane).lower()
    skills = []
    for e in emp:
        if e in blob or any(e in b.lower() for b in chosen):
            skills.append(e.upper() if len(e) <= 4 else e.title())
    # unique
    seen = set()
    skills_u = []
    for s in skills:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            skills_u.append(s)

    base = {
        "base_id": lane,
        "label": meta["label"],
        "folder": meta["folder"],
        "masters_path": str(masters_dir(root) / meta["folder"]),
        "emphasis": emp,
        "skills": skills_u[:16],
        "bullets": chosen,
        "summary_seed": (
            f"Base track {lane} — {meta['label']}. "
            f"Emphasis: {', '.join(emp[:8])}."
        ),
        "factcheck": {"status": "pending", "claims": [], "notes": ["Run factcheck"]},
        "synced_at": hkt_now(),
    }
    return base


def save_base(root: Path, base: dict[str, Any]) -> Path:
    p = base_file(root, str(base["base_id"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    base["updated_at"] = hkt_now()
    p.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def load_base(root: Path, lane: str) -> dict[str, Any] | None:
    p = base_file(root, lane)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def factcheck_base(root: Path, base: dict[str, Any]) -> dict[str, Any]:
    """Ground each base bullet in evidence blob (00_Profile + lane masters)."""
    lane = str(base.get("base_id") or "")
    blob = load_evidence_blob(root, lane=lane).lower()
    claims = []
    failed = 0

    def check(kind: str, text: str) -> dict[str, Any]:
        nonlocal failed
        toks = [
            t
            for t in tokens(text)
            if t not in {"the", "and", "for", "with", "from", "that", "this", "result"}
        ]
        if not toks:
            failed += 1
            return {"kind": kind, "text": text, "supported": False, "hit_ratio": 0.0}
        hits = [t for t in toks if t in blob]
        ratio = len(hits) / max(1, len(toks))
        supported = ratio >= 0.30 or len(hits) >= 3
        if not supported:
            failed += 1
        return {
            "kind": kind,
            "text": text,
            "supported": supported,
            "hit_ratio": round(ratio, 2),
            "hits": hits[:8],
        }

    for b in base.get("bullets") or []:
        claims.append(check("bullet", str(b)))
    for s in base.get("skills") or []:
        claims.append(check("skill", str(s)))

    status = "passed" if failed == 0 and claims else "failed"
    if not claims:
        status = "failed"
    base = dict(base)
    base["factcheck"] = {
        "status": status,
        "failed_count": failed,
        "claims": claims,
        "checked_at": hkt_now(),
        "notes": [
            "Fact-check is REQUIRED for role-type bases (A–F).",
            "Per-JD tailor must use a passed base and must NOT re-audit all facts.",
        ],
    }
    return base


def pick_lane_from_text(title: str, teaser: str = "") -> str:
    blob = f"{title} {teaser}".lower()
    scores = {}
    for lane, meta in load_lanes().items():
        emp = meta["emphasis"].split(",")
        scores[lane] = sum(1 for e in emp if e.lower() in blob)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "F"
    return best
