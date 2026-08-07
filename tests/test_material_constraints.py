from tools.job_materials.material_constraints import compact_cover_letter_match, sentence_count


def test_compact_cover_letter_match_keeps_two_sentences_and_budget():
    value = compact_cover_letter_match(
        "The role builds reliable workflow controls. "
        "My evidence shows I implemented review checkpoints and can improve delivery. "
        "This third sentence must not enter the slot.",
        max_chars=150,
    )

    assert sentence_count(value) == 2
    assert "third sentence" not in value
    assert len(value) <= 150


def test_compact_cover_letter_match_trims_a_single_long_sentence_at_word_boundary():
    value = compact_cover_letter_match(
        "The role requires responsible automation and cross-functional process monitoring "
        "across business teams.",
        max_chars=55,
    )

    assert value.endswith("…")
    assert len(value) <= 55
    assert not value.endswith(" .")
