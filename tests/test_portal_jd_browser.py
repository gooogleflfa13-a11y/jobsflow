import json

from tools.fresh_24h import portal_jd_browser as browser
from tools.fresh_24h.jd_cache import jd_cache_path, load_jd_cache


def _failure(reason="waf"):
    return browser.JdFetchResult(
        ok=False,
        url="https://hk.jobsdb.com/job/123",
        portal="jobsdb",
        fail_reason=reason,
    )


def _success():
    return browser.JdFetchResult(
        ok=True,
        url="https://hk.jobsdb.com/job/123",
        portal="jobsdb",
        text="A complete job description. " * 20,
        chars=600,
    )


def test_retry_failure_then_success_writes_cache_and_diagnostics(tmp_path, monkeypatch):
    results = iter([_failure("waf"), _success()])
    sleeps = []
    monkeypatch.setattr(browser, "_fetch_jd_body_once", lambda *args, **kwargs: next(results))
    monkeypatch.setattr(browser.random, "uniform", lambda low, high: 0.0)
    monkeypatch.setattr(browser.time, "sleep", sleeps.append)

    result = browser.fetch_jd_body(
        "https://hk.jobsdb.com/job/123",
        retry=2,
        retry_delay=30,
        cache_root=tmp_path,
    )

    assert result.ok is True
    assert result.attempts == 2
    assert result.retried == 1
    assert result.last_reason == "waf"
    assert sleeps == [30]
    cached, meta = load_jd_cache(result.url, tmp_path)
    assert cached == result.text
    assert meta["cache_key"] == jd_cache_path(result.url, tmp_path).stem


def test_retry_zero_preserves_single_attempt_behavior(monkeypatch):
    calls = []

    def fake_once(*args, **kwargs):
        calls.append(kwargs)
        return _failure("timeout")

    monkeypatch.setattr(browser, "_fetch_jd_body_once", fake_once)
    result = browser.fetch_jd_body("https://hk.jobsdb.com/job/123", retry=0, retry_delay=0)

    assert len(calls) == 1
    assert result.ok is False
    assert result.fail_reason == "timeout"
    assert result.attempts == 1
    assert result.retried == 0
    assert result.last_reason == "timeout"


def test_persistent_failure_reports_attempt_count_and_last_reason(monkeypatch):
    calls = []

    def fake_once(*args, **kwargs):
        calls.append(1)
        return _failure("waf")

    monkeypatch.setattr(browser, "_fetch_jd_body_once", fake_once)
    result = browser.fetch_jd_body(
        "https://hk.jobsdb.com/job/123",
        retry=2,
        retry_delay=0,
    )

    assert len(calls) == 3
    assert result.ok is False
    assert result.fail_reason == "waf"
    assert result.attempts == 3
    assert result.retried == 1
    assert result.last_reason == "waf"


def test_missing_storage_state_is_silently_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTAL_JD_STORAGE_STATE", str(tmp_path / "missing.json"))
    assert browser.resolve_storage_state(None, "jobsdb") is None


def test_cli_parses_retry_flags_and_emits_json(monkeypatch, capsys):
    calls = []

    def fake_fetch(url, **kwargs):
        calls.append((url, kwargs))
        return _success()

    monkeypatch.setattr(browser, "fetch_jd_body", fake_fetch)
    assert browser.main(
        [
            "--url",
            "https://hk.jobsdb.com/job/123",
            "--retry",
            "0",
            "--retry-delay",
            "0",
            "--json",
        ]
    ) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert calls[0][1]["retry"] == 0
    assert calls[0][1]["retry_delay"] == 0
    assert calls[0][1]["cache_root"] == browser._default_cache_root()
