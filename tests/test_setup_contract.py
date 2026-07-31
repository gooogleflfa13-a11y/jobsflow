from tools.setup_contract import (
    BASE_TRACKER_COLUMNS,
    build_setup_design_request,
    resolve_setup_design,
)


def _fallback():
    return {
        "track_mapping": {
            "A": "Core",
            "B": "Adjacent",
            "C": "Operations",
            "D": "Analysis",
            "E": "Specialist",
            "F": "Other",
        },
        "extra_columns": [],
        "relevance_keywords": ["product", "operations", "analysis"],
        "adjacent_keywords": ["project"],
        "track_rules": [],
        "scoring_weights": {
            "resume": 0.35,
            "eligibility": 0.20,
            "direction": 0.20,
            "industry": 0.10,
            "work": 0.10,
            "pay": 0.05,
        },
    }


def test_setup_request_gives_low_model_exact_schema_contract():
    request = build_setup_design_request(
        intent="Product operations roles with no evening shifts",
        resume_keywords=["workflow", "analytics", "stakeholder"],
        fallback=_fallback(),
    )

    assert request["model_contract"]["next_action"] == "propose_setup_design"
    assert request["model_contract"]["do_not_infer_missing_values"] is True
    assert request["limits"]["max_extra_columns"] == 8
    assert set(request["required_output"]["track_mapping"]["required_keys"]) == set(
        "ABCDEF"
    )
    assert "no evening shifts" in request["inputs"]["job_search_intent"]
    assert request["required_output"]["industry_context"]["sources_required"] is True


def test_valid_model_schema_can_customize_tracker_by_industry_and_constraints():
    proposal = {
        "track_mapping": {
            "A": "Product Operations",
            "B": "Business Operations",
            "C": "Program Management",
            "D": "Data Operations",
            "E": "Customer Operations",
            "F": "Other",
        },
        "extra_columns": [
            {
                "name": "轮班要求",
                "type": "text",
                "description": "Whether the role requires evening or weekend shifts",
            },
            {
                "name": "SQL要求",
                "type": "text",
                "description": "Required SQL proficiency",
            },
        ],
        "relevance_keywords": ["product operations", "business operations", "program"],
        "adjacent_keywords": ["analytics", "customer success"],
        "track_rules": [
            {"letter": "A", "patterns": ["product operations"]},
            {"letter": "D", "patterns": ["data operations", "analytics"]},
        ],
        "scoring_weights": {
            "resume": 0.30,
            "eligibility": 0.20,
            "direction": 0.20,
            "industry": 0.10,
            "work": 0.15,
            "pay": 0.05,
        },
        "industry_context": {
            "target_industry": "Technology operations",
            "common_requirements": ["SQL literacy", "cross-functional delivery"],
            "source_urls": ["https://example.org/industry-guide"],
            "uncertainties": [],
        },
    }

    result = resolve_setup_design(proposal, fallback=_fallback())

    assert result["source"] == "model_proposal"
    assert result["ready"] is True
    assert result["design"]["track_mapping"]["A"] == "Product Operations"
    assert result["design"]["extra_columns"][0]["name"] == "轮班要求"
    assert result["design"]["industry_context"]["target_industry"] == "Technology operations"
    assert not ({column["name"] for column in result["design"]["extra_columns"]} & set(BASE_TRACKER_COLUMNS))


def test_invalid_low_model_schema_falls_back_without_polluting_product():
    proposal = {
        "track_mapping": {"A": "Only one track"},
        "extra_columns": [
            {"name": "职位", "type": "shell", "description": "overwrite required"}
        ],
        "relevance_keywords": [],
        "scoring_weights": {"resume": 9},
    }

    result = resolve_setup_design(proposal, fallback=_fallback())

    assert result["source"] == "deterministic_fallback"
    assert result["ready"] is False
    assert result["validation_errors"]
    assert result["design"]["track_mapping"]["A"] == "Core"
