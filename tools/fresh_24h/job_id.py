#!/usr/bin/env python3
"""Job ID allocation for fresh scans — aligns with 简历审查简报 rules.

Format: {A-F}{0-2}-{NNN}
  letter  = resume version (A litigation … F general)
  digit   = 0 核心 (B/C, score≥3.5) | 1 一级 (D, score≥3.3) | 2 二级 (D<3.3 or E)
  NNN     = continues from max existing ID in Google Sheet / tracker for that prefix

Fresh tab rows are ordered by score desc; within each prefix, numbers increase
so higher scores get earlier continuation numbers in that batch.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable


def tier_from_score(score: float, grade: str = "") -> tuple[int, str]:
    g = (grade or "").strip().upper()
    if g in {"A", "B", "C"} or score >= 3.5:
        return 0, "核心"
    if g == "D" and score >= 3.3:
        return 1, "一级"
    if g in {"D", "E"} or score >= 2.5:
        return 2, "二级"
    return 3, "剔除"


def parse_id(jid: str) -> tuple[str, int, int] | None:
    m = re.match(r"^([A-F])([0-3])-(\d+)$", (jid or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3))


def max_prefix_from_ids(ids: Iterable[str]) -> dict[str, int]:
    mx: dict[str, int] = defaultdict(int)
    for jid in ids:
        p = parse_id(jid)
        if not p:
            continue
        letter, digit, n = p
        pref = f"{letter}{digit}"
        mx[pref] = max(mx[pref], n)
    return dict(mx)


def allocate_ids(
    jobs: list[dict],
    *,
    baseline_max: dict[str, int],
    letter_key: str = "简历版本",
    score_key: str = "CareerOps分数",
    grade_key: str = "CareerOps等级",
) -> list[dict]:
    """Assign 岗位编号 + 层级 in place. jobs should already be score-sorted desc."""
    counters = dict(baseline_max)
    for row in jobs:
        score = float(row.get(score_key) or 0)
        grade = str(row.get(grade_key) or "")
        digit, tier_name = tier_from_score(score, grade)
        letter = (str(row.get(letter_key) or "F").strip().upper()[:1] or "F")
        if letter not in "ABCDEF":
            letter = "F"
        pref = f"{letter}{digit}"
        counters[pref] = counters.get(pref, 0) + 1
        row["岗位编号"] = f"{letter}{digit}-{counters[pref]:03d}"
        row["层级"] = tier_name
        row["简历版本"] = letter
    return jobs
