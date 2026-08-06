import csv
import json

from tools.fresh_24h import two_pass_score
from tools.fresh_24h.careerops_quickscore import score_job
from tools.fresh_24h.jd_cache import save_jd_cache


def _profile():
    return {
        "core_keywords": ["operations"],
        "evidence_keywords": ["automation"],
        "preferred_industry_keywords": ["technology"],
        "track_mapping": {"A": "Operations"},
    }


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_scored_artifact_reuse_requires_source_profile_and_jd_inputs(tmp_path):
    source = tmp_path / "fresh_24h_2026-08-06.csv"
    scored = tmp_path / "fresh_24h_2026-08-06_twopass_scored.csv"
    raw_rows = [
        {
            "title": "Operations Analyst",
            "company": "Acme",
            "source": "jobsdb",
            "url": "https://hk.jobsdb.com/job/123456789",
            "teaser": "Automate operations workflows.",
        }
    ]
    _write_csv(source, raw_rows)
    _write_csv(
        scored,
        [
            {
                "岗位编号": "A0",
                "职位": "Operations Analyst",
                "公司": "Acme",
                "来源": "JobsDB",
                "链接": raw_rows[0]["url"],
                "CareerOps分数": "4.00",
            }
        ],
    )
    full_jd = "Full JD text for the artifact fingerprint. " * 20
    save_jd_cache(raw_rows[0]["url"], full_jd, source="browser_jobsdb", root=tmp_path)
    profile = _profile()
    meta = {
        "artifact": two_pass_score.build_scored_artifact_metadata(
            source_csv=source,
            profile=profile,
            gate_pass1=3.3,
            min_final=3.3,
            max_deep=20,
            jd_fingerprints={
                raw_rows[0]["url"]: two_pass_score.jd_fingerprint(full_jd),
            },
            repo=tmp_path,
        )
    }
    meta_path = scored.with_suffix(".json")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    reused = two_pass_score.load_reusable_scored_artifact(
        source,
        repo=tmp_path,
        profile=profile,
        min_score=3.3,
        max_deep=20,
    )

    assert reused is not None
    rows, loaded_meta = reused
    assert rows[0]["岗位编号"] == "A0"
    assert loaded_meta["artifact"]["source_csv_sha256"]

    source.write_text(source.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8")
    assert (
        two_pass_score.load_reusable_scored_artifact(
            source,
            repo=tmp_path,
            profile=profile,
            min_score=3.3,
            max_deep=20,
        )
        is None
    )


def test_two_pass_skips_inter_job_delay_for_jd_cache_hits(monkeypatch, tmp_path):
    sleeps = []

    def cached_deep(hit, *, repo):
        hit["_enrich"] = {"mode": "cache", "ok": True}
        hit["_deep_jd_full"] = "Cached full JD text. " * 20
        return hit["_deep_jd_full"], "deep"

    monkeypatch.setattr(two_pass_score, "deep_enrich_hit", cached_deep)
    monkeypatch.setattr(two_pass_score.time, "sleep", sleeps.append)

    rows, _ = two_pass_score.run_two_pass(
        [
            {"title": "Operations Analyst", "company": "Acme", "url": "https://example.com/1", "teaser": "operations"},
            {"title": "Operations Manager", "company": "Acme", "url": "https://example.com/2", "teaser": "operations"},
        ],
        repo=tmp_path,
        gate_pass1=0.0,
        min_final=0.0,
        max_deep=2,
        sleep_s=2.0,
        drop_below_final=False,
    )

    assert len(rows) == 2
    assert sleeps == []


def test_two_pass_loads_profile_once_and_passes_it_to_each_score(monkeypatch, tmp_path):
    profile = _profile()
    loads = []
    received = []

    monkeypatch.setattr(
        two_pass_score,
        "load_scoring_profile",
        lambda repo: loads.append(repo) or profile,
    )

    def score_once(hit, teaser, **kwargs):
        received.append(kwargs["profile"])
        return score_job(
            title=hit.get("title", ""),
            company=hit.get("company", ""),
            teaser=teaser,
            profile=kwargs["profile"],
            repo=tmp_path,
        )

    monkeypatch.setattr(two_pass_score, "score_hit", score_once)

    two_pass_score.run_two_pass(
        [
            {"title": "Operations Analyst", "company": "Acme", "url": "https://example.com/1", "teaser": "operations"},
            {"title": "Operations Manager", "company": "Acme", "url": "https://example.com/2", "teaser": "operations"},
        ],
        repo=tmp_path,
        gate_pass1=0.0,
        min_final=0.0,
        max_deep=0,
        sleep_s=0.0,
        drop_below_final=False,
    )

    assert len(loads) == 1
    assert received
    assert all(value is profile for value in received)
