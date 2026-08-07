"""Build private, tracker-backed job manifests for material batches."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.io_utils import atomic_write_json
from tools.job_materials.manifest import build_job_manifest, write_job_manifest
from tools.job_materials.packages import create_package_from_tracker, find_tracker_row
from tools.job_materials.paths import jobsearch_root


def _root(value: Path) -> Path:
    root = Path(value).expanduser().resolve()
    return root if root.name == "JobSearch_2026" else root / "JobSearch_2026"


def _tracker_files(root: Path) -> list[Path]:
    tracker = _root(root) / "02_Tracker"
    if not tracker.is_dir():
        return []
    paths = [p for p in tracker.rglob("*.csv") if p.is_file()]

    def key(path: Path) -> tuple[int, float, str]:
        # The main apply list is authoritative; scored/candidate exports are a
        # useful fallback when the user selected a row before promoting it.
        priority = 0 if path.name.startswith("hk_apply_list_") else 1
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        return priority, -mtime, path.name

    return sorted(paths, key=key)


def _all_rows(root: Path) -> Iterable[tuple[dict[str, str], Path]]:
    seen: set[str] = set()
    for path in _tracker_files(root):
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    job_id = str(row.get("岗位编号") or row.get("job_id") or "").strip()
                    if not job_id or job_id in seen:
                        continue
                    seen.add(job_id)
                    yield {str(key): str(value or "") for key, value in row.items()}, path
        except (OSError, csv.Error, UnicodeError):
            continue


def build_jobs_json(
    root: Path,
    *,
    job_ids: list[str] | None = None,
    output: Path | None = None,
    create_packages: bool = True,
) -> dict[str, Any]:
    """Generate a private JSON batch manifest from local tracker rows.

    The generated fields are disposable.  User edits belong in each package's
    ``job_manifest.json.overrides`` (or the equivalent ``overrides`` object),
    so rerunning this command cannot erase confirmed wording.
    """
    workspace = _root(root)
    wanted = {str(item).strip() for item in (job_ids or []) if str(item).strip()}
    rows: list[tuple[dict[str, str], Path]] = []
    if wanted:
        for job_id in wanted:
            found = find_tracker_row(workspace, job_id)
            if found:
                rows.append(found)
    else:
        # Enumerate IDs from every export, then resolve each one through the
        # same priority order used by package creation (main apply list first,
        # then the newest scored/local export).  This prevents a stale scored
        # CSV from silently winning a batch manifest.
        all_ids = [
            str(row.get("岗位编号") or row.get("job_id") or "").strip()
            for row, _ in _all_rows(workspace)
        ]
        for job_id in all_ids:
            found = find_tracker_row(workspace, job_id)
            if found:
                rows.append(found)

    manifests: list[dict[str, Any]] = []
    for row, tracker_path in rows:
        job_id = str(row.get("岗位编号") or row.get("job_id") or "").strip()
        if not job_id:
            continue
        if create_packages:
            package = create_package_from_tracker(workspace, job_id)
            manifest_path = package / "job_manifest.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                manifest = build_job_manifest(
                    root=workspace,
                    package=package,
                    row=row,
                    tracker_path=tracker_path,
                )
                write_job_manifest(package, manifest)
        else:
            # No package side effect mode is useful for previewing a batch; the
            # package path is still deterministic and derived from the row.
            lane = str(row.get("简历版本") or row.get("lane") or "F").strip()[:1].upper() or "F"
            package = workspace / "01_Masters" / f"{lane}_track" / "待审" / job_id
            manifest = build_job_manifest(
                root=workspace,
                package=package,
                row=row,
                tracker_path=tracker_path,
            )
        manifests.append(manifest)

    result = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "local_tracker_and_jd_cache",
        "jobs": manifests,
        "model_contract": {
            "mode": "deterministic_manifest",
            "manual_fields": "jobs[].overrides",
            "do_not_infer_missing_values": True,
            "next_action": "review_overrides_then_run_materials_pipeline",
        },
    }
    target = Path(output or workspace / "02_Tracker" / "jobs.generated.json").expanduser()
    atomic_write_json(target, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=jobsearch_root())
    parser.add_argument("--job-id", action="append", default=[])
    parser.add_argument("--all", action="store_true", dest="all_jobs")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-create-packages", action="store_true")
    args = parser.parse_args(argv)
    if not args.all_jobs and not args.job_id:
        parser.error("provide --job-id (repeatable) or --all")
    result = build_jobs_json(
        args.root,
        job_ids=None if args.all_jobs else args.job_id,
        output=args.output,
        create_packages=not args.no_create_packages,
    )
    print(f"Wrote {len(result['jobs'])} job manifest(s)")
    print(f"Output: {args.output or _root(args.root) / '02_Tracker' / 'jobs.generated.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
