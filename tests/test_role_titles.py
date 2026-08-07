from tools.job_materials.role_titles import build_role_title_contract, normalize_role_for_material


def test_substantive_parenthetical_is_preserved_and_metadata_is_not():
    substantive = build_role_title_contract("Paralegal (Corporate Funds)")
    metadata = build_role_title_contract("Paralegal (Hong Kong)")
    fullwidth = build_role_title_contract("分析师（香港）")

    assert substantive["primary"] == "Paralegal (Corporate Funds)"
    assert substantive["specialisms"] == ["Corporate Funds"]
    assert metadata["primary"] == "Paralegal"
    assert metadata["metadata_parentheticals"] == ["Hong Kong"]
    assert fullwidth["primary"] == "分析师"


def test_slash_alternatives_are_separate_but_known_acronym_compound_is_not():
    alternatives = build_role_title_contract("Paralegal / Legal Assistant")
    acronym = build_role_title_contract("UI/UX Designer")

    assert alternatives["primary"] == "Paralegal"
    assert alternatives["alternates"] == ["Legal Assistant"]
    assert alternatives["confirmation_needed"] is True
    assert acronym["primary"] == "UI/UX Designer"
    assert acronym["alternates"] == []


def test_normalizer_never_introduces_a_short_dash_for_parentheses():
    value = normalize_role_for_material("Paralegal (Corporate Funds)")
    assert value == "Paralegal (Corporate Funds)"
    assert "-" not in value
