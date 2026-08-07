"""Deterministic length and sentence constraints for outbound materials.

The application pipeline does not rewrite user-owned DOCX templates.  It does,
however, expose one small, model-independent compaction primitive so a lower
capability model can keep the optional role/industry paragraph inside the same
slot and page budget as the generic Cover Letter.
"""

from __future__ import annotations

import re


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def compact_cover_letter_match(
    text: str,
    *,
    max_sentences: int = 2,
    max_chars: int = 420,
) -> str:
    """Keep a role/industry match paragraph compact without changing facts.

    Complete sentences are preferred.  If the first sentence alone exceeds the
    character budget, it is cut at the last word boundary and marked with an
    ellipsis; callers and validators still treat the result as a draft that
    requires the normal human/PDF review.
    """
    if max_sentences < 1 or max_chars < 1:
        return ""
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized:
        return ""
    sentences = [item.strip() for item in _SENTENCE_SPLIT.split(normalized) if item.strip()]
    selected: list[str] = []
    for sentence in sentences[:max_sentences]:
        candidate = " ".join(selected + [sentence])
        if len(candidate) <= max_chars:
            selected.append(sentence)
            continue
        if not selected:
            clipped = sentence[: max(0, max_chars - 1)].rstrip()
            if " " in clipped:
                clipped = clipped.rsplit(" ", 1)[0].rstrip()
            return (clipped + "…").strip()
        break
    return " ".join(selected).strip()


def sentence_count(text: str) -> int:
    """Count non-empty sentence-like fragments for deterministic validation."""
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    return len([item for item in _SENTENCE_SPLIT.split(normalized) if item.strip()]) if normalized else 0
