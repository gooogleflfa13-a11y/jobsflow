import pytest

from tools.salary_parsing import AMBIGUOUS, INVALID, PARSED, parse_localized_number, parse_salary_range


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("108,5", 108.5),
        ("1.234,5", 1234.5),
        ("1 234,5", 1234.5),
        ("1,234.5", 1234.5),
        ("1,234,567", 1234567.0),
    ],
)
def test_localized_numbers_parse_without_locale_specific_callers(raw, expected):
    result = parse_localized_number(raw)

    assert result.status == PARSED
    assert result.value == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["1,234", "1.234"])
def test_single_three_digit_separator_is_not_guessed(raw):
    result = parse_localized_number(raw)

    assert result.status == AMBIGUOUS
    assert result.value is None


def test_salary_range_uses_currency_and_range_context_for_grouped_thousands():
    result = parse_salary_range("HKD 28,000–32,000 monthly")

    assert result.status == PARSED
    assert result.currency == "HKD"
    assert result.period == "monthly"
    assert result.low == 28000
    assert result.high == 32000


def test_salary_suffix_currency_is_supported():
    result = parse_salary_range("30.000–32.000 EUR")

    assert result.status == PARSED
    assert result.currency == "EUR"
    assert (result.low, result.high) == (30000, 32000)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20,000-25,000", (20_000, 25_000)),
        ("HKD 1.5M - 2M", (1_500_000, 2_000_000)),
        ("$35k - $40k", (35_000, 40_000)),
        ("月薪 2万-2.5万", (20_000, 25_000)),
    ],
)
def test_salary_ranges_keep_the_separator_and_normalize_amount_units(raw, expected):
    result = parse_salary_range(raw)

    assert result.status == PARSED
    assert (result.low, result.high) == expected


def test_salary_range_does_not_treat_months_as_millions():
    result = parse_salary_range("3 months experience; HKD 30,000-40,000")

    assert result.status == PARSED
    assert (result.low, result.high) == (30_000, 40_000)


def test_bare_minimum_amount_stays_ambiguous_until_user_confirms_locale():
    result = parse_salary_range("minimum 30,000")

    assert result.status == AMBIGUOUS
    assert result.low is None


def test_non_salary_text_is_invalid():
    result = parse_salary_range("salary negotiable")

    assert result.status == INVALID
    assert result.low is None
