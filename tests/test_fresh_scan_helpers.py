from tools.fresh_24h.careerops_quickscore import (
    SHEET_HEADERS,
    company_brief,
    score_job,
)
from tools.fresh_24h.fresh_24h_scan import JobHit, apply_rules, has_fatal_portal_errors
from tools.fresh_24h import two_pass_score


def test_portal_errors_are_fatal_only_when_no_new_jobs():
    errors = [{"portal": "linkedin", "error": "timeout"}]

    assert has_fatal_portal_errors(errors, 0) is True
    assert has_fatal_portal_errors(errors, 1) is False
    assert has_fatal_portal_errors([], 0) is False


def test_company_brief_extracts_about_section_without_mapping_text():
    teaser = (
        "Responsibilities include transaction monitoring. "
        "About Us: Acme Pay is a Hong Kong fintech providing cross-border "
        "payment services to SMEs. Requirements: one year of experience."
    )

    brief = company_brief("Acme Pay", teaser)

    assert brief.startswith("Acme Pay，")
    assert "Hong Kong fintech" in brief
    assert "Requirements" not in brief
    assert "简历版本" not in brief


def test_company_brief_marks_missing_background_as_unverified():
    brief = company_brief("Acme Legal", "Draft contracts and support counsel.")

    assert brief == "Acme Legal；当前职位页未提供明确公司背景，建议结合官网核实。"


def test_scan_relevance_uses_private_industry_config_not_legal_default():
    cfg = {
        "relevance_keywords": ["software", "backend", "python", "platform"],
        "hard_reject_title_patterns": [],
        "soft_flag_patterns": {},
    }
    tech = JobHit(
        id="1",
        title="Backend Software Engineer",
        company="Acme",
        source="jobsdb",
        location="Hong Kong",
        salary="",
        url="https://example.com/1",
        posted_at=None,
        teaser="Build Python platform services.",
        query_id="backend",
        track_hint="A",
    )
    legal = JobHit(
        id="2",
        title="Litigation Paralegal",
        company="Acme",
        source="jobsdb",
        location="Hong Kong",
        salary="",
        url="https://example.com/2",
        posted_at=None,
        teaser="Support legal case work.",
        query_id="backend",
        track_hint="F",
    )

    apply_rules(tech, cfg)
    apply_rules(legal, cfg)

    assert tech.decision == "new"
    assert legal.reject_reason == "outside_configured_search_scope"


def test_generic_scorer_uses_profile_keywords_and_generic_headers():
    profile = {
        "core_keywords": ["software", "backend", "python", "platform"],
        "adjacent_keywords": ["cloud", "data"],
        "evidence_keywords": ["python", "api", "distributed systems"],
        "preferred_industry_keywords": ["saas", "technology"],
        "track_mapping": {"A": "Backend", "F": "Other"},
        "track_rules": [{"letter": "A", "patterns": ["backend", "api", "platform"]}],
    }

    tech = score_job(
        title="Backend Software Engineer",
        company="Acme SaaS",
        teaser="Build Python APIs and distributed platform services.",
        profile=profile,
    )
    unrelated = score_job(
        title="Litigation Paralegal",
        company="Law Firm",
        teaser="Support court filings.",
        profile=profile,
    )

    assert tech.score > unrelated.score
    assert tech.resume_ver == "A"
    assert "语言要求" in SHEET_HEADERS
    assert "PCLL工时风险" not in SHEET_HEADERS


def test_jobsdb_deep_enrichment_reuses_url_cache(monkeypatch, tmp_path):
    cached = "Full JobsDB description with enough detail for deep scoring."
    monkeypatch.setattr(
        two_pass_score,
        "_load_cache",
        lambda url, repo: (cached, {"source": "browser_jobsdb"}),
    )
    hit = {
        "url": "https://hk.jobsdb.com/job/93660409",
        "teaser": "short teaser",
    }

    text, depth = two_pass_score.deep_enrich_hit(
        hit,
        repo=tmp_path,
        use_browser=False,
    )

    assert text == cached
    assert depth == "deep"
    assert hit["_deep_jd_full"] == cached
