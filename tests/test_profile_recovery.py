import json

from tools.fresh_24h.careerops_quickscore import load_scoring_profile, score_job
from tools.profile_recovery import repair_scoring_profile


def _write_private_profile(root):
    profile = root / "JobSearch_2026" / "00_Profile"
    profile.mkdir(parents=True)
    (profile / "resume_runtime").mkdir()
    (profile / "resume_runtime" / "resume.txt").write_text(
        "Built Python APIs and automated deployment checks for payment services.\n",
        encoding="utf-8",
    )
    (profile / "fact_evidence.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "evidence_id": "EVID-001",
                        "claim": "Built Python APIs and automated deployment checks for payment services.",
                        "allowed_phrasing": ["Built Python APIs", "automated deployment checks"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (profile / "queries.json").write_text(
        json.dumps(
            {
                "scoring_profile": {
                    "domain": "technology",
                    "core_keywords": ["backend", "platform"],
                    "adjacent_keywords": ["cloud"],
                    "evidence_keywords": [],
                    "preferred_industry_keywords": [],
                    "weights": {"resume": 0.35, "eligibility": 0.20, "direction": 0.20, "industry": 0.10, "work": 0.10, "pay": 0.05},
                },
                "queries": [
                    {"id": "backend", "terms": {"linkedin": "backend fintech engineer", "jobsdb": "backend fintech", "ctgoodjobs": "backend fintech"}}
                ],
            }
        ),
        encoding="utf-8",
    )
    return profile


def test_recovery_rebuilds_missing_keywords_from_private_sources(tmp_path):
    profile_dir = _write_private_profile(tmp_path)

    profile, health, changed = repair_scoring_profile(tmp_path)

    assert changed is True
    assert health["status"] == "ready"
    assert "python" in profile["evidence_keywords"]
    assert "technology" in profile["preferred_industry_keywords"]
    assert "fintech" in profile["preferred_industry_keywords"]
    saved = json.loads((profile_dir / "queries.json").read_text(encoding="utf-8"))
    assert saved["profile_recovery"]["status"] == "repaired"


def test_recovered_profile_restores_score_separation(tmp_path, monkeypatch):
    _write_private_profile(tmp_path)
    monkeypatch.setenv("JOBSEARCH_ROOT", str(tmp_path / "JobSearch_2026"))

    profile = load_scoring_profile()
    matching = score_job(
        title="Backend Engineer",
        company="Fintech Platform",
        teaser="Build Python APIs and automated deployment checks.",
        profile=profile,
    )
    unrelated = score_job(
        title="Litigation Paralegal",
        company="General Services",
        teaser="Support court filings.",
        profile=profile,
    )

    assert matching.score > unrelated.score
    assert matching.resume_ver != unrelated.resume_ver or matching.score != unrelated.score
    assert profile["_profile_health"]["status"] == "ready"


def test_incomplete_profile_is_capped_and_explains_why():
    result = score_job(
        title="Backend Engineer",
        company="Acme",
        teaser="Build reliable Python services.",
        profile={
            "core_keywords": ["backend"],
            "evidence_keywords": [],
            "preferred_industry_keywords": [],
            "_profile_health": {"status": "incomplete"},
        },
    )

    assert result.score <= 2.9
    assert "评分配置不完整" in result.reason
