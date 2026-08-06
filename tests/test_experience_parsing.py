from pathlib import Path

import pytest

from tools.experience_parsing import parse_experience_requirement
from tools.fresh_24h.careerops_quickscore import score_job
from tools.fresh_24h.job_assessment import build_job_assessment


PROFILE = {
    "core_keywords": ["operations"],
    "evidence_keywords": ["automation"],
    "preferred_industry_keywords": ["technology"],
    "max_relevant_years": 3,
    "weights": {
        "resume": 0.35,
        "eligibility": 0.20,
        "direction": 0.20,
        "industry": 0.10,
        "work": 0.10,
        "pay": 0.05,
    },
}


@pytest.mark.parametrize(
    "phrase",
    ["2 to 5 years", "3-5 years", "3 - 5 years", "2至5年相关经验"],
)
def test_jd_experience_range_uses_lower_bound_for_scoring(phrase):
    result = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser=f"Minimum {phrase} experience in operations and automation.",
        profile=PROFILE,
    )

    assert "相关年限要求超出已确认经历cap3.4" not in result.cap_notes
    assert result.experience_requirement.startswith(("2", "3"))


def test_assessment_uses_the_same_lower_bound_as_the_scorer():
    phrase = "Minimum 2 to 5 years of relevant experience"
    score = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser=phrase,
        profile=PROFILE,
    )
    assessment = build_job_assessment(
        repo=Path("/tmp"),
        job_id="A0-001",
        title="Operations Analyst",
        company="Acme",
        source="jobsdb",
        url="https://hk.jobsdb.com/job/experience-range-regression",
        jd_text=phrase,
        jd_depth="deep",
        profile=PROFILE,
        score=score,
    )

    experience_gaps = [item for item in assessment["gaps"] if item.get("kind") == "experience"]
    assert experience_gaps
    assert "JD 要求 2 年" in experience_gaps[0]["reason"]


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [("5+ years", 5), ("8 years PQE", 8), ("至少三年相关经验", 3)],
)
def test_single_year_requirements_keep_their_minimum_value(phrase, expected):
    result = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser=phrase,
        profile=PROFILE,
    )

    assert result.experience_requirement.startswith(str(expected))


@pytest.mark.parametrize("phrase", ["5年经验要求", "5年工作经验者优先"])
def test_chinese_experience_suffix_can_be_followed_by_more_jd_text(phrase):
    parsed = parse_experience_requirement(phrase)

    assert parsed is not None
    assert parsed.minimum_years == 5
