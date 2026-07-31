from tools.job_materials.llmo import (
    audit_plain_text,
    build_evidence_nodes,
    build_llmo_contract,
)
from tools.job_materials.paths import find_latest_master_docx, is_archived_path
from tools.job_materials.tailor import build_tailored_payload


def _base():
    return {
        "base_id": "A",
        "label": "Operations",
        "bullets": [
            "Built and monitored an automated operations workflow with review checkpoints.",
            "Improved reporting quality by coordinating implementation with stakeholder teams.",
        ],
        "factcheck": {"status": "passed"},
    }


def test_evidence_nodes_are_stable_and_have_claim_boundaries():
    first = build_evidence_nodes(_base())
    second = build_evidence_nodes(_base())

    assert [node["evidence_id"] for node in first] == [node["evidence_id"] for node in second]
    assert first[0]["fact_status"] == "fact_verified"
    assert first[0]["forbidden_inference"]
    assert first[0]["metrics"] == []


def test_llmo_contract_links_jd_anchors_across_material_views():
    contract = build_llmo_contract(
        jd=(
            "Experience in developing and monitoring operational programmes. "
            "Coordinate implementation with business teams and improve reporting quality."
        ),
        focus=["process_design_and_monitoring", "stakeholder_partnership"],
        base=_base(),
        summary="Operations analyst with workflow delivery experience.",
        bullets=_base()["bullets"],
        role="Operations Analyst",
        company="Acme",
    )

    assert contract["schema_version"] == 1
    assert len(contract["evidence_nodes"]) == 2
    assert {"cv", "cover_letter", "application_email"} <= set(contract["cross_material"]["materials"])
    assert contract["cross_material"]["materials"]["cover_letter"]["evidence_ids"]
    assert all(anchor["status"] in {"covered", "partial", "uncovered", "prohibited_to_claim"} for anchor in contract["jd_anchors"])


def test_unmatched_required_anchor_is_prohibited_to_claim():
    contract = build_llmo_contract(
        jd="Required: professional license and ten years of experience.",
        focus=["licensing_and_qualifications"],
        base=_base(),
        summary="Operations analyst.",
        bullets=_base()["bullets"],
        role="Operations Analyst",
        company="Acme",
    )

    assert contract["jd_anchors"][0]["status"] == "prohibited_to_claim"
    assert contract["cross_material"]["claim_policy"]["human_review_required"] is True


def test_tailor_payload_exposes_llmo_and_email_contract():
    payload = build_tailored_payload(
        base=_base(),
        job_title="Operations Analyst",
        company="Acme",
        jd_text="Build and monitor operational workflows with stakeholder teams.",
        company_research={
            "nature": "Operations technology company",
            "business": "Workflow software",
            "role_priorities": ["Monitor operational workflows"],
            "verified_signals": [{"claim": "Acme builds workflow software", "source_url": "https://example.com/about"}],
            "interest_angles": ["Interest in reliable operations tooling"],
        },
    )

    assert payload["llmo"]["evidence_nodes"]
    assert payload["llmo"]["jd_anchors"]
    assert payload["application_email_blueprint"]["required_slots"]
    assert "cross_material_contract" in payload["low_model_contract"]["required_order"]


def test_plain_text_audit_is_explicitly_not_an_ats_score():
    result = audit_plain_text(
        "PROFESSIONAL SUMMARY\nCORE EXPERTISE\nPROFESSIONAL EXPERIENCE\nEDUCATION\n"
        "QUALIFICATIONS & LANGUAGES\nuser@example.com",
        expected_contact_tokens=["user@example.com"],
    )

    assert result["text_layer"] is True
    assert result["parse_completeness"] == 1.0
    assert "ATS score" in result["metrics_note"]


def test_archive_paths_are_not_active_master_candidates(tmp_path):
    folder = tmp_path / "JobSearch_2026" / "01_Masters" / "A_track"
    (folder / "_archive" / "2026-07-31").mkdir(parents=True)
    (folder / "_archive" / "2026-07-31" / "master_old_v99.docx").write_bytes(b"old")
    folder.mkdir(parents=True, exist_ok=True)
    assert is_archived_path(folder / "_archive" / "2026-07-31" / "master_old_v99.docx")
    assert find_latest_master_docx("A", tmp_path / "JobSearch_2026") is None
