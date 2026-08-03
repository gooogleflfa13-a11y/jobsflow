#!/usr/bin/env python3
"""Two-pass CareerOps for fresh/temp search results.

User product rule (JobSearch line):
  1) Scan latest jobs (temp/daily) — title + teaser only
  2) **Pass-1 score** — keep only score >= gate (default **3.3**)
  3) **Deep JD** only for gated jobs (LinkedIn CLI; JobsDB Playwright; **skip CT browser**)
  4) **Pass-2 score** on full(er) JD text
  5) Write scored CSV / rows for sheet — both scores visible
  6) Materials tailor is **NOT** here — only when user later makes a package

This is NOT an auto-trigger on every /scan without the configured threshold.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))

from careerops_quickscore import (  # noqa: E402
    SHEET_HEADERS,
    build_tracker_row,
    score_job,
)
from job_id import allocate_ids, max_prefix_from_ids  # noqa: E402
from linkedin_enrich import (  # noqa: E402
    DEEP_DESC_CHARS,
    DEEP_SLEEP_S,
    build_deep_teaser,
    enrich_one_deep,
    is_linkedin_url,
)
from tools.job_urls import normalize_job_url  # noqa: E402
from tools.fresh_24h.policy import DEFAULT_MAX_DEEP_FETCHES, SCORE_GATE  # noqa: E402
from tools.fresh_24h.tracker_schema import merge_tracker_headers  # noqa: E402
from tools.io_utils import atomic_write_json, atomic_write_stream, atomic_write_text  # noqa: E402

# JD full-text cache imports (imported inline in deep_enrich_hit to keep optional)

# Extra columns for two-pass visibility (appended after SHEET_HEADERS when writing local CSV)
PASS_EXTRA = [
    "初评分数",
    "初评等级",
    "初评理由",
    "深评分数",
    "深评等级",
    "深评理由",
    "JD深度",  # teaser | deep | paste_needed
]


def pending_semantic_rows(rows: list[dict]) -> list[dict]:
    """Return rows whose deep score still depends on pending semantic work.

    The score CSV remains useful as a preview, but formal push callers use
    this helper as a gate so a keyword fallback cannot silently become a
    tracker result.
    """
    pending = []
    for row in rows:
        try:
            count = int(str(row.get("语义待处理数") or "0"))
        except (TypeError, ValueError):
            count = 0
        if count > 0 or str(row.get("语义匹配来源") or "").strip() == "pending_fallback":
            pending.append(row)
    return pending


def pending_semantic_tasks(rows: list[dict]) -> list[str]:
    """Collect unique task identifiers for a user-facing push error."""
    tasks: list[str] = []
    for row in pending_semantic_rows(rows):
        for task in str(row.get("语义待处理任务") or "").split(";"):
            task = task.strip()
            if task and task not in tasks:
                tasks.append(task)
    return tasks


def hkt_day() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")


def latest_fresh_csv(tracker: Path) -> Path | None:
    files = sorted(tracker.glob("fresh_24h_????-??-??.csv"), reverse=True)
    files = [f for f in files if "_scored" not in f.name and "_run" not in f.name and "_twopass" not in f.name]
    return files[0] if files else None


def normalize_hit_url(h: dict) -> None:
    """Normalize job URL in-place; preserve original in url_raw if changed."""
    raw = h.get("url") or ""
    if not raw:
        return
    url = normalize_job_url(raw, source=h.get("source") or "")
    if url and url != raw:
        if not h.get("url_raw"):
            h["url_raw"] = raw
        h["url"] = url


def normalize_hits_urls(hits: list[dict]) -> None:
    for h in hits:
        normalize_hit_url(h)


def load_hits(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        return []
    if "职位" in fieldnames or "职位" in (rows[0] or {}):
        hits = []
        for r in rows:
            hits.append(
                {
                    "title": r.get("职位") or r.get("title") or "",
                    "company": r.get("公司") or r.get("company") or "",
                    "source": r.get("来源") or r.get("source") or "",
                    "location": r.get("地点") or r.get("location") or "",
                    "salary": r.get("薪资") or r.get("salary") or "—",
                    "url": r.get("链接") or r.get("url") or "",
                    "teaser": r.get("简述") or r.get("teaser") or "",
                    "posted_at": r.get("发布日期") or r.get("posted_at") or "",
                    "track_hint": r.get("简历版本") or r.get("track_hint") or "F",
                    "soft_flags": r.get("soft_flags") or "",
                }
            )
        normalize_hits_urls(hits)
        return hits
    if "decision" in fieldnames:
        rows = [r for r in rows if (r.get("decision") or "new").lower() == "new"]
    normalize_hits_urls(rows)
    return rows


def local_id_baseline(tracker: Path) -> dict[str, int]:
    """Max per-prefix job numbers from local tracker CSVs (no Google credentials)."""
    ids: list[str] = []
    apply_lists = sorted(tracker.glob("hk_apply_list_*.csv"), reverse=True)
    paths: list[Path] = []
    if apply_lists:
        paths.append(apply_lists[0])  # latest apply list only
    paths.extend(sorted(tracker.glob("fresh_24h_*_scored.csv")))
    paths.extend(sorted(tracker.glob("*_twopass_scored.csv")))
    seen: set[Path] = set()
    for p in paths:
        rp = p.resolve()
        if rp in seen or not p.is_file():
            continue
        seen.add(rp)
        try:
            with p.open(encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    jid = (r.get("岗位编号") or "").strip()
                    if jid:
                        ids.append(jid)
        except OSError:
            continue
    return max_prefix_from_ids(ids)


def local_id_map(tracker: Path) -> dict[str, str]:
    """Return canonical URL → existing job ID mappings from local trackers."""
    paths = []
    apply_lists = sorted(tracker.glob("hk_apply_list_*.csv"), reverse=True)
    if apply_lists:
        paths.append(apply_lists[0])
    paths.extend(sorted(tracker.glob("*_twopass_scored.csv"), reverse=True))
    paths.extend(sorted(tracker.glob("fresh_24h_*_scored.csv"), reverse=True))
    mapping: dict[str, str] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    jid = str(row.get("岗位编号") or "").strip()
                    url = str(row.get("链接") or row.get("url") or "").strip()
                    if not jid or not url:
                        continue
                    canonical = normalize_job_url(url, source=row.get("来源") or "") or url
                    mapping.setdefault(canonical, jid)
        except OSError:
            continue
    return mapping


def score_hit(
    h: dict,
    teaser: str,
    *,
    jd_depth: str = "teaser",
    repo: Path | None = None,
    jd_full: str | None = None,
):
    return score_job(
        title=h.get("title") or "",
        company=h.get("company") or "",
        teaser=teaser or "",
        source=h.get("source") or "",
        salary=h.get("salary") or "",
        track_hint=h.get("track_hint") or "F",
        soft_flags=h.get("soft_flags") or "",
        jd_depth=jd_depth,
        repo=repo,
        jd_url=h.get("url") or "",
        jd_full=jd_full,
        jd_cache_meta=h.get("_jd_cache_meta") if isinstance(h.get("_jd_cache_meta"), dict) else None,
    )


def _save_cache(url: str, text: str, *, source: str, repo: Path) -> dict[str, Any]:
    try:
        from jd_cache import save_jd_cache as _sv
        return _sv(url, text, source=source, root=repo)
    except (ImportError, OSError):
        return {}


def _load_cache(url: str, repo: Path) -> tuple[str | None, dict]:
    try:
        from jd_cache import load_jd_cache as _ld
        return _ld(url, repo)
    except ImportError:
        return None, {}


def deep_enrich_hit(h: dict, *, repo: Path, use_browser: bool = True) -> tuple[str, str]:
    """
    Return (text_for_pass2, depth_label).

    Order:
      1) URL-keyed JD cache (zero network requests)
      2) LinkedIn CLI detail when possible
      3) Playwright for **JobsDB only** (and LinkedIn if CLI failed)
      4) **CTgoodjobs: never open browser** — teaser only (saves compute; WAF often fails)
      5) teaser / paste_needed fallback

    URL should already be normalized early; re-normalize is idempotent.
    Set use_browser=False or env PORTAL_JD_BROWSER=0 to skip all browser deep.
    """
    normalize_hit_url(h)
    url = h.get("url") or ""
    portal_host = (url or "").lower()
    env_browser = os.environ.get("PORTAL_JD_BROWSER", "1").strip() not in {"0", "false", "no"}
    use_browser = bool(use_browser and env_browser)

    # The URL cache is the first and cheapest source for every portal.  This
    # must run before the CT browser policy so a user-pasted or previously
    # fetched full JD is still reusable without any new network request.
    cached_text, cached_meta = _load_cache(url, repo)
    if cached_text:
        h["_enrich"] = {
            "mode": "cache",
            "ok": True,
            "cache_key": cached_meta.get("cache_key"),
            "source": cached_meta.get("source", "cache"),
            "desc_len": len(cached_text),
        }
        h["_jd_cache_meta"] = {
            "url": url,
            "source": cached_meta.get("source", "cache"),
            "chars": len(cached_text),
            "cache_key": cached_meta.get("cache_key"),
            "mode": "cache",
        }
        h["_deep_jd_full"] = cached_text
        return cached_text[:DEEP_DESC_CHARS], "deep"

    # CT: never waste browser cycles — short teaser is enough for scoring.
    if "ctgoodjobs.hk" in portal_host:
        h["_enrich"] = {
            "mode": "ctgoodjobs_skip_browser",
            "ok": False,
            "note": "CT browser disabled by policy — teaser only; paste JD for materials if needed",
            "url": url,
        }
        return h.get("teaser") or "", "teaser"

    if is_linkedin_url(url):
        res = enrich_one_deep(url, repo=repo)
        if res.ok and res.description:
            text = build_deep_teaser(res, max_chars=DEEP_DESC_CHARS)
            h["_enrich"] = {
                "mode": "deep",
                "ok": True,
                "job_id": res.job_id,
                "desc_len": len(res.description),
            }
            h["_deep_jd_full"] = res.description
            cache_meta = _save_cache(url, res.description, source="linkedin_enrich", repo=repo)
            h["_jd_cache_meta"] = {
                "url": url,
                "source": "linkedin_enrich",
                "chars": len(res.description),
                "cache_key": cache_meta.get("cache_key") if isinstance(cache_meta, dict) else None,
                "mode": "fetched",
            }
            return text, "deep"
        h["_enrich"] = {"mode": "deep", "ok": False, "error": getattr(res, "error", None)}
        if not use_browser:
            return h.get("teaser") or "", "teaser_fallback"

    # Browser only for JobsDB (and LinkedIn CLI miss)
    needs_browser = use_browser and (
        "jobsdb.com" in portal_host
        or (is_linkedin_url(url) and not (h.get("_enrich") or {}).get("ok"))
    )
    if needs_browser:
        try:
            from portal_jd_browser import fetch_jd_body  # type: ignore
        except ImportError:
            try:
                from tools.fresh_24h.portal_jd_browser import fetch_jd_body  # type: ignore
            except ImportError as e:
                h["_enrich"] = {
                    "mode": "browser",
                    "ok": False,
                    "error": f"import: {e}",
                }
                return h.get("teaser") or "", "teaser"

        fres = fetch_jd_body(url, cache_root=repo)
        if fres.ok and fres.text:
            h["_enrich"] = {
                "mode": "browser",
                "ok": True,
                "portal": fres.portal,
                "selector": fres.selector,
                "desc_len": fres.chars,
                "attempts": fres.attempts,
                "retried": fres.retried,
                "last_reason": fres.last_reason,
            }
            h["teaser"] = fres.text[:3000]
            h["_deep_jd_full"] = fres.text
            cache_meta = _save_cache(url, fres.text, source=f"browser_{fres.portal}", repo=repo)
            h["_jd_cache_meta"] = {
                "url": url,
                "source": f"browser_{fres.portal}",
                "chars": len(fres.text),
                "cache_key": cache_meta.get("cache_key") if isinstance(cache_meta, dict) else None,
                "mode": "fetched",
            }
            return fres.text[:DEEP_DESC_CHARS], "deep"
        h["_enrich"] = {
            "mode": "browser",
            "ok": False,
            "portal": getattr(fres, "portal", None),
            "fail_reason": getattr(fres, "fail_reason", None),
            "attempts": getattr(fres, "attempts", None),
            "retried": getattr(fres, "retried", None),
            "last_reason": getattr(fres, "last_reason", None),
            "url": url,
        }
        return h.get("teaser") or "", "teaser_fallback"

    return h.get("teaser") or "", "teaser"


def run_two_pass(
    hits: list[dict],
    *,
    gate_pass1: float = SCORE_GATE,
    min_final: float | None = None,
    repo: Path = REPO,
    sleep_s: float = DEEP_SLEEP_S,
    max_deep: int = DEFAULT_MAX_DEEP_FETCHES,
    drop_below_final: bool = True,
) -> tuple[list[dict], dict]:
    """
    Returns (sheet_rows with two-pass fields, meta).
    Sheet CareerOps* columns = **pass-2 (deep)** scores.
    Extra keys on row: 初评*, 深评*, JD深度.
    By default, pass-2 below min_final are hard-dropped in accordance with
    docs/system_rules.md.
    """
    if min_final is None:
        min_final = gate_pass1

    # URL normalize before scoring/dedup (not only inside deep enrich)
    normalize_hits_urls(hits)

    meta: dict[str, Any] = {
        "gate_pass1": gate_pass1,
        "min_final": min_final,
        "drop_below_final": drop_below_final,
        "input": len(hits),
        "pass1_kept": 0,
        "pass1_dropped": 0,
        "deep_attempted": 0,
        "deep_ok": 0,
        "final_kept": 0,
        "dropped_final": [],
        "pass1_drop_samples": [],
        "semantic_pending_rows": 0,
        "semantic_pending_tasks": [],
    }

    gated: list[tuple[dict, Any]] = []
    for h in hits:
        # Pass 1 — teaser / card only (no deep fetch)
        teaser1 = h.get("teaser") or ""
        sc1 = score_hit(h, teaser1, repo=repo)
        h["_sc1"] = sc1
        if sc1.score < gate_pass1:
            meta["pass1_dropped"] += 1
            if len(meta["pass1_drop_samples"]) < 15:
                meta["pass1_drop_samples"].append(
                    {
                        "title": h.get("title"),
                        "company": h.get("company"),
                        "score": sc1.score,
                        "grade": sc1.grade,
                    }
                )
            continue
        meta["pass1_kept"] += 1
        gated.append((h, sc1))

    # Pass 2 — deep JD then rescore (cap deep calls)
    draft_rows: list[dict] = []
    deep_n = 0
    for h, sc1 in gated:
        teaser2 = h.get("teaser") or ""
        depth = "teaser"
        if deep_n < max_deep:
            meta["deep_attempted"] += 1
            text2, depth = deep_enrich_hit(h, repo=repo)
            if depth == "deep":
                meta["deep_ok"] += 1
                teaser2 = text2
                h["teaser"] = text2[:3000]  # keep for 简述 context
            deep_n += 1
            if sleep_s > 0 and deep_n < len(gated) and deep_n < max_deep:
                time.sleep(sleep_s)
        else:
            depth = "teaser_capped"

        # Only claim deep JD in reason/confidence when enrich actually returned deep text
        sc2 = score_hit(
            h,
            teaser2,
            jd_depth="deep" if depth == "deep" else "teaser",
            repo=repo,
            jd_full=h.get("_deep_jd_full") if depth == "deep" else None,
        )
        h["_sc2"] = sc2
        h["_jd_depth"] = depth

        below_final = sc2.score < min_final
        if below_final:
            meta["dropped_final"].append(
                {
                    "title": h.get("title"),
                    "company": h.get("company"),
                    "pass1": sc1.score,
                    "pass2": sc2.score,
                    "depth": depth,
                }
            )
            if drop_below_final:
                continue

        # Row uses pass-2 as CareerOps* (what you rank on in sheet)
        cells = build_tracker_row("TMP", 0, h, sc2)
        row = dict(zip(SHEET_HEADERS, cells))
        row["简历版本"] = sc2.resume_ver
        row["_deep_jd_full"] = h.get("_deep_jd_full", "")
        row["_deep_jd_url"] = h.get("url", "")
        row["CareerOps分数"] = f"{sc2.score:.2f}"
        row["CareerOps等级"] = sc2.grade
        row["CareerOps理由"] = sc2.reason
        row["初评分数"] = f"{sc1.score:.2f}"
        row["初评等级"] = sc1.grade
        row["初评理由"] = (sc1.reason or "")[:200]
        row["深评分数"] = f"{sc2.score:.2f}"
        row["深评等级"] = sc2.grade
        row["深评理由"] = (sc2.reason or "")[:200]
        row["JD深度"] = depth
        if below_final:
            row["_below_final"] = True
        else:
            meta["final_kept"] += 1
        if depth == "deep":
            conf = row.get("置信度") or sc2.confidence
            if conf in {"低", "中"}:
                row["置信度"] = "中高" if conf == "中" else "中"
        draft_rows.append(row)

    draft_rows.sort(
        key=lambda r: -float(r.get("深评分数") or r.get("CareerOps分数") or 0)
    )
    pending_rows = pending_semantic_rows(draft_rows)
    meta["semantic_pending_rows"] = len(pending_rows)
    meta["semantic_pending_tasks"] = pending_semantic_tasks(draft_rows)
    return draft_rows, meta


def write_csv(path: Path, rows: list[dict], *, repo: Path = REPO) -> None:
    headers = merge_tracker_headers(SHEET_HEADERS, repo, additional=PASS_EXTRA)
    # also keep any extra keys
    path.parent.mkdir(parents=True, exist_ok=True)
    def write_rows(f):
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({h: r.get(h, "") for h in headers})
    atomic_write_stream(path, write_rows, encoding="utf-8-sig", newline="")


def _persist_deep_jds(rows: list[dict], repo: Path) -> None:
    """Write deep JD text fetched during two-pass scoring to jds/{id}.md."""
    cache_dir = repo / "JobSearch_2026" / "02_Tracker" / "jds"
    cache_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        jd_full = r.pop("_deep_jd_full", "")
        if not jd_full:
            continue
        pid = (r.get("岗位编号") or "").strip()
        if not pid:
            continue
        url = (r.get("链接") or r.get("_deep_jd_url") or "").strip()
        header = f"# JD - {pid}\n\n"
        if url:
            header += f"- url: {url}\n"
        header += f"- source: two_pass_deep\n\n---\n\n"
        atomic_write_text(cache_dir / f"{pid}.md", header + jd_full.strip() + "\n")
        n += 1
    if n:
        print(f"JD cache: wrote {n} deep JD(s) to {cache_dir}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Two-pass score: gate 3.3 on teaser → deep JD → rescore → CSV"
    )
    ap.add_argument("--csv", type=Path, default=None, help="fresh_24h candidates CSV")
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument(
        "--gate",
        type=float,
        default=SCORE_GATE,
        help="Pass-1 minimum to fetch full JD (default 3.3; same as entry min)",
    )
    ap.add_argument(
        "--min-final",
        type=float,
        default=None,
        help="Pass-2 soft floor for final_kept / 待审 flag (default = same as --gate)",
    )
    ap.add_argument(
        "--keep-below-final",
        action="store_true",
        help="Diagnostic only: keep pass-2 scores below min_final and flag them",
    )
    ap.add_argument(
        "--max-deep",
        type=int,
        default=DEFAULT_MAX_DEEP_FETCHES,
        help="Maximum post-gate deep JD fetches",
    )
    ap.add_argument("--sleep", type=float, default=DEEP_SLEEP_S)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output scored CSV (default: *_twopass_scored.csv)",
    )
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    tracker = repo / "JobSearch_2026" / "02_Tracker"
    csv_path = args.csv.expanduser().resolve() if args.csv else latest_fresh_csv(tracker)
    if not csv_path or not csv_path.exists():
        print("ERROR: no fresh_24h CSV — run fresh_24h_scan first (temp/daily)", file=sys.stderr)
        return 2

    hits = load_hits(csv_path)
    print(f"two-pass: input={len(hits)} from {csv_path.name}")
    print(f"  gate_pass1={args.gate} (only these get deep JD)")
    print(f"  min_final={args.min_final if args.min_final is not None else args.gate}")
    print(
        f"  drop_below_final={not args.keep_below_final} "
        f"(default True per system rules)"
    )
    print(
        "  deep JD: LinkedIn CLI + JobsDB Playwright; "
        "CT=teaser only (no browser)"
    )
    print("  materials/tailor: NOT run here — only when you make a package")

    rows, meta = run_two_pass(
        hits,
        gate_pass1=args.gate,
        min_final=args.min_final,
        repo=repo,
        sleep_s=args.sleep,
        max_deep=args.max_deep,
        drop_below_final=not args.keep_below_final,
    )
    baseline = local_id_baseline(tracker)
    allocate_ids(rows, baseline_max=baseline, existing_ids=local_id_map(tracker))
    # After ID alloc (which sets 层级 from score), flag pass-2 soft drops for review
    for r in rows:
        if r.pop("_below_final", False):
            r["层级"] = "待审-深评偏低"
    _persist_deep_jds(rows, repo)

    out = args.out
    if out is None:
        stem = csv_path.stem
        out = csv_path.with_name(f"{stem}_twopass_scored.csv")
    else:
        out = out.expanduser().resolve()
    write_csv(out, rows, repo=repo)

    meta_path = out.with_suffix(".json")
    meta["baseline_max"] = baseline
    atomic_write_json(meta_path, meta)

    print(f"id baseline prefixes={len(baseline)} (local tracker; no gsheet)")
    print(f"pass1 kept={meta['pass1_kept']} dropped={meta['pass1_dropped']}")
    print(f"deep attempted={meta['deep_attempted']} ok={meta['deep_ok']}")
    n_below = len(meta["dropped_final"])
    print(
        f"final kept={meta['final_kept']} "
        f"pass2_below_min={n_below} (in_csv={args.keep_below_final}) → {out}"
    )
    if meta.get("semantic_pending_rows"):
        print(
            f"WARNING: semantic pending rows={meta['semantic_pending_rows']} "
            "— complete them and rerun before /push"
        )
    print(f"meta → {meta_path}")
    if meta["dropped_final"][:5]:
        print("sample pass2 below-min:", meta["dropped_final"][:5])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
