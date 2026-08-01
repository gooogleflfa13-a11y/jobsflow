"""
A–F role-type bases for JobSearch_2026.

PREMISE:
- Different lanes (A–F) MUST have different emphasis (already true in 01_Masters).
- Fact-check against the independent 00_Profile fact evidence store is REQUIRED before trusting a base for tailor.
- Generated masters are never accepted as evidence; per-JD tailor may reorder only a passed evidence set and does NOT invent facts.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from tools.job_materials.evidence import (
    lane_seed_bullets,
    load_fact_evidence,
    load_fact_records,
    tokens,
)
from tools.job_materials.paths import LANES, bases_runtime_dir, load_lanes, masters_dir


SEMANTIC_PROFILE_DEFAULT = {
    "schema_version": 1,
    "upper_bound_level": "medium",
    "label": "中（平衡）",
    "transfer_scope": "允许相邻职责和明确可迁移能力，但不等同于已有实操经历",
    "transfer_score_cap": 4.5,
    "upper_only_score_cap": 4.0,
    "direct_facts_score_cap": 5.0,
    "forbid_invented_experience": True,
}

DEFAULT_FORBIDDEN_CLAIMS = [
    "不得把能力上沿写成已经承担过的实操职责",
    "不得补造雇主、客户、工具、证书、牌照、年限、指标或结果",
    "不得把相邻能力推断当作事实经历或已验证资格",
]


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
    blob = load_fact_evidence(root).lower()
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

    # The semantic matcher receives two explicit layers: facts_anchor is what
    # may be stated as experience; capability_upper is only a transferable
    # potential layer.  The user's calibration is private setup state and is
    # never inferred from a profession or a built-in legal profile.
    try:
        query_config = json.loads(
            (Path(root) / "00_Profile" / "queries.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        query_config = {}
    scoring = query_config.get("scoring_profile") if isinstance(query_config, dict) else {}
    if not isinstance(scoring, dict):
        scoring = {}
    semantic_profile = dict(SEMANTIC_PROFILE_DEFAULT)
    configured_semantic = scoring.get("semantic_profile")
    if isinstance(configured_semantic, dict):
        semantic_profile.update(configured_semantic)

    existing = load_base(root, lane) or {}
    facts_anchor = existing.get("facts_anchor") or chosen
    capability_upper = existing.get("capability_upper")
    if not isinstance(capability_upper, list) or not capability_upper:
        capability_upper = [
            {
                "capability": skill,
                "basis": "transferable_potential",
                "not_experience": True,
                "note": "可用于相邻岗位语义比较，不可直接写成已承担职责",
            }
            for skill in skills_u[:12]
        ]
    forbidden_claims = existing.get("forbidden_claims")
    if not isinstance(forbidden_claims, list) or not forbidden_claims:
        forbidden_claims = list(DEFAULT_FORBIDDEN_CLAIMS)

    base = {
        "base_id": lane,
        "label": meta["label"],
        "folder": meta["folder"],
        "masters_path": str(masters_dir(root) / meta["folder"]),
        "emphasis": emp,
        "skills": skills_u[:16],
        "bullets": chosen,
        "facts_anchor": facts_anchor[:12],
        "capability_upper": capability_upper[:16],
        "forbidden_claims": forbidden_claims[:16],
        "semantic_profile": semantic_profile,
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
    """Ground each base claim in independent evidence nodes.

    The old implementation searched a blob that included generated masters.
    That made a claim capable of validating itself.  This implementation
    requires ``00_Profile/fact_evidence.json`` and matches each claim against
    its independent records; generated masters are never used as evidence.
    """
    lane = str(base.get("base_id") or "")
    records = load_fact_records(root)
    claims = []
    failed = 0

    if not records:
        base = dict(base)
        base["factcheck"] = {
            "status": "failed",
            "failed_count": 1,
            "claims": [],
            "checked_at": hkt_now(),
            "notes": [
                "Independent fact_evidence.json is missing or invalid; fail closed.",
                "Generated masters are not accepted as fact evidence.",
            ],
        }
        return base

    def metric_tokens(text: str) -> set[str]:
        return {
            m.lower().replace(" ", "")
            for m in re.findall(
                r"(?:rmb\s*\d+(?:\.\d+)?\s*(?:million|m)?|\d+(?:\.\d+)?\s*%|\d+\+)",
                text.lower(),
            )
        }

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
        claim_metrics = metric_tokens(text)
        record_infos = []
        for record in records:
            record_text = " ".join(
                [
                    str(record.get("claim") or ""),
                    " ".join(str(x) for x in record.get("allowed_phrasing") or []),
                    " ".join(str(x) for x in record.get("contexts") or []),
                ]
            )
            record_tokens = tokens(record_text)
            hits = [t for t in toks if t in record_tokens]
            ratio = len(hits) / max(1, len(toks))
            record_metrics = metric_tokens(record_text)
            record_infos.append((record, record_tokens, record_metrics, hits, ratio))
        union_tokens = set().union(*(item[1] for item in record_infos))
        union_metrics = set().union(*(item[2] for item in record_infos))
        hits = [t for t in toks if t in union_tokens]
        ratio = len(hits) / max(1, len(toks))
        metrics_supported = claim_metrics.issubset(union_metrics)
        hit_count = len(hits)
        evidence_ids = [
            item[0].get("evidence_id")
            for item in sorted(record_infos, key=lambda item: item[4], reverse=True)
            if item[3]
        ][:4]
        # A concise Core line may combine two independently supported facts;
        # use a moderate lexical threshold while still requiring every metric
        # to appear in the matched evidence node.
        supported = bool(metrics_supported and (ratio >= 0.30 or hit_count >= 3))
        if not supported:
            failed += 1
        return {
            "kind": kind,
            "text": text,
            "supported": supported,
            "hit_ratio": round(ratio, 2),
            "hits": hits[:8],
            "evidence_ids": evidence_ids,
            "metric_tokens": sorted(claim_metrics),
        }

    fact_claims = base.get("facts_anchor") or base.get("bullets") or []
    for b in fact_claims:
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
            "Fact-check is REQUIRED for role-type bases before semantic matching.",
            "Claims were matched to independent fact_evidence.json records; generated masters were excluded.",
            "Per-JD tailor and semantic matching must use a passed base and must NOT silently invent or alter facts.",
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
