#!/usr/bin/env python3
"""
JobSearch_2026 materials pipeline CLI.

Honest scope:
  - Scan two-pass (fresh_24h) is SEPARATE; this module never auto-runs on /scan.
  - Deep full JD is reliable mainly for LinkedIn; CT/JobsDB need paste (`jd set`).
  - tailor reorders from fact-checked A–F base; does NOT re-fact-check;
    plan is emphasis (skills/bullets order), not freestyle invent.

Stages:
  A) Read CV / masters → A–F bases with FACT-CHECK
  B) See full JD (URL normalize + LinkedIn deep + paste)
  C) Tailor from passed base toward JD (no re-fact-check)

Usage examples:
  python3 -m tools.job_materials base sync
  python3 -m tools.job_materials base factcheck --lane C
  python3 -m tools.job_materials base list

  python3 -m tools.job_materials url normalize --url 'https://jobs.example/job/123'

  python3 -m tools.job_materials jd set --package 'JobSearch_2026/01_Masters/A_track/核心/A0-005_未投_Example' --file ./jd.txt
  python3 -m tools.job_materials enrich --package '...'

  python3 -m tools.job_materials tailor --package '...' --lane C
  python3 -m tools.job_materials pipeline --package '...' --lane C
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# allow `python3 -m tools.job_materials` from repo root
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.job_materials.bases import (  # noqa: E402
    factcheck_base,
    list_bases,
    load_base,
    pick_lane_from_text,
    save_base,
    sync_base_from_masters,
)
from tools.job_materials.enrich import enrich_package, normalize_url_in_snapshot  # noqa: E402
from tools.job_materials.company_research import (  # noqa: E402
    load_company_research,
    save_company_research,
    write_company_research_request,
)
from tools.job_materials.jd_store import (  # noqa: E402
    extract_url_from_snapshot,
    jd_meta,
    package_id_from_path,
    read_jd,
    write_jd,
)
from tools.job_materials.paths import LANES, jobsearch_root  # noqa: E402
from tools.job_materials.packages import resolve_package  # noqa: E402
from tools.job_materials.tailor import (  # noqa: E402
    build_tailored_payload,
    package_quality_exit_code,
    write_base_master_ref,
    write_materials_status,
    write_tailor_outputs,
)
from tools.job_materials.url_normalize import normalize_job_url  # noqa: E402
from tools.job_materials.resume_parse import (  # noqa: E402
    load_resume_meta,
    load_resume_text,
    save_parsed_resume,
)
from tools.job_materials.requirements_engine import (  # noqa: E402
    build_application_preflight,
    load_preflight_answers,
    save_preflight_answer,
    write_application_preflight,
)
from tools.audit_log import append_audit_event  # noqa: E402


def _pkg(path: str | None, *, job_id: str | None = None) -> Path | None:
    """Resolve --package path or create a package from a local tracker row."""
    if path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p
    if job_id:
        masters_root = (jobsearch_root() / "01_Masters").resolve()
        try:
            package = resolve_package(jobsearch_root(), job_id)
        except LookupError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            print(
                "Run /push --local-only (or --also-local) and append the selected "
                "row to a local tracker before /materials.",
                file=sys.stderr,
            )
            return None
        try:
            package.resolve().relative_to(masters_root)
        except ValueError:
            print(
                f"ERROR: package resolution escaped 01_Masters: {package}",
                file=sys.stderr,
            )
            return None
        return package.resolve()
    return None


def _parse_title_company(package: Path) -> tuple[str, str]:
    snap = package / "job_snapshot.md"
    title, company = package.name, ""
    if snap.exists():
        text = snap.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"Role:\s*(.+)", text)
        if m:
            title = m.group(1).strip()
        m = re.search(r"Company:\s*(.+)", text)
        if m:
            company = m.group(1).strip()
        # fallback header: # C0-005 — Compliance … @ Gate
        m = re.search(r"^#\s+.+?—\s+(.+?)\s+@\s+(.+)$", text, re.M)
        if m:
            title = title if title != package.name else m.group(1).strip()
            company = company or m.group(2).strip()
    return title, company


def _known_application_answers(package: Path) -> dict[str, str]:
    known = {}
    config_paths = [
        jobsearch_root() / "00_Profile" / "config.personal.json",
        REPO / "config.personal.json",
    ]
    for config_path in config_paths:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        for key in (
            "current_salary",
            "expected_salary",
            "notice_period",
            "availability",
            "work_authorization",
            "language",
            "license",
            "experience_years",
        ):
            if config.get(key):
                known[key] = str(config[key])
        break
    known.update(
        {
            key: str(value)
            for key, value in load_preflight_answers(package).items()
            if str(value).strip()
        }
    )
    return known


def _print_pdf_next_steps(package: Path) -> None:
    print("")
    print("== next (PDF export — after you edit DOCX from master) ==")
    print(f"  python3 tools/fresh_24h/docx_to_pdf.py '{package}/<CV>.docx' --engine libreoffice")
    print(f"  python3 tools/fresh_24h/docx_to_pdf.py '{package}/<Cover Letter>.docx' --engine libreoffice")
    print("  Handbook: JobSearch_2026/03_Applications/二级及部分一级岗位定制材料技术手册_2026-07-28.md")
    print("  Rules:    JobSearch_2026/03_Applications/系统规则_PDF与检索_强制遵守.md")


def cmd_base(args: argparse.Namespace) -> int:
    root = jobsearch_root()
    if args.action == "list":
        for b in list_bases(root):
            fc = (b.get("factcheck") or {}).get("status") or "?"
            print(f"  {b.get('base_id')}  factcheck={fc:8}  {b.get('label')}  emp={','.join(b.get('emphasis') or [])}")
        return 0

    if args.action == "sync":
        lanes = [args.lane.upper()] if args.lane else list(LANES.keys())
        for lane in lanes:
            base = sync_base_from_masters(root, lane)
            base = factcheck_base(root, base)
            p = save_base(root, base)
            print(f"{lane}: factcheck={base['factcheck']['status']} bullets={len(base.get('bullets') or [])} → {p}")
            if base["factcheck"]["status"] != "passed":
                for c in base["factcheck"].get("claims") or []:
                    if not c.get("supported"):
                        print(f"  ✗ {str(c.get('text'))[:100]}")
        return 0

    if args.action == "factcheck":
        if not args.lane:
            print("need --lane A-F", file=sys.stderr)
            return 2
        base = load_base(root, args.lane) or sync_base_from_masters(root, args.lane)
        base = factcheck_base(root, base)
        p = save_base(root, base)
        print(f"factcheck={base['factcheck']['status']} → {p}")
        for c in base["factcheck"].get("claims") or []:
            mark = "✓" if c.get("supported") else "✗"
            print(f"  {mark} [{c.get('kind')}] {str(c.get('text'))[:100]}")
        return 0 if base["factcheck"]["status"] == "passed" else 1

    if args.action == "show":
        if not args.lane:
            print("need --lane", file=sys.stderr)
            return 2
        base = load_base(root, args.lane)
        if not base:
            print("missing — run base sync", file=sys.stderr)
            return 1
        print(json.dumps(base, ensure_ascii=False, indent=2))
        return 0
    return 0


def cmd_url(args: argparse.Namespace) -> int:
    if args.action == "normalize":
        print(normalize_job_url(args.url or "", source=args.source or ""))
        return 0
    return 0


def cmd_jd(args: argparse.Namespace) -> int:
    root = jobsearch_root()
    package = _pkg(args.package, job_id=getattr(args, "job_id", None))
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2

    if args.action == "set":
        if args.file:
            text = Path(args.file).expanduser().read_text(encoding="utf-8")
        else:
            print("Paste full JD, end with Ctrl-D:")
            text = sys.stdin.read()
        if len(text.strip()) < 40:
            print("JD too short", file=sys.stderr)
            return 1
        url = extract_url_from_snapshot(package)
        path = write_jd(root, package, text, url=url, source="user_paste")
        # also normalize URLs in snapshot
        for c in normalize_url_in_snapshot(package):
            print(f"  · {c}")
        print(f"Wrote {path} ({len(text.strip())} chars) id={package_id_from_path(package)}")
        return 0

    if args.action == "show":
        print(read_jd(package, root) or "(empty)")
        return 0
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    root = jobsearch_root()
    package = _pkg(args.package)
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2
    notes = enrich_package(package, root)
    for n in notes:
        print(f"  · {n}")
    meta = jd_meta(package, root)
    print(f"jd depth={meta.get('depth')} chars={meta.get('chars')} source={meta.get('source')}")
    if meta.get("is_shallow"):
        print(
            "Note: JD still shallow/stub — for CT/JobsDB paste is required for materials quality.",
            file=sys.stderr,
        )
        return 2
    return 0


def cmd_tailor(args: argparse.Namespace) -> int:
    root = jobsearch_root()
    package = _pkg(args.package)
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2
    title, company = _parse_title_company(package)
    lane = (args.lane or "").upper()
    if not lane:
        lane = pick_lane_from_text(title, read_jd(package, root)[:500])
        print(f"auto lane={lane}")

    base = load_base(root, lane)
    if not base:
        print(f"base {lane} missing — running sync+factcheck…")
        base = sync_base_from_masters(root, lane)
        base = factcheck_base(root, base)
        save_base(root, base)

    fc = (base.get("factcheck") or {}).get("status")
    if fc != "passed" and not args.allow_unchecked:
        print(
            f"BASE {lane} factcheck={fc}. Fix evidence or: base factcheck --lane {lane}\n"
            f"Or pass --allow-unchecked (not recommended).",
            file=sys.stderr,
        )
        return 1

    jd = read_jd(package, root)
    if len(jd) < 80 and not args.allow_shallow_jd:
        print(
            "JD too short. Run: enrich --package …  OR  jd set --package … --file jd.txt\n"
            "(Deep full JD reliable mainly for LinkedIn; CT/JobsDB → paste.)",
            file=sys.stderr,
        )
        return 2

    preflight = build_application_preflight(
        jd,
        known_answers=_known_application_answers(package),
    )
    write_application_preflight(package, preflight)
    research = load_company_research(
        package,
        root=root,
        company=company or "",
    )
    if not (research.get("quality") or {}).get("ready_for_tailoring"):
        request_path = write_company_research_request(
            package,
            company=company or "",
            role=title,
            jd_text=jd,
        )
        print(f"Wrote {request_path} -> complete sourced company quick research")
    payload = build_tailored_payload(
        base=base,
        job_title=title,
        company=company or "Company",
        jd_text=jd,
        company_research=research,
        use_llm=bool(args.llm),
    )
    payload["application_preflight"] = {
        "ready_for_apply": preflight["ready_for_apply"],
        "next_action": preflight["next_action"],
        "question_ids": [item["id"] for item in preflight["questions"]],
        "review_ids": [item["id"] for item in preflight["review_items"]],
    }
    write_tailor_outputs(package, payload)
    ref = write_base_master_ref(package, lane, root)
    if ref:
        print(f"Wrote {ref}")
    cov = payload.get("jd_coverage") or {}
    print(f"base={payload.get('base_id')} factcheck={fc} mode={payload.get('mode')}")
    print(f"coverage hit_rate={cov.get('hit_rate')} hits={cov.get('hits')[:6]}")
    print(f"Wrote {package / 'tailor_plan.md'}")
    print(f"Wrote {package / 'tailor_plan.json'}")
    print(
        "Tailor = emphasis reorder from fact-checked base (no re-fact-check; no freestyle invent)."
    )
    print("Next: apply summary/bullets into CV/CL DOCX per 二级手册, then PDF export.")
    _print_pdf_next_steps(package)

    # When plan exists, surface quality issues for agents (unless pure tailor strict path already returned)
    code = package_quality_exit_code(payload, package, root)
    quality_gate = payload.get("quality_gate") or {}
    if quality_gate and not quality_gate.get("ready_for_drafting", True):
        code = code or 4
    if code and args.allow_shallow_jd:
        # still wrote plan; non-zero so agents notice
        meta = jd_meta(package, root)
        print(
            f"WARN exit={code}: factcheck={fc} jd_depth={meta.get('depth')} "
            f"(tailor_plan written; fix blockers before sending materials)",
            file=sys.stderr,
        )
    return code if args.allow_shallow_jd or args.allow_unchecked or code == 4 else 0


def cmd_preflight(args: argparse.Namespace) -> int:
    root = jobsearch_root()
    package = _pkg(args.package, job_id=getattr(args, "job_id", None))
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2
    if args.action == "answer":
        if not args.field or not args.value:
            print("preflight answer needs --field and --value", file=sys.stderr)
            return 2
        path = save_preflight_answer(package, args.field, args.value)
        print(f"Wrote {path}")
    jd = read_jd(package, root)
    value = build_application_preflight(
        jd,
        known_answers=_known_application_answers(package),
    )
    write_application_preflight(package, value)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0 if value["ready_for_apply"] else 4


def cmd_company(args: argparse.Namespace) -> int:
    package = _pkg(args.package, job_id=getattr(args, "job_id", None))
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2
    if args.action == "show":
        _, company = _parse_title_company(package)
        print(
            json.dumps(
                load_company_research(
                    package,
                    root=jobsearch_root(),
                    company=company,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not args.file:
        print("need --file company_research.json", file=sys.stderr)
        return 2
    try:
        value = json.loads(Path(args.file).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"invalid company research JSON: {exc}", file=sys.stderr)
        return 2
    saved = save_company_research(package, value, root=jobsearch_root())
    print(
        f"Wrote {package / 'company_research.json'} "
        f"({len(saved.get('verified_signals') or [])} sourced signals)"
    )
    print(f"Wrote {package / 'company_research.md'}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """PDF → plain text (apply-bot style graft)."""
    root = jobsearch_root()
    if args.action == "parse":
        if not args.pdf:
            print("need --pdf path/to/CV.pdf", file=sys.stderr)
            return 2
        meta = save_parsed_resume(Path(args.pdf), root=root, also_copy_bullets=True)
        print(
            f"OK source={meta.get('sourceName')} chars={meta.get('textLength')} "
            f"→ {root / '00_Profile' / 'resume_runtime' / 'resume.txt'}"
        )
        return 0
    if args.action == "show":
        meta = load_resume_meta(root)
        if not meta:
            print("(no parsed resume — run: resume parse --pdf …)")
            return 1
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        text = load_resume_text(root)
        print("--- text preview ---")
        print(text[:1500] + ("…" if len(text) > 1500 else ""))
        return 0
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    """
    Package step: enrich → tailor → materials_status + master ref.
    Does NOT invent facts. Exit non-zero if base factcheck failed or JD stub/shallow
    (plan is still written so humans can see blockers).
    """
    root = jobsearch_root()
    package = _pkg(args.package, job_id=args.job_id)
    if package is None or not package.is_dir():
        print(f"not a package dir: {package}", file=sys.stderr)
        return 2
    args.package = str(package)

    print("== normalize + enrich ==")
    print("  (LinkedIn deep OK; CT/JobsDB → URL fix / structured only — paste for full body)")
    enrich_notes = enrich_package(package, root)
    for n in enrich_notes:
        print(f"  · {n}")
    meta = jd_meta(package, root)
    print(f"  jd depth={meta.get('depth')} chars={meta.get('chars')} source={meta.get('source')}")

    # Always produce plan for agent visibility; quality reflected in exit code
    args.allow_shallow_jd = True
    print("== tailor (emphasis from A–F base; no re-fact-check) ==")
    title, company = _parse_title_company(package)
    lane = (args.lane or "").upper()
    if not lane:
        lane = pick_lane_from_text(title, read_jd(package, root)[:500])
        print(f"auto lane={lane}")
        args.lane = lane

    # Run tailor body (may return early if factcheck hard-fail without allow_unchecked)
    rc_tailor = cmd_tailor(args)

    # materials_status after plan exists (if tailor wrote it)
    plan = package / "tailor_plan.json"
    if plan.exists():
        try:
            payload = json.loads(plan.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {
                "role": title,
                "company": company,
                "base_id": lane,
                "base_factcheck": "?",
                "mode": "unknown",
                "jd_shallow": True,
                "jd_coverage": {},
            }
        write_base_master_ref(package, lane or str(payload.get("base_id") or "F"), root)
        status = write_materials_status(
            package,
            root=root,
            payload=payload,
            lane=lane or str(payload.get("base_id") or "F"),
            enrich_notes=enrich_notes,
        )
        print(f"Wrote {status}")
        append_audit_event(
            root,
            "materials_pipeline",
            {
                "job_id": package_id_from_path(package),
                "base_id": payload.get("base_id"),
                "company_research_sources": len(
                    (payload.get("company_profile") or {}).get("verified_signals") or []
                ),
                "differentiation_fingerprint": payload.get(
                    "differentiation_fingerprint"
                ),
            },
        )
        code = package_quality_exit_code(payload, package, root)
        quality_gate = payload.get("quality_gate") or {}
        if quality_gate and not quality_gate.get("ready_for_drafting", True):
            code = code or 4
        preflight = payload.get("application_preflight") or {}
        if not preflight.get("ready_for_apply", True):
            code = code or 4
        # Prefer quality code over tailor early-exit if plan exists
        if code:
            print(
                f"PIPELINE WARN exit={code}: check materials_status.md "
                f"(factcheck and/or JD depth). Plan written for review.",
                file=sys.stderr,
            )
            return code
        print("pipeline ok — review tailor_plan.md + materials_status.md")
        return 0

    # no plan (e.g. hard factcheck fail without --allow-unchecked)
    print("pipeline incomplete — no tailor_plan.json", file=sys.stderr)
    return int(rc_tailor or 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="job_materials",
        description=(
            "JobSearch_2026 materials (on-demand only). "
            "Separate from scan two-pass. "
            "JD body: LinkedIn CLI + Playwright browser (JobsDB/CT); paste fallback. "
            "tailor = emphasis from fact-checked A–F base (no re-fact-check)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Notes:\n"
            "  • Never auto-runs on /scan / push_to_gsheet / temp_two_pass.\n"
            "  • pipeline writes tailor_plan + materials_status + base_master_ref;\n"
            "    exit ≠ 0 if base factcheck failed or JD stub/shallow.\n"
            "  • PDF export is manual: docx_to_pdf (LibreOffice headless).\n"
            "  • resume parse grafts apply-bot PDF→text into 00_Profile/resume_runtime/.\n"
        ),
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("resume", help="Parse CV PDF → plain text (apply-bot style)")
    pr_sub = pr.add_subparsers(dest="action", required=True)
    pr_parse = pr_sub.add_parser("parse", help="Parse a PDF resume")
    pr_parse.add_argument("--pdf", required=True, help="Path to CV PDF")
    pr_parse.set_defaults(func=cmd_resume)
    pr_show = pr_sub.add_parser("show", help="Show parsed resume meta + preview")
    pr_show.set_defaults(func=cmd_resume)

    p = sub.add_parser("base", help="A–F bases sync/factcheck (required before trustworthy tailor)")
    p.add_argument("action", choices=["list", "sync", "factcheck", "show"])
    p.add_argument("--lane", default="", help="A-F")
    p.set_defaults(func=cmd_base)

    p = sub.add_parser("url", help="URL helpers (CT / JobsDB / LinkedIn canonicalize)")
    p.add_argument("action", choices=["normalize"])
    p.add_argument("--url", default="")
    p.add_argument("--source", default="")
    p.set_defaults(func=cmd_url)

    p = sub.add_parser(
        "jd",
        help="Full JD paste/store (required for CT/JobsDB; LinkedIn often via enrich)",
    )
    p.add_argument("action", choices=["set", "show"])
    p.add_argument("--package", default=None, help="Path to package folder (or use --job-id)")
    p.add_argument("--job-id", default=None, help="Job ID resolved from the local tracker")
    p.add_argument("--file", default="")
    p.set_defaults(func=cmd_jd)

    p = sub.add_parser(
        "enrich",
        help="Normalize URLs + LinkedIn deep JD; CT/JobsDB = URL fix / structured only",
    )
    p.add_argument("--package", default=None, help="Package path (or use --job-id)")
    p.set_defaults(func=cmd_enrich)

    p = sub.add_parser(
        "company",
        help="Store/show source-aware company research used by CV/cover-letter tailoring",
    )
    p.add_argument("action", choices=["set", "show"])
    p.add_argument("--package", default=None, help="Package path (or use --job-id)")
    p.add_argument("--job-id", default=None)
    p.add_argument("--file", default="", help="Research JSON for `company set`")
    p.set_defaults(func=cmd_company)

    p = sub.add_parser(
        "preflight",
        help="Deterministically surface JD questions and hard requirements",
    )
    p.add_argument("action", choices=["show", "refresh", "answer"])
    p.add_argument("--package", default=None, help="Package path (or use --job-id)")
    p.add_argument("--job-id", default=None)
    p.add_argument("--field", default="")
    p.add_argument("--value", default="")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser(
        "tailor",
        help="Reorder emphasis from fact-checked A–F base toward JD (no re-fact-check)",
    )
    p.add_argument("--package", required=True)
    p.add_argument("--lane", default="", help="A-F (auto if empty)")
    p.add_argument("--llm", action="store_true", help="Optional rephrase of base lines only")
    p.add_argument("--allow-unchecked", action="store_true", help="Allow non-passed base (not recommended)")
    p.add_argument(
        "--allow-shallow-jd",
        action="store_true",
        help="Write plan even if JD short; exit non-zero so agents notice",
    )
    p.set_defaults(func=cmd_tailor)

    p = sub.add_parser(
        "pipeline",
        help=(
            "On-demand package step: enrich → tailor → materials_status "
            "(not part of scan; exit ≠0 if factcheck/JD weak)"
        ),
    )
    p.add_argument("--package", default=None, help="Package path (or use --job-id)")
    p.add_argument("--job-id", default=None, help="Job ID like C0-005 (resolves to package path)")
    p.add_argument("--lane", default="")
    p.add_argument("--llm", action="store_true")
    p.add_argument("--allow-unchecked", action="store_true")
    p.set_defaults(func=cmd_pipeline)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
