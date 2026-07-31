#!/usr/bin/env python3
"""Fail closed on JobsFlow public-release hygiene."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_PATH_PREFIXES = (
    "JobSearch_2026/",
    "config.personal.json",
    "job_search_tracker.csv",
)
REMOVED_LEGACY_PATHS = {
    ".claude/skills/job-scraper/SKILL.md",
    ".claude/skills/job-scraper/search-queries.md",
    "tools/fresh_24h/cv_temu_baseline_export.py",
}
MAX_PUBLIC_BLOB_BYTES = 10 * 1024 * 1024


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def _private_path(path: str) -> bool:
    normalized = path.strip()
    if normalized == ".env" or (
        normalized.startswith(".env.") and normalized != ".env.example"
    ):
        return True
    return any(
        normalized == prefix.rstrip("/") or normalized.startswith(prefix)
        for prefix in PRIVATE_PATH_PREFIXES
    )


def source_errors() -> list[str]:
    errors: list[str] = []
    guard = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "security_guards.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if guard.returncode:
        errors.append("security guards failed:\n" + guard.stdout.strip())

    tracked = _git("ls-files", "--cached", "--others", "--exclude-standard")
    if tracked.returncode:
        errors.append("cannot enumerate tracked files")
    else:
        for path in tracked.stdout.splitlines():
            if not (ROOT / path).exists():
                continue
            if _private_path(path):
                errors.append(f"private path is tracked: {path}")
            if path in REMOVED_LEGACY_PATHS:
                errors.append(f"legacy personal workflow is tracked: {path}")

    query_path = ROOT / "tools" / "fresh_24h" / "queries.json"
    try:
        query_template = json.loads(query_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"tracked query template is unreadable: {exc}")
    else:
        if query_template.get("setup_required") is not True:
            errors.append("tracked query template must require setup")
        if query_template.get("queries"):
            errors.append("tracked query template must not contain candidate queries")

    diff_check = _git("diff", "--check")
    if diff_check.returncode:
        errors.append("git diff --check failed:\n" + diff_check.stdout.strip())
    return errors


def history_errors() -> list[str]:
    errors = source_errors()
    history = _git("log", "--all", "--format=", "--name-only")
    if history.returncode:
        errors.append("cannot inspect Git history")
    else:
        private_history = sorted(
            {path for path in history.stdout.splitlines() if _private_path(path)}
        )
        if private_history:
            preview = ", ".join(private_history[:8])
            errors.append(
                "Git history contains private workspace paths; publish from a new "
                f"clean snapshot instead ({preview})"
            )
    objects = _git("rev-list", "--objects", "--all")
    if objects.returncode == 0:
        object_paths: dict[str, str] = {}
        for line in objects.stdout.splitlines():
            sha, _, path = line.partition(" ")
            object_paths.setdefault(sha, path)
        sized = subprocess.run(
            [
                "git",
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ],
            cwd=ROOT,
            input="\n".join(object_paths) + "\n",
            text=True,
            capture_output=True,
        )
        if sized.returncode == 0:
            oversized = []
            for line in sized.stdout.splitlines():
                sha, object_type, raw_size = line.split()
                if object_type == "blob" and int(raw_size) > MAX_PUBLIC_BLOB_BYTES:
                    oversized.append(
                        (
                            int(raw_size),
                            object_paths.get(sha) or sha,
                        )
                    )
            if oversized:
                preview = ", ".join(
                    f"{path} ({size / 1024 / 1024:.1f} MiB)"
                    for size, path in sorted(oversized, reverse=True)[:6]
                )
                errors.append(
                    "Git history contains oversized blobs; publish from a clean "
                    f"snapshot or explicitly justify them ({preview})"
                )
    status = _git("status", "--porcelain")
    if status.returncode or status.stdout.strip():
        errors.append("working tree is not clean; review and commit the release snapshot")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", action="store_true")
    mode.add_argument("--history", action="store_true")
    args = parser.parse_args(argv)
    errors = history_errors() if args.history else source_errors()
    if errors:
        print(f"public_release_check: {len(errors)} failure(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"public_release_check: OK ({'history' if args.history else 'source'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
