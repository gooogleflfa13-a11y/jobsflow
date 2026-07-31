#!/usr/bin/env python3
"""Migrate and repair private search configuration without touching product defaults."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.io_utils import atomic_write_json
from tools.profile_recovery import repair_scoring_profile


def _legacy_queries_from_head(repo: Path) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", "HEAD:tools/fresh_24h/queries.json"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode:
        return None
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("setup_required"):
        return None
    return value


def migrate_legacy_queries(repo: Path) -> Path | None:
    repo = Path(repo).resolve()
    destination = repo / "JobSearch_2026" / "00_Profile" / "queries.json"
    if destination.exists():
        repair_scoring_profile(repo, persist=True)
        return destination
    legacy = _legacy_queries_from_head(repo)
    if not legacy:
        return None
    legacy["schema_version"] = 2
    legacy["migrated_from"] = "legacy_tracked_queries"
    legacy.setdefault(
        "relevance_keywords",
        [
            "legal",
            "lawyer",
            "counsel",
            "solicitor",
            "paralegal",
            "litigation",
            "compliance",
            "regulatory",
            "aml",
            "kyc",
            "法务",
            "律师",
            "合规",
            "诉讼",
        ],
    )
    legacy.setdefault("adjacent_keywords", ["risk", "governance", "policy"])
    legacy.setdefault(
        "scoring_profile",
        {
            "domain": "legal",
            "core_keywords": legacy["relevance_keywords"],
            "adjacent_keywords": legacy["adjacent_keywords"],
            "evidence_keywords": [],
            "preferred_industry_keywords": [],
            "track_mapping": {
                "A": "诉讼/所内支持",
                "B": "合同商事/Counsel",
                "C": "合规/AML",
                "D": "跨境/中国法",
                "E": "重组/破产顾问",
                "F": "通用法律",
            },
            "track_rules": [],
            "weights": {
                "resume": 0.35,
                "eligibility": 0.2,
                "direction": 0.2,
                "industry": 0.1,
                "work": 0.1,
                "pay": 0.05,
            },
        },
    )
    atomic_write_json(destination, legacy)
    repair_scoring_profile(repo, persist=True)
    return destination


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    path = migrate_legacy_queries(repo)
    if path:
        profile, health, _ = repair_scoring_profile(repo, persist=True)
        data = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            pass
        recovered = ", ".join(
            (data.get("profile_recovery") or {}).get("fields")
            or health.get("recovered_fields")
            or []
        ) or "none"
        print(f"Private search config ready: {path}")
        print(
            f"Scoring profile: {health.get('status')} "
            f"(recovered={recovered}, evidence={len(profile.get('evidence_keywords') or [])}, "
            f"industry={len(profile.get('preferred_industry_keywords') or [])})"
        )
        return 0
    print("No legacy tracked queries found; run /setup.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
