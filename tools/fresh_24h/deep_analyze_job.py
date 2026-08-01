#!/usr/bin/env python3
"""Deep CareerOps analysis with LinkedIn full JD (user-requested 深度分析).

Use when the user asks for thorough evaluation of one (or a few) jobs —
not for bulk scan. Fetches LinkedIn `detail` full description, then scores
with CareerOps and writes a markdown brief under 02_Tracker.

Usage:
  python3 tools/fresh_24h/deep_analyze_job.py https://hk.linkedin.com/jobs/view/...
  python3 tools/fresh_24h/deep_analyze_job.py 4445487535
  python3 tools/fresh_24h/deep_analyze_job.py URL --title "Legal Counsel" --company BingX
  python3 tools/fresh_24h/deep_analyze_job.py URL --no-write   # stdout only

SYSTEM RULE: JobSearch_2026/03_Applications/系统规则_PDF与检索_强制遵守.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from careerops_quickscore import score_job  # noqa: E402
from linkedin_enrich import (  # noqa: E402
    build_deep_teaser,
    enrich_one_deep,
    extract_linkedin_job_id,
)


def hkt_stamp() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d_%H%M")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Deep LinkedIn JD + CareerOps analysis")
    ap.add_argument("url_or_id", help="LinkedIn job URL or numeric id")
    ap.add_argument("--title", default="", help="Override title if known")
    ap.add_argument("--company", default="", help="Override company if known")
    ap.add_argument("--location", default="Hong Kong")
    ap.add_argument("--track-hint", default="B", help="A-G track hint for scorer")
    ap.add_argument("--salary", default="")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: JobSearch_2026/02_Tracker/deep_analysis/",
    )
    ap.add_argument("--no-write", action="store_true", help="Print only, no markdown file")
    ap.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    print(f"deep analyze: fetching LinkedIn detail for {args.url_or_id} …")
    res = enrich_one_deep(args.url_or_id, repo=repo)
    if not res.ok:
        print(f"ERROR: detail failed: {res.error}", file=sys.stderr)
        # still try score on title if provided
        if not args.title:
            return 1

    title = args.title or (res.raw.get("title") if res.raw else "") or "(unknown title)"
    company = args.company or (res.raw.get("company") if res.raw else "") or "—"
    location = args.location or (res.raw.get("location") if res.raw else "") or "Hong Kong"
    url = (res.raw.get("url") if res.raw else None) or (
        f"https://www.linkedin.com/jobs/view/{res.job_id}" if res.job_id else args.url_or_id
    )

    teaser = build_deep_teaser(res) if res.ok else ""
    if not teaser and args.title:
        teaser = f"(detail failed: {res.error})"

    sc = score_job(
        title=title,
        company=company,
        teaser=teaser,
        source="linkedin",
        salary=args.salary or "",
        track_hint=args.track_hint,
        soft_flags="",
        jd_depth="deep" if res.ok else "teaser_fallback",
        repo=repo,
    )

    jid = res.job_id or extract_linkedin_job_id(args.url_or_id) or "unknown"
    print()
    print("=== DEEP CareerOps ===")
    print(f"Job: {title} @ {company}")
    print(f"URL: {url}")
    print(f"Detail: ok={res.ok} desc_len={len(res.description)} id={jid}")
    if res.seniority:
        print(f"Seniority: {res.seniority}")
    if res.employment_type:
        print(f"Employment: {res.employment_type}")
    print(f"Score: {sc.score:.2f} / {sc.grade} | tier={sc.tier} | resume={sc.resume_ver}")
    print(f"Match points: {sc.match_points} | confidence: {sc.confidence}")
    print(f"Brief: {sc.brief}")
    print(f"Reason: {sc.reason}")
    print(f"Match key: {sc.match_key}")
    print(f"Gaps: {sc.gaps}")
    print()

    if args.no_write:
        if res.description:
            print("--- JD (truncated) ---")
            print(res.description[:2000])
            if len(res.description) > 2000:
                print(f"\n… [{len(res.description) - 2000} more chars]")
        return 0

    out_dir = (
        args.out_dir
        if args.out_dir
        else repo / "JobSearch_2026" / "02_Tracker" / "deep_analysis"
    )
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_co = "".join(c if c.isalnum() or c in "-_" else "_" for c in company)[:40]
    path = out_dir / f"deep_{hkt_stamp()}_{jid}_{safe_co}.md"

    md = f"""# Deep analysis — {title} @ {company}

- **When (HKT):** {(datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")}
- **URL:** {url}
- **LinkedIn job id:** {jid}
- **Detail fetch:** {"OK" if res.ok else f"FAILED ({res.error})"}
- **Description length:** {len(res.description)} chars
- **Seniority:** {res.seniority or "—"}
- **Employment:** {res.employment_type or "—"}
- **Function:** {res.job_function or "—"}
- **Industries:** {res.industries or "—"}

## CareerOps (deep / full-JD teaser)

| Field | Value |
|-------|-------|
| Score | **{sc.score:.2f}** |
| Grade | **{sc.grade}** |
| Tier | {sc.tier} |
| Resume version | {sc.resume_ver} ({sc.resume_note}) |
| Match points | {sc.match_points} |
| Confidence | {sc.confidence} |

**Brief:** {sc.brief}

**Reason:** {sc.reason}

**Match key:** {sc.match_key}

**Gaps:** {sc.gaps}

**Work-time risk:** {sc.work_time_risk}

## Full job description

{res.description or "_(no description retrieved)_"}

## Notes

- Deep mode uses LinkedIn `detail` HTML (expanded markup), not the collapsed search card.
- For package building, re-read this file or re-run detail; do not invent facts beyond JD + profile handbook.
"""
    path.write_text(md, encoding="utf-8")
    # also json sidecar for agents
    side = path.with_suffix(".json")
    side.write_text(
        json.dumps(
            {
                "url": url,
                "job_id": jid,
                "title": title,
                "company": company,
                "location": location,
                "detail_ok": res.ok,
                "description": res.description,
                "seniority": res.seniority,
                "employment_type": res.employment_type,
                "score": sc.score,
                "grade": sc.grade,
                "tier": sc.tier,
                "resume_ver": sc.resume_ver,
                "reason": sc.reason,
                "brief": sc.brief,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote: {path}")
    print(f"Wrote: {side}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
