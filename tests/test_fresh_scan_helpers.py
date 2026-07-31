import csv
import json

from tools.fresh_24h.careerops_quickscore import (
    SHEET_HEADERS,
    company_brief,
    score_job,
)
from tools.fresh_24h.fresh_24h_scan import (
    JobHit,
    apply_recency,
    apply_rules,
    card_to_hit,
    has_fatal_portal_errors,
    now_utc,
)
from tools.fresh_24h import two_pass_score
from tools.fresh_24h.local_tracker import merge_scored_rows
from tools.fresh_24h.tracker_schema import merge_tracker_headers


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


def test_linkedin_date_only_is_soft_flagged_not_rejected_in_temp_window():
    today = now_utc().strftime("%Y-%m-%d")
    hit = card_to_hit(
        {
            "id": "li-1",
            "title": "Operations Analyst",
            "company": "Acme",
            "location": "Hong Kong",
            "date": today,
            "url": "https://www.linkedin.com/jobs/view/123456789/",
        },
        source="linkedin",
        query_id="core",
        track_hint="A",
    )

    apply_recency(hit, max_hours=2, portal="linkedin", jobsdb_client_hours=None)

    assert hit.date_precision == "day"
    assert hit.decision == "new"
    assert "date_precision_day" in hit.soft_flags


def test_setup_tracker_schema_columns_are_consumed_by_exporters(tmp_path):
    schema = {
        "columns": [
            {"name": "岗位编号"},
            {"name": "行业证书"},
            {"name": "轮班要求"},
        ]
    }
    schema_path = tmp_path / "JobSearch_2026" / "02_Tracker" / "tracker_schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

    headers = merge_tracker_headers(["岗位编号", "职位"], tmp_path)

    assert headers == ["岗位编号", "职位", "行业证书", "轮班要求"]


def test_local_tracker_merge_writes_main_csv_and_custom_columns(tmp_path):
    schema_path = tmp_path / "JobSearch_2026" / "02_Tracker" / "tracker_schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text(
        json.dumps({"columns": [{"name": "岗位编号"}, {"name": "轮班要求"}]}),
        encoding="utf-8",
    )

    tracker, added = merge_scored_rows(
        tmp_path,
        [
            {
                "岗位编号": "A0-004",
                "职位": "Operations Analyst",
                "公司": "Acme",
                "链接": "https://example.com/jobs/4",
                "CareerOps分数": "4.20",
            }
        ],
        base_headers=SHEET_HEADERS,
        mode="temp",
    )

    with tracker.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert added == 1
    assert rows[0]["岗位编号"] == "A0-004"
    assert "轮班要求" in rows[0]
    assert rows[0]["本轮新增"] == "是"
