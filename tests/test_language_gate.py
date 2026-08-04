from tools.language_gate import (
    FAIL,
    FLAG,
    PASS,
    REVIEW,
    evaluate_language_gate,
    extract_language_requirements,
    parse_candidate_languages,
)


def test_candidate_language_profile_parses_names_and_levels():
    records = parse_candidate_languages("English C1; 粤语 母语")

    assert {(item["key"], item["level"]) for item in records} == {
        ("english", "c1"),
        ("cantonese", "native"),
    }


def test_posting_language_is_not_confused_with_the_language_used_to_write_the_ad():
    assert extract_language_requirements("The role is written in English.") == []
    assert extract_language_requirements("Reports must be written in English.")


def test_missing_declared_language_is_a_hard_fail():
    result = evaluate_language_gate("Fluent French required.", "English C1")

    assert result["status"] == FAIL
    assert "French" in result["note"]


def test_higher_language_bar_is_a_flag_not_an_auto_reject():
    result = evaluate_language_gate("Must be fluent in English.", "English B2")

    assert result["status"] == FLAG
    assert "B2" in result["note"] or "b2" in result["note"]


def test_declared_language_without_level_passes_unspecified_requirement():
    result = evaluate_language_gate("English required.", "English")

    assert result["status"] == PASS


def test_empty_private_language_profile_requires_setup_review():
    result = evaluate_language_gate("Must be fluent in Cantonese.", [])

    assert result["status"] == REVIEW
    assert "档案" in result["note"]
