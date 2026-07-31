"""Deterministic LLMO contracts for job-material generation.

LLMO here means information-loss control for ATS/RAG/LLM readers.  The module
does not promise an ATS score and never asks a model to add unsupported claims.
It turns a fact-checked base and a JD into explicit evidence nodes, requirement
anchors, and a cross-material contract that a less capable model can execute.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any


LLMO_SCHEMA_VERSION = 1
_REQUIRED_LANGUAGE = re.compile(
    r"\b(?:must|required|minimum|at\s+least|need(?:s)?\s+to|experience\s+in|"
    r"proficien(?:t|cy)|qualification|degree|license|licen[cs]e|\d+\+?\s+years?)\b|"
    r"必须|要求|至少|需要|资格|学历|牌照|执业|经验",
    re.I,
)
_NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:\d+(?:[.,]\d+)*\+?|\d+%)(?![A-Za-z])")
_SENTENCE_RE = re.compile(r"[^.!?。！？\n]{20,240}[.!?。！？]?")
_STOP_TOKENS = {
    "and", "the", "for", "with", "from", "that", "this", "into", "your",
    "our", "their", "role", "experience", "required", "must", "need",
}


def _stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha256(" ".join(str(text).split()).casefold().encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:10].upper()}"


def _metric_values(text: str) -> list[str]:
    return sorted(set(_NUMBER_RE.findall(text or "")))


def _factcheck_claims(base: dict[str, Any]) -> dict[str, dict[str, Any]]:
    claims = (base.get("factcheck") or {}).get("claims") or []
    return {
        str(item.get("text") or "").strip().casefold(): item
        for item in claims
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    }


def build_evidence_nodes(base: dict[str, Any]) -> list[dict[str, Any]]:
    """Create stable, auditable evidence nodes from a passed base.

    ``fact_status`` and ``lint_status`` are deliberately separate.  A node is
    only usable for external drafting when the base claim was fact-checked;
    containing the same words is not treated as independent proof.
    """
    claims = _factcheck_claims(base)
    base_status = str((base.get("factcheck") or {}).get("status") or "missing")
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in base.get("bullets") or []:
        claim = " ".join(str(raw or "").split()).strip()
        if not claim:
            continue
        check = claims.get(claim.casefold(), {})
        # Preserve the independent fact store's ID when the base factcheck
        # matched one.  This is what lets a profile edit invalidate every
        # material view that used the same fact node.
        matched_ids = check.get("evidence_ids") or []
        matched_id = check.get("evidence_id") or (matched_ids[0] if matched_ids else "")
        node_id = str(matched_id or _stable_id("EVID", claim))
        if node_id in seen:
            continue
        seen.add(node_id)
        # Older/runtime bases may only carry the aggregate passed status.  Keep
        # that contract valid while preferring per-claim support whenever it is
        # available; the node still records whether an independent claim row
        # was present in ``support_detail``.
        supported = base_status == "passed" and (
            not claims or bool(check.get("supported"))
        )
        nodes.append(
            {
                "evidence_id": node_id,
                "claim": claim,
                "entities": [],
                "metrics": _metric_values(claim),
                "contexts": [str(base.get("label") or "general")],
                "allowed_phrasing": [claim],
                "forbidden_inference": [
                    "Do not add duties, tools, scope, seniority, clients, metrics or outcomes not present in this claim."
                ],
                "source_refs": [
                    f"fact_checked_base:{base.get('base_id') or '?'}",
                    *([f"fact_evidence:{matched_id}"] if matched_id else []),
                ],
                "fact_status": "fact_verified" if supported else "needs_fact_check",
                "lint_status": "lint_passed" if claim else "lint_failed",
                "support_detail": {
                    "base_factcheck": base_status,
                    "independent_claim_match": bool(check),
                    "hit_ratio": check.get("hit_ratio"),
                    "evidence_ids": list(matched_ids),
                },
            }
        )
    return nodes


def _anchor_sentence(jd: str, focus: str) -> str:
    hints = [part for part in re.split(r"[_ ]+", focus) if len(part) > 3]
    for sentence in _SENTENCE_RE.findall(jd or ""):
        low = sentence.casefold()
        if any(h.casefold() in low for h in hints):
            return " ".join(sentence.split())[:240]
    return focus.replace("_", " ")


def _focus_is_required(jd: str, focus: str, exact: str) -> bool:
    """Apply hard-requirement status to the matching anchor, not the whole JD."""
    if _REQUIRED_LANGUAGE.search(exact):
        return True
    focus_terms = [part.casefold() for part in re.split(r"[_ ]+", focus) if len(part) > 3]
    # If the capability label is only a fallback, require a nearby semantic
    # hint before borrowing a hard-requirement signal from the JD.
    relevant = any(
        term in jd.casefold() or term[:5] in jd.casefold()
        for term in focus_terms
    )
    return relevant and bool(_REQUIRED_LANGUAGE.search(jd or ""))


def _node_relevance(anchor: str, node: dict[str, Any]) -> float:
    a = set(re.findall(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff+.#/-]{2,40}", anchor.casefold()))
    b = set(re.findall(r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff+.#/-]{2,40}", str(node.get("claim") or "").casefold()))
    a -= _STOP_TOKENS
    b -= _STOP_TOKENS
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a))


def build_jd_anchors(
    jd: str,
    focus: list[str],
    evidence_nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map capability anchors to evidence without treating keyword hits as proof."""
    anchors: list[dict[str, Any]] = []
    for index, capability in enumerate(focus):
        exact = _anchor_sentence(jd, capability)
        required = _focus_is_required(jd, capability, exact)
        ranked = sorted(
            (
                (_node_relevance(exact, node), node)
                for node in evidence_nodes
                if node.get("fact_status") == "fact_verified"
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        linked = [node for score, node in ranked if score >= 0.18][:3]
        best_score = ranked[0][0] if ranked else 0.0
        if not linked:
            status = "prohibited_to_claim" if required else "uncovered"
        elif best_score < 0.45:
            status = "partial"
        else:
            status = "covered"
        anchors.append(
            {
                "anchor_id": _stable_id("ANCHOR", f"{capability}:{exact}"),
                "text": exact,
                "capability": capability,
                "tier": 1 if required or index < 3 else 2,
                "required": required,
                "evidence_ids": [str(node["evidence_id"]) for node in linked],
                "status": status,
                "boundary": (
                    "Only use linked evidence IDs; do not turn an uncovered requirement into a claim."
                    if status in {"uncovered", "prohibited_to_claim"}
                    else "Use the linked evidence wording and preserve its scope."
                ),
            }
        )
    return anchors


def _ids_for_text(text: str, nodes: list[dict[str, Any]]) -> list[str]:
    value = " ".join(str(text or "").split()).casefold()
    return [str(node["evidence_id"]) for node in nodes if str(node.get("claim") or "").casefold() == value]


def build_cross_material_contract(
    *,
    summary: str,
    bullets: list[str],
    evidence_nodes: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    role: str,
    company: str,
) -> dict[str, Any]:
    selected_ids: list[str] = []
    for item in [summary, *bullets]:
        for evidence_id in _ids_for_text(item, evidence_nodes):
            if evidence_id not in selected_ids:
                selected_ids.append(evidence_id)
    for anchor in anchors:
        for evidence_id in anchor.get("evidence_ids") or []:
            if evidence_id not in selected_ids and len(selected_ids) < 8:
                selected_ids.append(evidence_id)
    metrics = sorted(
        {
            metric
            for node in evidence_nodes
            if node.get("evidence_id") in selected_ids
            for metric in node.get("metrics") or []
        }
    )
    return {
        "schema_version": LLMO_SCHEMA_VERSION,
        "role": role,
        "company": company,
        "shared_evidence_ids": selected_ids,
        "numeric_facts": metrics,
        "materials": {
            "cv": {"purpose": "parseable evidence view", "evidence_ids": selected_ids},
            "cover_letter": {
                "purpose": "motivation plus the first three mapped evidence points",
                "evidence_ids": selected_ids[:3],
            },
            "application_email": {
                "purpose": "short application note using the same strongest evidence",
                "evidence_ids": selected_ids[:3],
            },
        },
        "consistency_rules": [
            "Reuse the same evidence_id for the same claim in CV, cover letter and email.",
            "Do not change numbers, employer names, titles or scope between materials.",
            "If a fact changes, regenerate every material view that references its evidence_id.",
        ],
        "claim_policy": {
            "allowed": "fact_verified evidence nodes only",
            "prohibited": "uncovered, prohibited_to_claim or inferred Tier 3 claims",
            "human_review_required": any(
                anchor.get("status") in {"partial", "uncovered", "prohibited_to_claim"}
                for anchor in anchors
            ),
        },
    }


def build_llmo_contract(
    *,
    jd: str,
    focus: list[str],
    base: dict[str, Any],
    summary: str,
    bullets: list[str],
    role: str,
    company: str,
) -> dict[str, Any]:
    nodes = build_evidence_nodes(base)
    anchors = build_jd_anchors(jd, focus, nodes)
    cross_material = build_cross_material_contract(
        summary=summary,
        bullets=bullets,
        evidence_nodes=nodes,
        anchors=anchors,
        role=role,
        company=company,
    )
    return {
        "schema_version": LLMO_SCHEMA_VERSION,
        "definition": "LLMO is parseability and evidence alignment, not model-memory or ATS-score manipulation.",
        "evidence_nodes": nodes,
        "jd_anchors": anchors,
        "cross_material": cross_material,
        "positioning_plan": {
            "summary": "Put identity, target role and the strongest two JD-supported facts first.",
            "experience": "Put the strongest mapped result first in each relevant role; keep every bullet self-contained.",
            "cover_letter": "Open with role/company, then use the first three mapped evidence IDs before the close.",
            "application_email": "Use the same evidence order as the CV and cover letter; do not include internal notes.",
        },
        "parseability_contract": {
            "pdf_text_required": True,
            "single_column": True,
            "avoid": ["images for key facts", "text boxes", "headers/footers for contact details", "hidden text", "keyword stuffing"],
            "standard_sections": [
                "PROFESSIONAL SUMMARY",
                "CORE EXPERTISE",
                "PROFESSIONAL EXPERIENCE",
                "EDUCATION",
                "QUALIFICATIONS & LANGUAGES",
            ],
            "engine": "libreoffice_headless",
            "metrics_are_internal": True,
        },
    }


def audit_plain_text(
    text: str,
    *,
    kind: str = "cv",
    expected_contact_tokens: list[str] | None = None,
) -> dict[str, Any]:
    """Audit extracted text; intentionally reports engineering metrics, not ATS scores."""
    value = str(text or "")
    upper = value.upper()
    sections = [
        "PROFESSIONAL SUMMARY",
        "CORE EXPERTISE",
        "PROFESSIONAL EXPERIENCE",
        "EDUCATION",
        "QUALIFICATIONS & LANGUAGES",
    ]
    found = [section for section in sections if section in upper]
    order = [upper.find(section) for section in found]
    order_ok = order == sorted(order)
    contacts = [token for token in (expected_contact_tokens or []) if token and token in value]
    sentence_like = [line.strip() for line in value.splitlines() if line.strip()]
    self_contained = sum(1 for line in sentence_like if len(line) >= 20 and not re.match(r"^(above|same|as noted|如上|同上)", line, re.I))
    parse_completeness = round(
        (len(found) / len(sections) if kind == "cv" else min(1.0, len(value) / 500)) * 0.7
        + (min(1.0, len(contacts) / max(1, len(expected_contact_tokens or ["x"]))) * 0.3),
        2,
    )
    return {
        "schema_version": LLMO_SCHEMA_VERSION,
        "kind": kind,
        "parse_completeness": parse_completeness,
        "sections_found": found,
        "section_order": "passed" if order_ok else "review",
        "contact_tokens_found": contacts,
        "self_contained_line_ratio": round(self_contained / max(1, len(sentence_like)), 2),
        "text_layer": bool(value.strip()),
        "unsupported_claims": [],
        "position_priority_check": "review_required",
        "human_review_required": not bool(value.strip()) or (kind == "cv" and len(found) < 3) or not order_ok,
        "metrics_note": "Internal QA indicators; not an ATS score or hiring prediction.",
    }
