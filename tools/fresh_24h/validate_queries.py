#!/usr/bin/env python3
"""Validate a product template or setup-generated queries config.

Checks:
  1. All buckets listed in query_policy.mandatory_buckets have at least one query.
  2. No mandatory bucket is empty.
  3. Each query has valid terms for linkedin, jobsdb, and ctgoodjobs.
  4. No query references a non-existent bucket.

Exit with code 0 on success, 1 on failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
QUERIES = REPO / "tools" / "fresh_24h" / "queries.json"
REQUIRED_TERM_PORTALS = {"linkedin", "jobsdb", "ctgoodjobs"}
SUPPORTED_PORTALS = REQUIRED_TERM_PORTALS | {"freehire"}
SCAN_DEPTHS = {"economy", "balanced", "coverage"}
RETENTION_PREFERENCES = {"loose", "standard", "selective"}


def main(argv: list[str] | None = None) -> int:
    path = Path(argv[0]).expanduser().resolve() if argv else QUERIES
    if not path.exists():
        print(f"ERROR: queries.json not found at {path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    policy = data.get("query_policy") or {}
    mandatory_buckets = policy.get("mandatory_buckets") or []
    queries = data.get("queries") or []

    errors: list[str] = []
    workflow = data.get("workflow_preferences") or {}
    if workflow:
        if workflow.get("scan_depth") not in SCAN_DEPTHS:
            errors.append("workflow_preferences.scan_depth must be economy|balanced|coverage")
        if workflow.get("retention_preference") not in RETENTION_PREFERENCES:
            errors.append(
                "workflow_preferences.retention_preference must be loose|standard|selective"
            )
    if data.get("setup_required"):
        if queries:
            errors.append("product template with setup_required=true must not ship job queries")
        if mandatory_buckets:
            errors.append("product template must not ship profession-specific mandatory buckets")
        if errors:
            print("FAIL queries.json validation:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print("OK queries.json: industry-neutral setup-required product template")
        return 0

    # 1. Collect buckets present in queries
    present_buckets: dict[str, list[dict]] = {}
    for q in queries:
        b = q.get("bucket") or "unknown"
        present_buckets.setdefault(b, []).append(q)

    # 2. Check mandatory buckets present
    for mb in mandatory_buckets:
        if mb not in present_buckets:
            errors.append(f"mandatory bucket '{mb}' has zero queries")

    if len(mandatory_buckets) < 3:
        errors.append("setup-generated config must define at least three mandatory buckets")

    # 4. Each query must have non-empty terms for all portals
    for q in queries:
        qid = q.get("id") or "?"
        terms = q.get("terms") or {}
        for portal in REQUIRED_TERM_PORTALS:
            val = (terms.get(portal) or "").strip()
            if not val:
                errors.append(f"query '{qid}' has empty term for portal '{portal}'")

    configured = set((data.get("portals") or {}).keys())
    unknown = configured - SUPPORTED_PORTALS
    if unknown:
        errors.append(f"unsupported configured portals: {sorted(unknown)}")

    # 5. Each query must reference a valid bucket
    for q in queries:
        b = q.get("bucket") or "unknown"
        if b not in present_buckets:
            errors.append(f"query '{q.get('id')}' references non-standard bucket '{b}'")

    if errors:
        print("FAIL queries.json validation:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK queries.json: {len(queries)} queries across {len(present_buckets)} buckets (mandatory: {len(mandatory_buckets)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
