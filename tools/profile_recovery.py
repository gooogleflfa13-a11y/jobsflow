"""Recover missing private scoring keywords without adding a profession default.

Older private query files can contain valid search queries and a valid domain
while omitting the setup-derived evidence/industry keywords.  This module
rebuilds only missing fields from the user's private evidence and query intent.
It never reads or writes tracked product templates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.io_utils import atomic_write_json


_TOKEN_RE = re.compile(
    r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff+#./-]{2,40}"
)
_STOP = {
    "and", "the", "for", "with", "from", "that", "this", "your", "our", "their",
    "into", "over", "under", "after", "before", "role", "roles", "work", "working",
    "job", "jobs", "years", "year", "experience", "professional", "summary",
    "candidate", "company", "hong", "kong", "china", "mainland", "hongkong",
    "http", "https", "www", "com", "about", "required", "requirements", "including",
    "support", "supported", "assist", "assisted", "responsible", "responsibilities",
    "conducted", "prepared", "worked", "helped", "provided", "using", "used", "based",
    "team", "teams", "client", "clients", "department", "departments", "matter", "matters",
    "all", "general", "track", "other", "target", "unknown", "true", "false",
    "million", "rmb", "approximately", "university", "shenzhen", "beijing", "shanghai",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}
_INDUSTRY_STOP = _STOP | {
    "assistant", "associate", "officer", "analyst", "manager", "director", "lead",
    "engineer", "developer", "counsel", "lawyer", "solicitor", "paralegal", "secretary",
    "specialist", "coordinator", "intern", "junior", "senior", "principal", "head",
    "linkedin", "jobsdb", "ctgoodjobs", "freehire", "legal", "law", "compliance",
    "research", "review", "reviews", "contract", "contracts", "litigation", "regulatory",
    "firm", "executive", "house", "local", "intl", "solicitors", "clerk", "nonlit",
    "conveyancing", "disputes", "governance", "policy", "risk", "prc", "律师助理",
}


def _private_profile_dir(repo: Path) -> Path:
    root = Path(repo)
    if root.name == "JobSearch_2026":
        return root / "00_Profile"
    return root / "JobSearch_2026" / "00_Profile"


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _tokens(
    text: str,
    *,
    industry: bool = False,
    skip_title_case: bool = False,
) -> list[str]:
    stop = _INDUSTRY_STOP if industry else _STOP
    out = []
    for raw in _TOKEN_RE.findall(text or ""):
        if skip_title_case and raw[0].isupper() and not raw.isupper():
            continue
        token = raw.casefold().strip(".-_/")
        if token in stop or len(token) < 3 or token.isdigit() or "@" in token:
            continue
        if token.startswith(("20", "19")) and token[2:].isdigit():
            continue
        out.append(token)
    return out


def _ranked_tokens(
    texts: list[str],
    *,
    industry: bool = False,
    skip_title_case: bool = False,
    limit: int = 40,
) -> list[str]:
    counts: dict[str, int] = {}
    for text in texts:
        for token in _tokens(text, industry=industry, skip_title_case=skip_title_case):
            counts[token] = counts.get(token, 0) + 1
    return [
        token
        for token, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _fact_records(profile_dir: Path) -> list[dict[str, Any]]:
    value = _load_json(profile_dir / "fact_evidence.json")
    records = value.get("records")
    return [item for item in records or [] if isinstance(item, dict)]


def _resume_text(profile_dir: Path) -> str:
    path = profile_dir / "resume_runtime" / "resume.txt"
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _evidence_keywords(profile_dir: Path, *, limit: int = 40) -> list[str]:
    records = _fact_records(profile_dir)
    texts: list[str] = []
    for record in records:
        texts.append(str(record.get("claim") or ""))
        texts.extend(str(item) for item in record.get("allowed_phrasing") or [])
    texts.append(_resume_text(profile_dir))
    return _ranked_tokens(texts, limit=limit)


def _query_texts(config: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    profile = config.get("scoring_profile") or {}
    texts.extend(str(item) for item in profile.get("core_keywords") or [])
    texts.extend(str(item) for item in profile.get("adjacent_keywords") or [])
    texts.append(str(profile.get("domain") or ""))
    for query in config.get("queries") or []:
        if not isinstance(query, dict):
            continue
        texts.append(str(query.get("track_hint") or ""))
        texts.extend(str(value) for value in (query.get("terms") or {}).values())
    request = _load_json(Path(config.get("setup_design_request") or "")) if config.get("setup_design_request") else {}
    inputs = request.get("inputs") if isinstance(request, dict) else {}
    if isinstance(inputs, dict):
        texts.append(str(inputs.get("intent") or ""))
    return texts


def _industry_keywords(
    config: dict[str, Any], *, limit: int = 24, use_existing: bool = True
) -> list[str]:
    profile = config.get("scoring_profile") or {}
    current = [str(item).strip().casefold() for item in profile.get("preferred_industry_keywords") or [] if str(item).strip()]
    if current and use_existing:
        return current[:limit]
    domain = str(profile.get("domain") or "").strip().casefold()
    candidates = _ranked_tokens(
        _query_texts(config), industry=True, skip_title_case=True, limit=limit
    )
    if domain and domain not in {"general", "unconfigured", "unknown"}:
        candidates = [domain, *candidates]
    out: list[str] = []
    for item in candidates:
        if item not in out:
            out.append(item)
    return out[:limit]


def repair_scoring_profile(
    repo: Path,
    *,
    persist: bool = True,
    force: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Fill missing scoring keyword fields and return ``(profile, health, changed)``."""
    profile_dir = _private_profile_dir(Path(repo))
    path = profile_dir / "queries.json"
    config = _load_json(path)
    scoring = config.get("scoring_profile") if isinstance(config.get("scoring_profile"), dict) else {}
    scoring = dict(scoring)
    changes: list[str] = []

    evidence = [str(item).strip() for item in scoring.get("evidence_keywords") or [] if str(item).strip()]
    if force or not evidence:
        evidence = _evidence_keywords(profile_dir)
        if evidence:
            scoring["evidence_keywords"] = evidence
            changes.append("evidence_keywords")

    industries = [str(item).strip() for item in scoring.get("preferred_industry_keywords") or [] if str(item).strip()]
    if force or not industries:
        industries = _industry_keywords(config, use_existing=not force)
        if industries:
            scoring["preferred_industry_keywords"] = industries
            changes.append("preferred_industry_keywords")

    missing = []
    if not evidence:
        missing.append("evidence_keywords")
    if not industries:
        missing.append("preferred_industry_keywords")
    health = {
        "schema_version": 1,
        "status": "ready" if not missing else "incomplete",
        "recovered_fields": changes,
        "missing_fields": missing,
        "sources": [
            "00_Profile/fact_evidence.json",
            "00_Profile/resume_runtime/resume.txt",
            "00_Profile/queries.json",
        ],
        "action": "continue" if not missing else "run /setup and confirm target industry/roles",
    }
    scoring["profile_health"] = health
    if config and changes and persist:
        config["scoring_profile"] = scoring
        config["profile_recovery"] = {
            "status": "repaired",
            "fields": changes,
            "source": "private evidence and existing query intent",
        }
        atomic_write_json(path, config)
    return scoring, health, bool(changes)


def refresh_scoring_profile(
    repo: Path,
    *,
    persist: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Rebuild both derived keyword lists from current private sources.

    This is intended for an explicit user refresh after editing the résumé or
    search intent; ordinary scoring uses the non-destructive repair path.
    """
    return repair_scoring_profile(repo, persist=persist, force=True)
