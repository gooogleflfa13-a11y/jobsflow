"""Conservative parsing for localized numbers and salary ranges.

Salary values enter Jobsflow through several different surfaces: Excel
benchmarks, portal salary labels, and the user's search-intent text.  Keeping
the parser here makes those surfaces agree on decimal commas, grouped digits,
currency labels, and ambiguous values.

The parser deliberately does not guess a bare ``1,234`` (or ``1.234``): in
different locales it can mean either a decimal or a thousands separator.  A
salary range, an explicit currency, or an explicit pay period is enough
context to interpret it as a grouped integer.  Amount suffixes (``k``, ``M``,
``B``, ``万`` and ``亿``) are normalized before the value reaches a scorer.
Callers can therefore keep a neutral score or ask the user to confirm instead
of silently recording a bad constraint.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


PARSED = "parsed"
EMPTY = "empty"
AMBIGUOUS = "ambiguous"
INVALID = "invalid"


@dataclass(frozen=True)
class NumberParseResult:
    """Result of parsing one localized numeric value."""

    value: float | None
    status: str
    normalized: str = ""
    reason: str = ""


@dataclass(frozen=True)
class SalaryRange:
    """A salary value or range extracted from a label/text snippet."""

    low: float | None
    high: float | None
    currency: str = ""
    period: str = ""
    status: str = EMPTY
    raw: str = ""
    reason: str = ""


# Currency labels are intentionally small and explicit.  The generic ``$``
# symbol is kept as USD because callers should not treat an unlabeled dollar
# value as a Hong Kong-specific fact.
_CURRENCY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(?:HKD|HK\$|港币|港幣)\b|HK\$", "HKD"),
    (r"\b(?:USD|US\$|美元)\b|US\$|\$", "USD"),
    (r"\b(?:CNY|RMB|人民币|人民幣)\b|¥", "CNY"),
    (r"\b(?:EUR|欧元|歐元)\b|€", "EUR"),
    (r"\b(?:GBP|英镑|英鎊)\b|£", "GBP"),
    (r"\b(?:DKK|丹麦克朗|丹麥克朗)\b", "DKK"),
    (r"\b(?:SGD|新加坡元)\b", "SGD"),
    (r"\b(?:JPY|日元|日圓)\b|¥", "JPY"),
    (r"\b(?:CAD|加元)\b", "CAD"),
    (r"\b(?:AUD|澳元)\b", "AUD"),
)
_CURRENCY_RE = re.compile(
    "|".join(f"(?P<c{idx}>{pattern})" for idx, (pattern, _) in enumerate(_CURRENCY_PATTERNS)),
    re.IGNORECASE,
)
_CURRENCY_BY_GROUP = {f"c{idx}": code for idx, (_, code) in enumerate(_CURRENCY_PATTERNS)}

_PERIOD_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"per\s+month|monthly|month|/\s*mo\.?|月薪|每月|月", "monthly"),
    (r"per\s+year|yearly|annual|annually|year|/\s*yr?\.?|年薪|每年|年", "annual"),
    (r"per\s+week|weekly|week|/\s*wk?\.?|每周|每週|周薪|週薪", "weekly"),
    (r"per\s+day|daily|day|/\s*day|每日|日薪", "daily"),
)

# Keep spaces inside a number so ``1 234,5`` remains one token.  Separators
# between two amounts (for example ``28,000 - 32,000``) are not consumed.
#
# Do not include ``[+-]?`` here.  A hyphen in ``20,000-25,000`` is a range
# delimiter, not a negative sign.  Salary values are non-negative in the
# product contract; signed numbers remain supported by parse_localized_number
# when it is called directly.
_NUMBER_TOKEN_RE = re.compile(
    r"(?P<number>(?:"
    r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?"
    r"|\d+(?:\s+\d{3})+(?:[.,]\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r")(?:\s*['’]\s*\d{3})*)"
    r"(?:\s*(?P<unit>million|billion|bn|mm|[kKmMbB]|万|萬|千|亿|億))?"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)
_NUMERIC_ONLY_RE = re.compile(r"^[+-]?[\d.,\s'’]+$")
_CURRENCY_ONLY_RE = re.compile(
    r"(?i)^(?:hkd|hk\$|usd|us\$|rmb|cny|eur|gbp|dkk|sgd|jpy|cad|aud|"
    r"港币|港幣|美元|人民币|人民幣|欧元|歐元|英镑|英鎊|丹麦克朗|丹麥克朗|"
    r"新加坡元|日元|日圓|加元|澳元|[$€£¥])$"
)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _strip_currency(text: str) -> str:
    text = _CURRENCY_RE.sub(" ", text)
    return text.strip()


def parse_localized_number(
    value: Any,
    *,
    ambiguous_strategy: str = "reject",
) -> NumberParseResult:
    """Parse a number written with common locale separators.

    ``ambiguous_strategy`` may be ``reject`` (the default), ``grouped`` (a
    lone separator followed by three digits is a thousands separator),
    ``decimal``, or ``reject_comma``.  The latter matches the Excel release
    contract: a bare comma with three trailing digits is rejected, while a
    single dot remains a normal decimal value.  Product callers normally use
    the default; salary-range parsing selects ``grouped`` only when
    currency/range/period context makes that interpretation defensible.
    """

    if isinstance(value, bool):
        return NumberParseResult(None, INVALID, reason="boolean is not a salary number")
    if isinstance(value, (int, float, Decimal)):
        number = _finite_float(value)
        if number is None:
            return NumberParseResult(None, INVALID, reason="non-finite number")
        return NumberParseResult(number, PARSED, normalized=str(value))

    if value is None:
        return NumberParseResult(None, EMPTY)
    text = str(value).replace("\u00a0", " ").replace("\u202f", " ").strip()
    if not text:
        return NumberParseResult(None, EMPTY)
    if _CURRENCY_ONLY_RE.fullmatch(text):
        return NumberParseResult(None, INVALID, reason="currency label without amount")

    text = _strip_currency(text)
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"\s+", " ", text).strip()
    if not text or not _NUMERIC_ONLY_RE.fullmatch(text):
        return NumberParseResult(None, INVALID, reason="contains non-numeric text")

    compact = text.replace(" ", "")
    comma_count = compact.count(",")
    dot_count = compact.count(".")

    if comma_count and dot_count:
        # The last separator is the decimal marker.  Earlier separators are
        # grouping markers, covering both ``1.234,5`` and ``1,234.5``.
        last_comma = compact.rfind(",")
        last_dot = compact.rfind(".")
        decimal_sep = "," if last_comma > last_dot else "."
        grouping_sep = "." if decimal_sep == "," else ","
        compact = compact.replace(grouping_sep, "").replace(decimal_sep, ".")
    elif comma_count:
        if comma_count > 1:
            groups = compact.split(",")
            if len(groups[0].lstrip("+-")) not in range(1, 4) or any(len(part) != 3 for part in groups[1:]):
                return NumberParseResult(None, INVALID, reason="invalid comma grouping")
            compact = "".join(groups)
        else:
            left, right = compact.split(",")
            if len(right) == 3:
                if ambiguous_strategy in {"reject", "reject_comma"}:
                    return NumberParseResult(
                        None,
                        AMBIGUOUS,
                        normalized=text,
                        reason="single comma with three trailing digits can be decimal or thousands grouping",
                    )
                if ambiguous_strategy == "grouped":
                    compact = left + right
                elif ambiguous_strategy == "decimal":
                    compact = left + "." + right
                else:
                    return NumberParseResult(None, INVALID, reason="unknown ambiguity strategy")
            else:
                compact = left + "." + right
    elif dot_count:
        if dot_count > 1:
            groups = compact.split(".")
            if len(groups[0].lstrip("+-")) not in range(1, 4) or any(len(part) != 3 for part in groups[1:]):
                return NumberParseResult(None, INVALID, reason="invalid dot grouping")
            compact = "".join(groups)
        else:
            left, right = compact.split(".")
            if len(right) == 3 and ambiguous_strategy == "grouped":
                compact = left + right
            elif len(right) == 3 and ambiguous_strategy == "reject":
                return NumberParseResult(
                    None,
                    AMBIGUOUS,
                    normalized=text,
                    reason="single dot with three trailing digits can be decimal or thousands grouping",
                )
            else:
                compact = left + "." + right

    normalized = compact
    try:
        number = float(Decimal(normalized))
    except (InvalidOperation, ValueError, OverflowError):
        return NumberParseResult(None, INVALID, normalized=normalized, reason="invalid numeric value")
    if not math.isfinite(number):
        return NumberParseResult(None, INVALID, normalized=normalized, reason="non-finite number")
    return NumberParseResult(number, PARSED, normalized=normalized)


def _currency_and_period(text: str) -> tuple[str, str]:
    currency = ""
    match = _CURRENCY_RE.search(text)
    if match:
        currency = _CURRENCY_BY_GROUP.get(match.lastgroup or "", "")
    period = ""
    for pattern, label in _PERIOD_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            period = label
            break
    return currency, period


def _number_tokens(text: str) -> list[re.Match[str]]:
    matches = list(_NUMBER_TOKEN_RE.finditer(text))
    # Regex alternatives can leave punctuation-only fragments; discard those
    # and avoid overlapping matches if a future pattern is expanded.
    output: list[re.Match[str]] = []
    end = -1
    for match in matches:
        if match.start() < end:
            continue
        output.append(match)
        end = match.end()
    return output


_AMOUNT_UNIT_MULTIPLIERS: dict[str, float] = {
    "k": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    "千": 1_000.0,
    "万": 10_000.0,
    "萬": 10_000.0,
    "亿": 100_000_000.0,
    "億": 100_000_000.0,
}


def _parse_amount_token(match: re.Match[str], *, ambiguous_strategy: str) -> NumberParseResult:
    """Parse a number token and apply an attached amount unit.

    The unit is kept outside ``parse_localized_number`` so that the latter
    remains a strict numeric parser.  ``3 months`` is not interpreted as
    ``3M`` because the token regex only accepts a unit at a word boundary.
    """

    number_text = match.group("number")
    unit = (match.group("unit") or "").casefold()
    result = parse_localized_number(number_text, ambiguous_strategy=ambiguous_strategy)
    if result.status != PARSED or result.value is None:
        return result
    multiplier = _AMOUNT_UNIT_MULTIPLIERS.get(unit, 1.0)
    value = result.value * multiplier
    if not math.isfinite(value):
        return NumberParseResult(None, INVALID, reason="non-finite amount after unit conversion")
    normalized = f"{value:g}"
    return NumberParseResult(value, PARSED, normalized=normalized)


def parse_salary_range(value: Any) -> SalaryRange:
    """Parse a salary label such as ``HKD 28,000–32,000 monthly``.

    Attached units such as ``35k–40k``, ``1.5M–2M`` and ``2万–2.5万`` are
    converted to their base currency amount.

    A single bare value with an ambiguous separator is returned as
    ``status='ambiguous'``.  Explicit currency, a pay period, or two values in
    a range supplies enough context to interpret grouped thousands safely.
    """

    if value is None:
        return SalaryRange(None, None)
    raw = str(value).replace("\u00a0", " ").replace("\u202f", " ").strip()
    if not raw:
        return SalaryRange(None, None)

    currency, period = _currency_and_period(raw)
    matches = _number_tokens(raw)
    if not matches:
        return SalaryRange(None, None, currency, period, INVALID, raw, "no numeric amount found")

    # Ignore explicit experience/year counts when a salary phrase also carries
    # a number, e.g. ``3 years' experience; HKD 30,000``.
    useful: list[re.Match[str]] = []
    for match in matches:
        after = raw[match.end() : match.end() + 16]
        if re.match(
            r"\s*(?:\+?\s*years?\b|年(?:经验|經驗)?|months?\b|weeks?\b|days?\b|个月|個月)",
            after,
            flags=re.IGNORECASE,
        ):
            continue
        useful.append(match)
    if not useful:
        return SalaryRange(
            None,
            None,
            currency,
            period,
            INVALID,
            raw,
            "numeric value belongs to an experience/duration field",
        )

    # Currency suffixes are common (``30,000 HKD``); choose the nearest one or
    # two amounts around the currency marker instead of unrelated numbers.
    currency_match = _CURRENCY_RE.search(raw)
    if currency_match and len(useful) > 2:
        after = [item for item in useful if item.start() >= currency_match.end()]
        before = [item for item in useful if item.end() <= currency_match.start()]
        useful = (after or list(reversed(before)))[:2]
    else:
        useful = useful[:2]

    # Currency, period, a genuine range, or an explicit amount unit gives a
    # safe hint that a three-digit suffix is grouping.  A single bare
    # ``1,234`` stays ambiguous.
    has_amount_unit = any(match.group("unit") for match in useful)
    grouped_context = bool(currency or period or len(useful) >= 2 or has_amount_unit)
    strategy = "grouped" if grouped_context else "reject"
    parsed: list[float] = []
    for match in useful:
        result = _parse_amount_token(match, ambiguous_strategy=strategy)
        if result.status == AMBIGUOUS:
            return SalaryRange(None, None, currency, period, AMBIGUOUS, raw, result.reason)
        if result.status != PARSED or result.value is None:
            return SalaryRange(None, None, currency, period, INVALID, raw, result.reason)
        parsed.append(result.value)

    if not parsed:
        return SalaryRange(None, None, currency, period, INVALID, raw, "no usable salary amount")
    low = parsed[0]
    high = parsed[1] if len(parsed) > 1 else parsed[0]
    if high < low:
        low, high = high, low
    return SalaryRange(low, high, currency, period, PARSED, raw)
