#!/usr/bin/env python3
"""LinkedIn job description enrichment via linkedin-search `detail` CLI.

The public job search cards only return a short teaser (collapsed "See more" text).
Full JD HTML is available from the detail page parser (show-more-less-html__markup)
without browser click automation.

Modes:
  shallow — used before sheet push / batch CareerOps (capped, rate-limited, truncated)
  deep    — used when user asks for 深度分析 (full text + richer scoring context)

SYSTEM RULE: JobSearch_2026/03_Applications/系统规则_PDF与检索_强制遵守.md
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_DEFAULT = Path(__file__).resolve().parents[2]
DETAIL_CLI = (
    REPO_DEFAULT / ".agents/skills/linkedin-search/cli/src/cli.ts"
)

# Shallow defaults (入表前)
SHALLOW_MAX_JOBS = 30
SHALLOW_SLEEP_S = 1.4
SHALLOW_DESC_CHARS = 2500
SHALLOW_TIMEOUT_S = 45

# Deep defaults (单条或小批量精评)
DEEP_SLEEP_S = 1.8
DEEP_DESC_CHARS = 12000
DEEP_TIMEOUT_S = 60


@dataclass
class EnrichResult:
    ok: bool
    job_id: str | None = None
    description: str = ""
    seniority: str | None = None
    employment_type: str | None = None
    job_function: str | None = None
    industries: str | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def extract_linkedin_job_id(url_or_id: str) -> str | None:
    s = (url_or_id or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{6,}", s):
        return s
    m = re.search(r"urn:li:jobPosting:(\d+)", s)
    if m:
        return m.group(1)
    m = re.search(r"linkedin\.com/jobs/view/[^/?#]*?(\d{6,})", s, re.I)
    if m:
        return m.group(1)
    m = re.search(r"/(\d{6,})(?:\?|$|#)", s)
    if m:
        return m.group(1)
    m = re.search(r"-(\d{6,})(?:\?|$|#)", s)
    if m:
        return m.group(1)
    return None


def is_linkedin_url(url: str) -> bool:
    u = (url or "").lower()
    return "linkedin.com" in u and ("/jobs/" in u or "jobposting" in u)


def fetch_linkedin_detail(
    url_or_id: str,
    *,
    repo: Path | None = None,
    timeout: int = SHALLOW_TIMEOUT_S,
) -> EnrichResult:
    """Call bun linkedin-search detail; return parsed description."""
    repo = (repo or REPO_DEFAULT).resolve()
    cli = repo / ".agents/skills/linkedin-search/cli/src/cli.ts"
    jid = extract_linkedin_job_id(url_or_id)
    if not jid:
        return EnrichResult(ok=False, error=f"bad_id:{url_or_id[:80]}")
    if not cli.exists():
        return EnrichResult(ok=False, job_id=jid, error=f"cli_missing:{cli}")

    cmd = ["bun", "run", str(cli), "detail", jid, "--format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return EnrichResult(ok=False, job_id=jid, error="timeout")
    except FileNotFoundError:
        return EnrichResult(ok=False, job_id=jid, error="bun_not_found")

    raw_out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or raw_out or "")[:300]
        return EnrichResult(ok=False, job_id=jid, error=f"exit_{proc.returncode}:{err}")

    start = raw_out.find("{")
    if start < 0:
        return EnrichResult(ok=False, job_id=jid, error="no_json")
    try:
        payload = json.loads(raw_out[start:])
    except json.JSONDecodeError as e:
        return EnrichResult(ok=False, job_id=jid, error=f"json:{e}")

    if payload.get("error"):
        return EnrichResult(
            ok=False,
            job_id=jid,
            error=str(payload.get("error"))[:200],
            raw=payload,
        )

    desc = (payload.get("description") or "").strip()
    return EnrichResult(
        ok=bool(desc),
        job_id=str(payload.get("id") or jid),
        description=desc,
        seniority=payload.get("seniority"),
        employment_type=payload.get("employmentType"),
        job_function=payload.get("jobFunction"),
        industries=payload.get("industries"),
        error=None if desc else "empty_description",
        raw=payload,
    )


def enrich_hits_shallow(
    hits: list[dict[str, Any]],
    *,
    repo: Path | None = None,
    max_jobs: int = SHALLOW_MAX_JOBS,
    sleep_s: float = SHALLOW_SLEEP_S,
    desc_chars: int = SHALLOW_DESC_CHARS,
    only_sources: set[str] | None = None,
) -> dict[str, Any]:
    """In-place: for LinkedIn hits, replace/extend teaser with detail description.

    Only enriches up to max_jobs LinkedIn URLs (first-seen order).
    Mutates hit['teaser'] and sets hit['_enrich'] metadata.
    """
    repo = repo or REPO_DEFAULT
    only_sources = only_sources or {"linkedin"}
    stats: dict[str, Any] = {
        "mode": "shallow",
        "candidates": 0,
        "attempted": 0,
        "ok": 0,
        "failed": 0,
        "skipped_cap": 0,
        "skipped_non_li": 0,
        "errors": [],
    }

    # collect indices to enrich
    to_do: list[int] = []
    for i, h in enumerate(hits):
        src = (h.get("source") or "").lower()
        url = h.get("url") or ""
        if src not in only_sources and not is_linkedin_url(url):
            stats["skipped_non_li"] += 1
            continue
        if not is_linkedin_url(url) and not extract_linkedin_job_id(url):
            stats["skipped_non_li"] += 1
            continue
        stats["candidates"] += 1
        if len(to_do) < max_jobs:
            to_do.append(i)
        else:
            stats["skipped_cap"] += 1

    for n, i in enumerate(to_do):
        h = hits[i]
        url = h.get("url") or ""
        stats["attempted"] += 1
        res = fetch_linkedin_detail(url, repo=repo, timeout=SHALLOW_TIMEOUT_S)
        if res.ok and res.description:
            teaser = res.description[:desc_chars]
            h["teaser"] = teaser
            h["_enrich"] = {
                "mode": "shallow",
                "ok": True,
                "job_id": res.job_id,
                "desc_len": len(res.description),
                "seniority": res.seniority,
                "employmentType": res.employment_type,
            }
            # optional fields for scorer context
            if res.seniority:
                h["soft_flags"] = (h.get("soft_flags") or "") + f"|seniority:{res.seniority}"
            stats["ok"] += 1
        else:
            h["_enrich"] = {"mode": "shallow", "ok": False, "error": res.error}
            stats["failed"] += 1
            stats["errors"].append({"url": url[:120], "error": res.error})
        if n + 1 < len(to_do) and sleep_s > 0:
            time.sleep(sleep_s)

    return stats


def enrich_one_deep(
    url_or_id: str,
    *,
    repo: Path | None = None,
) -> EnrichResult:
    """Full description fetch for deep CareerOps / package prep."""
    return fetch_linkedin_detail(
        url_or_id, repo=repo, timeout=DEEP_TIMEOUT_S
    )


def build_deep_teaser(res: EnrichResult, *, max_chars: int = DEEP_DESC_CHARS) -> str:
    parts = []
    meta = []
    if res.seniority:
        meta.append(f"Seniority: {res.seniority}")
    if res.employment_type:
        meta.append(f"Employment: {res.employment_type}")
    if res.job_function:
        meta.append(f"Function: {res.job_function}")
    if res.industries:
        meta.append(f"Industries: {res.industries}")
    if meta:
        parts.append(" | ".join(meta))
    if res.description:
        parts.append(res.description[:max_chars])
    return "\n\n".join(parts).strip()
