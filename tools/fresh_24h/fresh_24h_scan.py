#!/usr/bin/env python3
"""Config-driven fresh job scan → candidate CSV (+ optional tracker append).

Modes:
  daily  — last ~24h window (default)
  temp   — since last successful refresh (state file); user says「临时」

State:
  JobSearch_2026/02_Tracker/fresh_refresh_state.json

Runs installed portal CLIs (LinkedIn / JobsDB / CTgoodjobs), filters by recency,
applies hard/soft rules, dedupes against the apply tracker, and writes:

  JobSearch_2026/02_Tracker/fresh_24h_YYYY-MM-DD.csv
  JobSearch_2026/02_Tracker/fresh_24h_YYYY-MM-DD_run.json

Does NOT auto-apply. Default is dry-write candidates only; use --append-tracker
to append new rows to the main apply list with status 未做 / 待审.

Reporting policy (sheet): only CareerOps ≥ 3.0 when pushing via push_to_gsheet.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

REPO_DEFAULT = Path(__file__).resolve().parents[2]
if str(REPO_DEFAULT) not in sys.path:
    sys.path.insert(0, str(REPO_DEFAULT))

from tools.io_utils import atomic_write_json, atomic_write_stream
from tools.audit_log import append_audit_event
from tools.spreadsheet_safety import neutralize_spreadsheet_formula

# Local package helpers
sys.path.insert(0, str(Path(__file__).resolve().parent))
from refresh_state import (  # noqa: E402
    DEFAULT_STATE,
    hours_to_jobage,
    load_state,
    record_refresh,
    resolve_window,
    status_text,
)
from policy import PORTAL_SUBPROCESS_TIMEOUT_SECONDS  # noqa: E402


TRACKER_COLS = [
    "岗位编号",
    "层级",
    "匹配分",
    "职位",
    "公司",
    "赛道",
    "来源",
    "地点",
    "薪资",
    "链接",
    "简述",
    "语言要求",
    "领域背景",
    "资格要求",
    "经验要求",
    "匹配要点",
    "主要缺口",
    "发布日期",
    "简历版本",
    "版本说明",
    "材料状态",
    "工作时间风险",
    "映射理由",
    "CareerOps分数",
    "CareerOps等级",
    "CareerOps理由",
    "置信度",
]

CANDIDATE_COLS = [
    "scan_id",
    "decision",
    "title",
    "company",
    "source",
    "location",
    "salary",
    "url",
    "posted_at",
    "age_hours",
    "query_id",
    "track_hint",
    "soft_flags",
    "reject_reason",
    "teaser",
    "first_seen_at",
    "in_tracker",
]


@dataclass
class JobHit:
    id: str
    title: str
    company: str
    source: str
    location: str
    salary: str
    url: str
    posted_at: str | None
    teaser: str
    query_id: str
    track_hint: str
    age_hours: float | None = None
    decision: str = "new"  # new | reject | duplicate
    soft_flags: list[str] = field(default_factory=list)
    reject_reason: str = ""
    in_tracker: bool = False


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def has_fatal_portal_errors(errors: list[dict[str, Any]], new_count: int) -> bool:
    return bool(errors and new_count == 0)


def should_record_refresh(errors: list[dict[str, Any]], new_count: int) -> bool:
    """A failed scan must never consume the next temp-mode search window."""
    return not has_fatal_portal_errors(errors, new_count)


def today_hk_date() -> str:
    # Asia/Hong_Kong ≈ UTC+8; good enough without zoneinfo dependency edge cases
    return (now_utc() + timedelta(hours=8)).strftime("%Y-%m-%d")


def normalize_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    try:
        p = urlparse(u)
        # Drop tracking query params
        q = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_")
            and k.lower() not in {"refId", "trackingId", "eBP", "refId".lower()}
        ]
        # LinkedIn: keep path only up to job id when possible
        path = p.path.rstrip("/")
        clean = urlunparse((p.scheme, p.netloc.lower(), path, "", urlencode(q), ""))
        return clean
    except Exception:
        return u.split("?")[0].rstrip("/")


def company_title_key(company: str, title: str) -> str:
    c = re.sub(r"\s+", " ", (company or "").strip().lower())
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    return f"{c}||{t}"


def parse_posted(date_raw: Any) -> datetime | None:
    if date_raw is None or date_raw == "":
        return None
    s = str(date_raw).strip()
    # ISO with Z or offset
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        if re.search(r"[+-]\d{2}:\d{2}$", s):
            return datetime.fromisoformat(s)
    except ValueError:
        pass
    # 2026-07-27 / 2026-07-27T12:09:41 / 2026-07-24T11:45:00
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                # Date-only (LinkedIn): treat as start of that UTC day
                return dt.replace(tzinfo=timezone.utc)
            # Naive datetime (common on CTgoodjobs): interpret as Asia/Hong_Kong
            return (dt - timedelta(hours=8)).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def run_portal_search(
    repo: Path,
    cli_rel: str,
    query: str,
    *,
    portal: str,
    jobage: int,
    location: str | None,
    limit: int,
    timeout: int = PORTAL_SUBPROCESS_TIMEOUT_SECONDS,
) -> tuple[list[dict[str, Any]], str | None]:
    cli = repo / cli_rel
    if not cli.exists():
        return [], f"CLI missing: {cli_rel}"

    cmd = [
        "bun",
        "run",
        str(cli),
        "search",
        "-q",
        query,
        "--jobage",
        str(jobage),
        "--limit",
        str(limit),
        "--format",
        "json",
    ]
    if portal == "linkedin" and location:
        cmd.extend(["-l", location])

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return [], f"timeout after {timeout}s"
    except FileNotFoundError:
        return [], "bun not found on PATH"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        return [], f"exit {proc.returncode}: {err}"

    raw = (proc.stdout or "").strip()
    if not raw:
        return [], "empty stdout"

    # Some CLIs may print warnings before JSON — find first {
    start = raw.find("{")
    if start < 0:
        return [], f"no JSON in stdout: {raw[:200]}"
    try:
        payload = json.loads(raw[start:])
    except json.JSONDecodeError as e:
        return [], f"JSON decode error: {e}"

    results = payload.get("results") or []
    if not isinstance(results, list):
        return [], "results not a list"
    return results, None


def card_to_hit(
    card: dict[str, Any],
    *,
    source: str,
    query_id: str,
    track_hint: str,
) -> JobHit:
    url = normalize_url(str(card.get("url") or ""))
    jid = str(card.get("id") or "")
    title = str(card.get("title") or "").strip()
    company = str(card.get("company") or "").strip() or "—"
    location = str(card.get("location") or "").strip() or "Hong Kong"
    salary = str(card.get("salary") or "—").strip() or "—"
    teaser = str(card.get("teaser") or "").strip()
    posted_raw = card.get("date")
    posted_dt = parse_posted(posted_raw)
    posted_at = None
    if posted_dt:
        posted_at = posted_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif posted_raw:
        posted_at = str(posted_raw)

    return JobHit(
        id=jid,
        title=title,
        company=company,
        source=source,
        location=location,
        salary=salary,
        url=url,
        posted_at=posted_at,
        teaser=teaser[:400],
        query_id=query_id,
        track_hint=track_hint,
    )


def apply_recency(
    hit: JobHit,
    *,
    max_hours: float,
    portal: str,
    jobsdb_client_hours: float | None,
) -> None:
    """Mutate hit.age_hours / decision for recency."""
    dt = parse_posted(hit.posted_at) if hit.posted_at else None
    if dt:
        age = (now_utc() - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
        hit.age_hours = round(age, 2)
        limit = max_hours
        if portal == "jobsdb" and jobsdb_client_hours is not None:
            limit = jobsdb_client_hours
        if age > limit:
            hit.decision = "reject"
            hit.reject_reason = f"older_than_{limit:.0f}h (age={age:.1f}h)"
        return

    # No date: LinkedIn/CT already constrained by jobage=1 → accept with flag
    if portal in {"linkedin", "ctgoodjobs"}:
        hit.soft_flags.append("date_unknown_portal_jobage1")
        return
    # JobsDB without date after jobage=7: keep but flag (not true 24h)
    hit.soft_flags.append("date_unknown_jobsdb_le7d")
    hit.soft_flags.append("not_strict_24h")


def _contains_configured_keyword(text: str, keywords: list[str]) -> bool:
    lowered = (text or "").casefold()
    for raw in keywords:
        keyword = str(raw).strip().casefold()
        if not keyword:
            continue
        if re.search(r"[\u4e00-\u9fff]", keyword):
            if keyword in lowered:
                return True
            continue
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lowered):
            return True
    return False


def apply_rules(hit: JobHit, cfg: dict[str, Any]) -> None:
    if hit.decision == "reject":
        return
    text = f"{hit.title}\n{hit.teaser}"
    title = hit.title or ""

    for pat in cfg.get("noise_title_patterns") or []:
        if re.search(pat, title, re.I):
            hit.decision = "reject"
            hit.reject_reason = f"noise_title:{pat}"
            return

    relevance_keywords = [
        str(value)
        for value in (
            list(cfg.get("relevance_keywords") or [])
            + list(cfg.get("adjacent_keywords") or [])
        )
        if str(value).strip()
    ]
    if relevance_keywords and not _contains_configured_keyword(text, relevance_keywords):
        hit.decision = "reject"
        hit.reject_reason = "outside_configured_search_scope"
        return

    for pat in cfg.get("hard_reject_title_patterns") or []:
        if re.search(pat, text):
            hit.decision = "reject"
            hit.reject_reason = f"hard_reject:{pat}"
            return
    soft = cfg.get("soft_flag_patterns") or {}
    for name, pat in soft.items():
        if re.search(pat, text):
            hit.soft_flags.append(name)


def load_tracker_keys(tracker_path: Path) -> tuple[set[str], set[str], list[str], list[dict[str, str]]]:
    urls: set[str] = set()
    ct: set[str] = set()
    ids: list[str] = []
    rows: list[dict[str, str]] = []
    if not tracker_path.exists():
        return urls, ct, ids, rows
    with tracker_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            u = normalize_url(row.get("链接") or "")
            if u:
                urls.add(u)
            # also bare linkedin numeric
            m = re.search(r"/(\d{8,})(?:/|$)", u)
            if m:
                urls.add(m.group(1))
            ct.add(company_title_key(row.get("公司") or "", row.get("职位") or ""))
            if row.get("岗位编号"):
                ids.append(row["岗位编号"])
    return urls, ct, ids, rows


def next_scan_id(existing_ids: list[str], track: str, n: int) -> str:
    """Allocate N0-### style under track letter + 0 for 待审 fresh."""
    letter = (track or "F")[0].upper()
    prefix = f"{letter}0-"
    max_n = 0
    for i in existing_ids:
        m = re.match(rf"^{re.escape(letter)}0-(\d+)$", i or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
        # also generic N0-
    # Prefer F0 for general fresh if letter conflicts — use N for brand-new scan bucket
    # User IDs use A0-F2; use letter from track_hint with high numbers to avoid clash
    return f"{letter}0-{max_n + n:03d}"


def load_seen(seen_path: Path) -> dict[str, Any]:
    if not seen_path.exists():
        return {"seen": {}}
    try:
        return json.loads(seen_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"seen": {}}


def write_candidates_csv(path: Path, hits: list[JobHit]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    def write_rows(f):
        w = csv.DictWriter(f, fieldnames=CANDIDATE_COLS)
        w.writeheader()
        for i, h in enumerate(hits, 1):
            row = {
                    "scan_id": f"SCAN-{i:03d}",
                    "decision": h.decision,
                    "title": h.title,
                    "company": h.company,
                    "source": h.source,
                    "location": h.location,
                    "salary": h.salary,
                    "url": h.url,
                    "posted_at": h.posted_at or "",
                    "age_hours": h.age_hours if h.age_hours is not None else "",
                    "query_id": h.query_id,
                    "track_hint": h.track_hint,
                    "soft_flags": "|".join(h.soft_flags),
                    "reject_reason": h.reject_reason,
                    "teaser": h.teaser,
                    "first_seen_at": iso_now(),
                    "in_tracker": "yes" if h.in_tracker else "no",
                }
            w.writerow(
                {
                    key: neutralize_spreadsheet_formula(value)
                    for key, value in row.items()
                }
            )
    atomic_write_stream(path, write_rows, encoding="utf-8-sig", newline="")


def append_to_tracker(
    tracker_path: Path,
    new_hits: list[JobHit],
    existing_ids: list[str],
) -> list[dict[str, str]]:
    """Append only decision==new and not in_tracker. Returns written rows."""
    written: list[dict[str, str]] = []
    if not new_hits:
        return written

    # Read existing to preserve exact field order
    fieldnames = TRACKER_COLS
    existing_rows: list[dict[str, str]] = []
    if tracker_path.exists():
        with tracker_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                fieldnames = list(reader.fieldnames)
            existing_rows = list(reader)

    ids = list(existing_ids)
    # allocate per track letter counters
    counters: dict[str, int] = {}
    for i in ids:
        m = re.match(r"^([A-F])0-(\d+)$", i or "")
        if m:
            letter, num = m.group(1), int(m.group(2))
            counters[letter] = max(counters.get(letter, 0), num)

    for h in new_hits:
        letter = (h.track_hint or "F")[0].upper()
        if letter not in "ABCDEF":
            letter = "F"
        counters[letter] = counters.get(letter, 0) + 1
        jid = f"{letter}0-{counters[letter]:03d}"
        ids.append(jid)
        posted_day = ""
        if h.posted_at:
            posted_day = h.posted_at[:10]
        flags = ",".join(h.soft_flags)
        row = {c: "" for c in fieldnames}
        row.update(
            {
                "岗位编号": jid,
                "层级": "待审",
                "匹配分": "",
                "职位": h.title,
                "公司": h.company,
                "赛道": "fresh_24h",
                "来源": h.source,
                "地点": h.location,
                "薪资": h.salary if h.salary else "—",
                "链接": h.url,
                "简述": (h.teaser or "")[:300],
                "语言要求": "待从完整JD核对",
                "领域背景": "待评分",
                "资格要求": "待从完整JD核对",
                "经验要求": "待从完整JD核对",
                "匹配要点": f"fresh_24h scan; query={h.query_id}",
                "主要缺口": flags,
                "发布日期": posted_day,
                "简历版本": letter,
                "版本说明": "待映射",
                "材料状态": "未做",
                "工作时间风险": "未评估",
                "映射理由": f"auto-append fresh_24h {iso_now()}; flags={flags}",
                "CareerOps分数": "",
                "CareerOps等级": "",
                "CareerOps理由": "",
                "置信度": "低",
            }
        )
        existing_rows.append(row)
        written.append(row)

    def write_tracker(f):
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in existing_rows:
            w.writerow(
                {
                    key: neutralize_spreadsheet_formula(value)
                    for key, value in r.items()
                }
            )
    atomic_write_stream(
        tracker_path,
        write_tracker,
        encoding="utf-8-sig",
        newline="",
    )
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Scan HK portals for fresh jobs (daily 24h or temp since last refresh)"
    )
    ap.add_argument("--repo", type=Path, default=REPO_DEFAULT, help="ai-job-search repo root")
    ap.add_argument(
        "--tracker",
        type=Path,
        default=None,
        help="Main apply-list CSV (default: latest hk_apply_list_*.csv under 02_Tracker)",
    )
    ap.add_argument(
        "--queries",
        type=Path,
        default=None,
        help=(
            "queries.json path (default: private JobSearch_2026/00_Profile/queries.json "
            "after setup; tracked preset otherwise)"
        ),
    )
    ap.add_argument(
        "--mode",
        choices=["daily", "temp"],
        default="daily",
        help="daily=last ~24h; temp=since last refresh (临时)",
    )
    ap.add_argument(
        "--hours",
        type=float,
        default=None,
        help="Max age in hours (default: 24 for daily; for temp auto from last refresh)",
    )
    ap.add_argument(
        "--state",
        type=Path,
        default=None,
        help="Path to fresh_refresh_state.json",
    )
    ap.add_argument(
        "--no-record",
        action="store_true",
        help="Do not update last_refresh_at after this run",
    )
    ap.add_argument(
        "--show-state",
        action="store_true",
        help="Print refresh state and exit",
    )
    ap.add_argument("--limit-per-query", type=int, default=15, help="CLI --limit per query")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: JobSearch_2026/02_Tracker)",
    )
    ap.add_argument(
        "--skip-portal",
        action="append",
        default=[],
        help="Portal to skip (repeatable): linkedin|jobsdb|ctgoodjobs",
    )
    ap.add_argument(
        "--append-tracker",
        action="store_true",
        help="Append decision=new rows to main tracker (default: candidates CSV only)",
    )
    ap.add_argument(
        "--include-rejects",
        action="store_true",
        help="Also write rejected/duplicate rows into candidates CSV",
    )
    ap.add_argument(
        "--update-seen",
        action="store_true",
        help="Merge new URLs into job_scraper/seen_jobs.json",
    )
    ap.add_argument("--sleep", type=float, default=0.6, help="Seconds between CLI calls")
    args = ap.parse_args(argv)

    repo: Path = args.repo.resolve()
    state_path = (args.state or (repo / "JobSearch_2026" / "02_Tracker" / "fresh_refresh_state.json")).resolve()
    state = load_state(state_path)

    if args.show_state:
        print(status_text(state))
        print(f"  state_file: {state_path}")
        return 0

    window = resolve_window(mode=args.mode, hours_arg=args.hours, state=state)
    scan_hours = float(window["hours"])
    print(f"refresh mode={window['mode']} hours={scan_hours} source={window['source']}")
    print(f"  since={window['since']} until={window['until']}")
    print(f"  {status_text(state)}")

    private_queries = repo / "JobSearch_2026" / "00_Profile" / "queries.json"
    tracked_preset = Path(__file__).resolve().parent / "queries.json"
    qpath = (
        args.queries
        or (private_queries if private_queries.exists() else tracked_preset)
    ).resolve()
    cfg = json.loads(qpath.read_text(encoding="utf-8"))
    if cfg.get("setup_required") and not args.queries:
        print(
            "ERROR: no private search configuration. Run /setup or "
            "python3 setup.py --resume-folder /path/to/cv-folder first.",
            file=sys.stderr,
        )
        return 2

    tracker_dir = repo / "JobSearch_2026" / "02_Tracker"
    if args.tracker:
        tracker_path = args.tracker.resolve()
    else:
        candidates = sorted(tracker_dir.glob("hk_apply_list_*.csv"), reverse=True)
        if not candidates:
            print("ERROR: no hk_apply_list_*.csv found", file=sys.stderr)
            return 2
        tracker_path = candidates[0]

    out_dir = (args.out_dir or tracker_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    day = today_hk_date()
    cand_path = out_dir / f"fresh_24h_{day}.csv"
    run_path = out_dir / f"fresh_24h_{day}_run.json"

    skip = {s.lower() for s in args.skip_portal}
    portals_cfg = cfg.get("portals") or {}
    location = cfg.get("location_linkedin") or "Hong Kong"

    url_keys, ct_keys, existing_ids, _ = load_tracker_keys(tracker_path)

    all_hits: list[JobHit] = []
    errors: list[dict[str, str]] = []
    call_log: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_ct: set[str] = set()

    for q in cfg.get("queries") or []:
        qid = q.get("id") or "q"
        track_hint = q.get("track_hint") or "F"
        terms = q.get("terms") or {}

        for portal, pcfg in portals_cfg.items():
            if portal in skip or not pcfg.get("enabled", True):
                continue
            term = terms.get(portal)
            if portal == "freehire" and not term:
                term = terms.get("linkedin") or terms.get("jobsdb")
            if not term:
                continue
            # Portal jobage bucket from window; still client-filter to scan_hours
            jobage = hours_to_jobage(scan_hours, portal)
            cli_rel = pcfg["cli"]
            results, err = run_portal_search(
                repo,
                cli_rel,
                term,
                portal=portal,
                jobage=jobage,
                location=location if portal == "linkedin" else None,
                limit=args.limit_per_query,
            )
            call_log.append(
                {
                    "portal": portal,
                    "query_id": qid,
                    "term": term,
                    "jobage": jobage,
                    "count": len(results),
                    "error": err,
                    "ct_cookie_expired": bool(
                        err and portal == "ctgoodjobs" and ("400" in err or "sid" in err.lower())
                    ) if err else False,
                }
            )
            if err:
                err_info = {"portal": portal, "query_id": qid, "error": err}
                if portal == "ctgoodjobs" and ("400" in err or "sid" in err.lower()):
                    err_info["ct_cookie_expired"] = True
                    print(
                        f"[warn] {portal}/{qid}: CTgoodjobs cookie expired or invalid — "
                        f"set CTGOOD_SID + CTGOOD_VISITOR_ID env vars or delete them to trigger re-bootstrap",
                        file=sys.stderr,
                    )
                else:
                    print(f"[warn] {portal}/{qid}: {err}", file=sys.stderr)
                errors.append(err_info)
            for card in results:
                hit = card_to_hit(
                    card, source=portal, query_id=qid, track_hint=track_hint
                )
                if not hit.url and not hit.title:
                    continue
                # Client-side recency = resolved window (daily 24h or temp since last)
                client_h = pcfg.get("client_max_hours")
                jobsdb_h = float(scan_hours) if client_h is not None else None
                apply_recency(
                    hit,
                    max_hours=scan_hours,
                    portal=portal,
                    jobsdb_client_hours=jobsdb_h,
                )
                apply_rules(hit, cfg)

                # dedupe within run
                uk = hit.url or f"{hit.source}:{hit.id}"
                ck = company_title_key(hit.company, hit.title)
                if uk in seen_urls or (ck != "—||" and ck in seen_ct):
                    hit.decision = "duplicate"
                    hit.reject_reason = hit.reject_reason or "duplicate_in_run"
                else:
                    seen_urls.add(uk)
                    seen_ct.add(ck)

                # tracker dedupe
                bare = ""
                m = re.search(r"/(\d{8,})(?:/|$)", hit.url)
                if m:
                    bare = m.group(1)
                if hit.url in url_keys or bare in url_keys or ck in ct_keys:
                    hit.in_tracker = True
                    if hit.decision == "new":
                        hit.decision = "duplicate"
                        hit.reject_reason = "already_in_tracker"

                all_hits.append(hit)

            if args.sleep > 0:
                time.sleep(args.sleep)

    # Sort: new first, then by age
    def sort_key(h: JobHit) -> tuple:
        pri = {"new": 0, "duplicate": 1, "reject": 2}.get(h.decision, 9)
        age = h.age_hours if h.age_hours is not None else 9999
        return (pri, age, h.source, h.title)

    all_hits.sort(key=sort_key)

    to_write = [h for h in all_hits if h.decision == "new"]
    if args.include_rejects:
        write_candidates_csv(cand_path, all_hits)
    else:
        write_candidates_csv(cand_path, to_write)

    appended: list[dict[str, str]] = []
    if args.append_tracker:
        appended = append_to_tracker(tracker_path, to_write, existing_ids)

    if args.update_seen:
        seen_path = repo / "job_scraper" / "seen_jobs.json"
        blob = load_seen(seen_path)
        seen = blob.setdefault("seen", {})
        for h in to_write:
            key = h.url or f"{h.company}|{h.title}"
            if key not in seen:
                seen[key] = {
                    "title": h.title,
                    "company": h.company,
                    "url": h.url,
                    "first_seen": day,
                    "fit": "unscored",
                    "status": "new",
                    "source": h.source,
                    "scan": "fresh_24h",
                }
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(seen_path, blob)

    n_new = len(to_write)
    summary = {
        "ran_at": iso_now(),
        "day": day,
        "mode": window["mode"],
        "hours": scan_hours,
        "window": window,
        "tracker": str(tracker_path),
        "candidates_csv": str(cand_path),
        "state_file": str(state_path),
        "fatal_portal_errors": has_fatal_portal_errors(errors, n_new),
        "counts": {
            "fetched": len(all_hits),
            "new": sum(1 for h in all_hits if h.decision == "new"),
            "duplicate": sum(1 for h in all_hits if h.decision == "duplicate"),
            "reject": sum(1 for h in all_hits if h.decision == "reject"),
            "appended_to_tracker": len(appended),
        },
        "calls": call_log,
        "errors": errors,
        "new_jobs": [asdict(h) for h in to_write],
        "appended_ids": [r.get("岗位编号") for r in appended],
        "model_contract": {
            "mode": "deterministic",
            "next_action": (
                "abort_and_report_errors"
                if has_fatal_portal_errors(errors, n_new)
                else ("score_new_jobs" if n_new else "report_no_new_jobs")
            ),
            "must_report": [
                "window",
                "counts",
                "errors",
                "candidates_csv",
                "state_file",
            ],
            "do_not_infer": [
                "missing publication dates",
                "missing JD requirements",
                "portal success when an error is present",
            ],
        },
        "notes": [
            "JobsDB has no native 24h API; dated posts filtered client-side.",
            "mode=temp uses last_refresh_at from fresh_refresh_state.json.",
            "Sheet push policy: CareerOps >= 3.0 only (push_to_gsheet --min-score 3).",
            "Default does not auto-apply; review candidates before --append-tracker.",
        ],
    }
    atomic_write_json(run_path, summary)
    append_audit_event(
        repo / "JobSearch_2026",
        "scan_finished",
        {
            "mode": window["mode"],
            "new_count": n_new,
            "portal_error_count": len(errors),
            "fatal": bool(summary["fatal_portal_errors"]),
        },
    )

    if not args.no_record and should_record_refresh(errors, n_new):
        record_refresh(
            state,
            mode=window["mode"],
            window_hours=scan_hours,
            since=window.get("since"),
            new_count=n_new,
            candidates_csv=str(cand_path),
            sheet_title=f"fresh_24h_{day}",
            path=state_path,
        )
        print(f"  state:       recorded last_refresh_at → {state.get('last_refresh_at')}")
    elif args.no_record:
        print("  state:       not updated (--no-record)")
    else:
        print("  state:       not updated (scan failed; refresh window preserved)")

    print(f"fresh_24h scan complete — {day}")
    print(f"  mode:        {window['mode']} ({scan_hours}h)")
    print(f"  tracker:     {tracker_path.name}")
    print(f"  fetched:     {summary['counts']['fetched']}")
    print(f"  new:         {n_new}")
    print(f"  duplicate:   {summary['counts']['duplicate']}")
    print(f"  reject:      {summary['counts']['reject']}")
    print(f"  candidates:  {cand_path}")
    print(f"  run log:     {run_path}")
    if args.append_tracker:
        print(f"  appended:    {len(appended)} rows → {tracker_path.name}")
        for r in appended:
            print(f"    + {r.get('岗位编号')} | {r.get('公司')} | {r.get('职位')}")
    elif n_new:
        print("  (candidates only — re-run with --append-tracker to add to main list)")
    if errors:
        print(f"  portal errors: {len(errors)} (see run log)")

    if to_write:
        print("\n## New (not in tracker)")
        for i, h in enumerate(to_write, 1):
            age = f"{h.age_hours:.1f}h" if h.age_hours is not None else "?"
            flags = f" [{','.join(h.soft_flags)}]" if h.soft_flags else ""
            print(f"{i:2d}. [{h.source}] {h.title} @ {h.company} ({age}){flags}")
            print(f"    {h.url}")

    if has_fatal_portal_errors(errors, n_new):
        print(
            "FATAL: portal errors left no trustworthy new-job result — "
            "refresh cursor preserved",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
