"""Spreadsheet-safe handling for values originating outside the repository."""

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_spreadsheet_formula(value):
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value
