"""Deterministic parsing of minimum experience requirements in job descriptions.

JD wording commonly expresses a band (``2 to 5 years``) even though the
scorer needs the *minimum* threshold to compare with a candidate's configured
experience ceiling.  This module keeps that interpretation in one place so
the score, gap classification, and downstream material checks cannot disagree.

This parser is intentionally conservative: it recognizes explicit numeric
years/PQE expressions, preserves the matched wording, and does not turn
unrelated dates or vague seniority labels into years of experience.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExperienceRequirement:
    """A normalized JD experience expression.

    ``minimum_years`` is the value used by scoring.  A maximum-only expression
    such as ``up to 5 years`` has no minimum and therefore does not create a
    hard experience cap.  ``maximum_years`` is retained for display and future
    policy decisions.
    """

    minimum_years: int | None
    maximum_years: int | None
    matched_text: str
    normalized: str


_ZH_NUMERIC = r"(?:\d+|[零〇一二两兩三四五六七八九十百千万萬]+)"
_ZH_EXPERIENCE_SUFFIX = (
    r"\s*(?:相关|相關)?\s*(?:工作|从业|從業)?\s*(?:经验|經驗)"
)
_EN_RANGE_RE = re.compile(
    r"(?<![\w])(?P<lower>\d+)\s*(?:to|[-–—~～])\s*(?P<upper>\d+)\s*"
    r"(?P<unit>years?|yrs?|pqe)\b",
    re.IGNORECASE,
)
_ZH_RANGE_RE = re.compile(
    rf"(?<![\w])(?P<lower>{_ZH_NUMERIC})\s*(?:至|到|[-–—~～])\s*"
    rf"(?P<upper>{_ZH_NUMERIC})\s*年"
    rf"(?:(?P<suffix>{_ZH_EXPERIENCE_SUFFIX})(?=$|[^0-9A-Za-z_])|"
    r"(?=$|[^\w]))",
)
_EN_SINGLE_RE = re.compile(
    r"(?<![\w])"
    r"(?P<qualifier>at\s+least|minimum|min\.?|over|more\s+than|"
    r"no\s+less\s+than|not\s+less\s+than|up\s+to|maximum|max\.?|"
    r"no\s+more\s+than|not\s+more\s+than)?\s*"
    r"(?P<value>\d+)\s*(?P<plus>\+)?\s*"
    r"(?P<unit>years?|yrs?|pqe)\b",
    re.IGNORECASE,
)
_ZH_SINGLE_RE = re.compile(
    rf"(?<![\w])"
    rf"(?P<qualifier>至少|最少|不少于|不低于|超过|多于|至多|最多|不超过|不多于)?\s*"
    rf"(?P<value>{_ZH_NUMERIC})\s*(?P<plus>\+)?\s*年"
    rf"(?:(?P<suffix>{_ZH_EXPERIENCE_SUFFIX})(?=$|[^0-9A-Za-z_])|"
    r"(?=$|[^\w]))",
)

_MAX_QUALIFIERS = {
    "up to",
    "maximum",
    "max",
    "no more than",
    "not more than",
    "至多",
    "最多",
    "不超过",
    "不超過",
    "不多于",
    "不多於",
}


def _chinese_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "兩": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000, "萬": 10000}
    if not value or any(char not in digits and char not in units for char in value):
        return None
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in digits:
            number = digits[char]
            continue
        unit = units[char]
        if unit < 10000:
            section += (number or 1) * unit
        else:
            section += number
            total += (section or 1) * unit
            section = 0
        number = 0
    result = total + section + number
    return result if result > 0 else None


def _number(value: str) -> int | None:
    try:
        parsed = _chinese_number(value)
    except (TypeError, ValueError):
        return None
    # A JD experience threshold beyond a normal working lifetime is almost
    # certainly a date or malformed text; do not let it affect scoring.
    return parsed if parsed is not None and 0 < parsed <= 100 else None


def _minimum_or_maximum(
    value: int,
    qualifier: str,
    plus: bool,
) -> tuple[int | None, int | None]:
    normalized_qualifier = re.sub(r"\s+", " ", (qualifier or "").strip().casefold())
    if normalized_qualifier in _MAX_QUALIFIERS:
        return None, value
    # ``+`` and minimum/at-least/over wording all represent a lower bound. A
    # plain number is also treated as the minimum, preserving the old scorer's
    # behavior for ``3 years' experience``.
    return value, None


def parse_experience_requirement(text: str) -> ExperienceRequirement | None:
    """Parse the first explicit JD experience requirement.

    A range returns its lower bound for scoring while retaining its upper bound
    and original matched text.  The first complete expression is intentional:
    phrases such as ``2 years, or 1 year in a similar role`` should not be
    replaced by a later unrelated total-years statement.
    """

    source = str(text or "")
    if not source.strip():
        return None

    for pattern in (_EN_RANGE_RE, _ZH_RANGE_RE):
        match = pattern.search(source)
        if not match:
            continue
        lower = _number(match.group("lower"))
        upper = _number(match.group("upper"))
        if lower is None or upper is None or lower > upper:
            continue
        matched = match.group(0).strip()
        unit = match.groupdict().get("unit") or "年"
        normalized = f"{lower}–{upper} {unit.lower() if unit != '年' else '年'}"
        return ExperienceRequirement(lower, upper, matched, normalized)

    for pattern in (_EN_SINGLE_RE, _ZH_SINGLE_RE):
        match = pattern.search(source)
        if not match:
            continue
        value = _number(match.group("value"))
        if value is None:
            continue
        qualifier = match.group("qualifier") or ""
        minimum, maximum = _minimum_or_maximum(
            value,
            qualifier,
            bool(match.group("plus")),
        )
        matched = match.group(0).strip()
        unit = match.groupdict().get("unit") or "年"
        if maximum is not None:
            normalized = f"up to {maximum} {unit.lower() if unit != '年' else '年'}"
        elif match.group("plus"):
            normalized = f"{minimum}+ {unit.lower() if unit != '年' else '年'}"
        else:
            normalized = f"{minimum} {unit.lower() if unit != '年' else '年'}"
        return ExperienceRequirement(minimum, maximum, matched, normalized)
    return None
