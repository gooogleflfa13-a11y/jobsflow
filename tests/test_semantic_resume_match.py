import json

from tools.fresh_24h.careerops_quickscore import score_job
from tools.fresh_24h import semantic_match_agent


def _write_semantic_workspace(root, *, level="low"):
    profile = root / "00_Profile" / "bases_runtime"
    profile.mkdir(parents=True)
    (profile / "A.json").write_text(
        json.dumps(
            {
                "base_id": "A",
                "label": "Operations",
                "facts_anchor": ["Built and monitored an operations workflow."],
                "capability_upper": [
                    {"capability": "Compliance programme design", "not_experience": True}
                ],
                "forbidden_claims": ["Do not claim direct compliance programme ownership."],
                "semantic_profile": {
                    "upper_bound_level": level,
                    "upper_only_score_cap": {"low": 3.5, "medium": 4.0, "high": 4.5}[level],
                    "transfer_score_cap": {"low": 4.0, "medium": 4.5, "high": 5.0}[level],
                },
                "factcheck": {"status": "passed"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "02_Tracker").mkdir(parents=True)


def _profile():
    return {
        "core_keywords": ["operations"],
        "adjacent_keywords": [],
        "evidence_keywords": ["workflow"],
        "preferred_industry_keywords": [],
        "track_mapping": {"A": "Operations"},
        "track_rules": [],
        "_profile_health": {"status": "ready"},
    }


def test_deep_score_creates_pending_but_teaser_does_not(tmp_path, monkeypatch):
    _write_semantic_workspace(tmp_path)
    monkeypatch.setenv("JOBSEARCH_ROOT", str(tmp_path))

    teaser = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Monitor operational programmes.",
        track_hint="A",
        jd_depth="teaser",
        profile=_profile(),
    )
    assert teaser.semantic_note == ""
    assert not list((tmp_path / "02_Tracker" / "semantic_matches").glob("**/*.json"))

    deep = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Develop and monitor a compliance programme with business stakeholders.",
        track_hint="A",
        jd_depth="deep",
        profile=_profile(),
    )
    pending = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "02_Tracker" / "semantic_matches" / "pending").glob("*.json")
    ]
    assert deep.semantic_note == ""
    resume_tasks = [task for task in pending if task.get("task") == "semantic_resume_match"]
    assert len(resume_tasks) == 1
    task = resume_tasks[0]
    assert "事实基线" in task["profile"]
    assert "能力上沿" in task["profile"]
    assert task["semantic_profile"]["upper_bound_level"] == "low"


def test_completed_upper_only_verdict_obeys_calibration_cap(tmp_path, monkeypatch):
    _write_semantic_workspace(tmp_path, level="low")
    monkeypatch.setenv("JOBSEARCH_ROOT", str(tmp_path))
    score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Develop and monitor a compliance programme.",
        track_hint="A",
        jd_depth="deep",
        profile=_profile(),
    )
    pending = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "02_Tracker" / "semantic_matches" / "pending").glob("*.json")
    ]
    key = next(task["key"] for task in pending if task.get("task") == "semantic_resume_match")

    assert semantic_match_agent.cmd_complete(
        key, 5.0, "Only a potential transfer from the profile upper bound.", "upper_only"
    ) == 0
    verdict = json.loads(
        (tmp_path / "02_Tracker" / "semantic_matches" / "done" / f"{key}.json").read_text(encoding="utf-8")
    )
    assert verdict["resume_match"] == 3.5
    assert verdict["basis"] == "upper_only"

    rescored = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Develop and monitor a compliance programme.",
        track_hint="A",
        jd_depth="deep",
        profile=_profile(),
    )
    assert rescored.semantic_note.startswith("语义简历匹配(A)[upper_only]")
    assert "语义简历匹配" in rescored.reason


def test_direct_verdict_is_not_limited_by_upper_bound(tmp_path, monkeypatch):
    _write_semantic_workspace(tmp_path, level="low")
    monkeypatch.setenv("JOBSEARCH_ROOT", str(tmp_path))
    score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Monitor the operations workflow.",
        track_hint="A",
        jd_depth="deep",
        profile=_profile(),
    )
    pending = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "02_Tracker" / "semantic_matches" / "pending").glob("*.json")
    ]
    key = next(task["key"] for task in pending if task.get("task") == "semantic_resume_match")
    semantic_match_agent.cmd_complete(key, 5.0, "Directly supported by the facts anchor.", "direct")
    rescored = score_job(
        title="Operations Analyst",
        company="Acme",
        teaser="Monitor the operations workflow.",
        track_hint="A",
        jd_depth="deep",
        profile=_profile(),
    )
    assert "[direct]" in rescored.semantic_note


def test_position_profile_task_returns_lane_and_company_brief(tmp_path, monkeypatch):
    _write_semantic_workspace(tmp_path)
    monkeypatch.setenv("JOBSEARCH_ROOT", str(tmp_path))
    profile = _profile()

    score_job(
        title="Operations Analyst",
        company="Acme Pay",
        teaser="A fintech providing cross-border payment infrastructure.",
        track_hint="A",
        jd_depth="deep",
        jd_url="https://example.com/jobs/acme-1",
        jd_full="A fintech providing cross-border payment infrastructure. " * 20,
        profile=profile,
    )
    tasks = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (tmp_path / "02_Tracker" / "semantic_matches" / "pending").glob("*.json")
    ]
    position = next(task for task in tasks if task.get("task") == "position_profile")
    assert position["jd_cache"]["cache_key"]
    assert position["jd_cache"]["chars"] > 100

    assert semantic_match_agent.cmd_complete(
        position["key"],
        0.0,
        "公司业务性质与岗位范围共同决定分类",
        "upper_only",
        lane="A",
        company_brief="Acme Pay 是提供跨境支付基础设施的金融科技公司",
    ) == 0

    rescored = score_job(
        title="Operations Analyst",
        company="Acme Pay",
        teaser="A fintech providing cross-border payment infrastructure.",
        track_hint="A",
        jd_depth="deep",
        jd_url="https://example.com/jobs/acme-1",
        jd_full="A fintech providing cross-border payment infrastructure. " * 20,
        profile=profile,
    )
    assert rescored.resume_ver == "A"
    assert rescored.company_brief_override.startswith("Acme Pay")
