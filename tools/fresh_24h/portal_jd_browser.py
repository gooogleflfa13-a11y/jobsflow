#!/usr/bin/env python3
"""Fetch full job-description body via Playwright (JobsDB / CTgoodjobs / LinkedIn).

Solves the "no reliable JD body from portal APIs" gap for two-pass scoring.

Design:
  - Headless Chromium by default; optional channel=chrome / storage_state
  - Only used after pass-1 gate (callers decide)
  - Fail soft: return ok=False + stable fail_reason (waf|timeout|empty|error|blocked)
  - Retry WAF/timeout/empty failures with a bounded delay; reuse private storage state
  - Successful bodies are written to the shared URL-keyed JD cache
  - Does NOT auto-apply or auto-tailor

Usage:
  python3 tools/fresh_24h/portal_jd_browser.py --url 'https://hk.jobsdb.com/job/93633598'
  python3 tools/fresh_24h/portal_jd_browser.py --url '…' --out /tmp/jd.md
  python3 tools/fresh_24h/portal_jd_browser.py --url '…' --headed \
    --save-storage-state ~/.config/jobsearch/storage_state_jobsdb.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.job_urls import normalize_job_url  # noqa: E402

# Prefer longer body for pass-2 / materials
MAX_CHARS = 14000
MIN_BODY_CHARS = 280

WAF_MARKERS = (
    "just a moment",
    "attention required",
    "access denied",
    "cf-browser-verification",
    "checking your browser",
    "enable javascript and cookies",
    "captcha",
    "aws waf",
    "request blocked",
)

# Portal-specific selector candidates (first long enough wins)
SELECTORS: dict[str, list[str]] = {
    "jobsdb": [
        '[data-automation="jobAdDetails"]',
        '[data-automation="jobDescription"]',
        'div[data-automation="jobAdDetails"]',
        '[class*="job-description"]',
        '[class*="JobDescription"]',
        "article",
        "main",
    ],
    "ctgoodjobs": [
        ".job-detail-content",
        ".job-description",
        "#job-description",
        '[class*="job-detail"]',
        '[class*="jobDetail"]',
        "article",
        "main",
        ".content",
    ],
    "linkedin": [
        ".show-more-less-html__markup",
        ".description__text",
        "article.jobs-description",
        ".jobs-description__content",
        ".jobs-box__html-content",
        "main",
    ],
    "generic": [
        "article",
        "main",
        '[role="main"]',
        "#content",
        ".content",
    ],
}


@dataclass
class JdFetchResult:
    ok: bool
    url: str
    portal: str
    text: str = ""
    fail_reason: str | None = None
    selector: str | None = None
    title: str = ""
    chars: int = 0
    attempts: int = 1
    last_reason: str | None = None
    retried: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_portal(url: str) -> str:
    u = (url or "").lower()
    if "jobsdb.com" in u:
        return "jobsdb"
    if "ctgoodjobs.hk" in u:
        return "ctgoodjobs"
    if "linkedin.com" in u:
        return "linkedin"
    return "generic"


def _clean_text(text: str) -> str:
    t = re.sub(r"\r\n?", "\n", text or "")
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _looks_like_waf(title: str, body: str, html_snip: str) -> bool:
    blob = f"{title}\n{body[:2000]}\n{html_snip[:1500]}".lower()
    return any(m in blob for m in WAF_MARKERS)


RETRYABLE_REASONS = {"waf", "timeout", "empty"}
FAIL_REASONS = {"waf", "timeout", "empty", "error", "blocked"}


def _stable_fail_reason(reason: str | None) -> str:
    """Normalize internal Playwright errors to the public failure contract."""
    value = (reason or "error").strip().lower()
    if value in FAIL_REASONS:
        return value
    if "waf" in value or "captcha" in value or "verify" in value:
        return "waf"
    if "timeout" in value:
        return "timeout"
    if "empty" in value:
        return "empty"
    if "blocked" in value or "access denied" in value:
        return "blocked"
    return "error"


def default_storage_state_path(portal: str) -> Path:
    """Return the private, portal-specific default cookie state path."""
    safe_portal = portal if portal in {"jobsdb", "ctgoodjobs", "linkedin"} else "generic"
    return Path.home() / ".config" / "jobsearch" / f"storage_state_{safe_portal}.json"


def resolve_storage_state(storage_state: str | Path | None, portal: str) -> Path | None:
    """Resolve explicit/env/default state, silently ignoring missing files."""
    raw = storage_state or os.environ.get("PORTAL_JD_STORAGE_STATE")
    path = Path(raw).expanduser() if raw else default_storage_state_path(portal)
    return path if path.is_file() else None


def _safe_storage_path(path: str | Path) -> Path:
    """Ensure sensitive cookie state stays under the user's home directory."""
    resolved = Path(path).expanduser().resolve()
    home = Path.home().resolve()
    try:
        resolved.relative_to(home)
    except ValueError as exc:
        raise ValueError("storage state path must be inside the user home directory") from exc
    return resolved


def _largest_block(page) -> tuple[str, str]:
    """Fallback: longest text-ish block in the DOM."""
    try:
        blocks = page.evaluate(
            """() => {
              const tags = ['div','section','article','main'];
              const out = [];
              for (const tag of tags) {
                for (const el of document.querySelectorAll(tag)) {
                  const t = (el.innerText || '').trim();
                  if (t.length < 400) continue;
                  // skip nav/footer-ish
                  const idc = ((el.id||'') + ' ' + (el.className||'')).toLowerCase();
                  if (/nav|footer|header|cookie|modal|sidebar|related/.test(idc)) continue;
                  out.push({t, len: t.length, sel: tag + (el.id?('#'+el.id):'')});
                }
              }
              out.sort((a,b) => b.len - a.len);
              return out.slice(0, 3);
            }"""
        )
    except Exception:
        return "", ""
    if not blocks:
        return "", ""
    best = blocks[0]
    return _clean_text(best.get("t") or ""), str(best.get("sel") or "heuristic")


def _fetch_jd_body_once(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    storage_state: str | Path | None = None,
    channel: str | None = None,
    max_chars: int = MAX_CHARS,
    save_storage_state: str | Path | None = None,
) -> JdFetchResult:
    """Open job URL once in Playwright and extract description text."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return JdFetchResult(
            ok=False,
            url=url,
            portal=detect_portal(url),
            fail_reason="error",
        )

    raw = (url or "").strip()
    portal = detect_portal(raw)
    canon = normalize_job_url(raw, source=portal if portal != "generic" else "")
    if not canon:
        return JdFetchResult(ok=False, url=raw, portal=portal, fail_reason="empty")

    state = resolve_storage_state(storage_state, portal)
    # Prefer system Chrome on macOS — better CF pass-rate than stock chromium
    channel = channel or os.environ.get("PORTAL_JD_CHANNEL") or "chrome"

    def _launch(p):
        last_err = None
        for ch in ([channel] if channel else []) + [None]:
            try:
                kw: dict[str, Any] = {"headless": headless}
                if ch:
                    kw["channel"] = ch
                return p.chromium.launch(**kw)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(str(last_err))

    try:
        with sync_playwright() as p:
            try:
                browser = _launch(p)
            except Exception as e:
                return JdFetchResult(
                    ok=False,
                    url=canon,
                    portal=portal,
                    fail_reason="error",
                )

            ctx_kwargs: dict[str, Any] = {
                "locale": "en-HK",
                "viewport": {"width": 1280, "height": 900},
                "user_agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            }
            if state and Path(state).expanduser().is_file():
                ctx_kwargs["storage_state"] = str(Path(state).expanduser())

            context = browser.new_context(**ctx_kwargs)

            save_path = _safe_storage_path(save_storage_state) if save_storage_state else None

            def _save_context_state() -> None:
                if save_path is None:
                    return
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=str(save_path))
                except Exception:
                    # A cookie-save failure must not turn a valid JD into a
                    # fetch failure; the next run can still use the result.
                    pass

            # JD extraction is text-only: avoid downloading heavy assets.
            context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in {"image", "media", "font"}
                    else route.continue_()
                ),
            )
            page = context.new_page()
            try:
                page.goto(canon, wait_until="domcontentloaded", timeout=timeout_ms)
                # Cloudflare / WAF interstitial often needs a few seconds
                interactive_verification = (
                    not headless and save_path is not None and sys.stdin.isatty()
                )
                if interactive_verification:
                    print(
                        "提示：浏览器若显示人机验证，请在窗口中完成；"
                        "验证后页面会自动继续并保存会话。",
                        file=sys.stderr,
                    )
                wait_default = "120" if interactive_verification else "10"
                wait_cap = 120 if interactive_verification else 15
                waf_wait_seconds = min(
                    wait_cap,
                    max(
                        0,
                        int(os.environ.get("PORTAL_JD_WAF_WAIT_SECONDS", wait_default)),
                    ),
                )
                for _ in range(waf_wait_seconds):
                    title0 = (page.title() or "").lower()
                    try:
                        blen = len(page.inner_text("body") or "")
                    except Exception:
                        blen = 0
                    if "just a moment" not in title0 and blen > 600:
                        break
                    page.wait_for_timeout(1000)
                page.wait_for_timeout(800)

                # expand "see more" style buttons if present
                for label in (
                    "See more",
                    "Show more",
                    "显示更多",
                    "展開",
                    "展开",
                    "Read more",
                ):
                    try:
                        btn = page.get_by_role("button", name=re.compile(label, re.I))
                        if btn.count() > 0:
                            btn.first.click(timeout=1500)
                            page.wait_for_timeout(600)
                    except Exception:
                        pass

                title = page.title() or ""
                html_snip = ""
                try:
                    html_snip = page.content()[:2000]
                except Exception:
                    pass

                selectors = SELECTORS.get(portal, []) + SELECTORS["generic"]
                text = ""
                used = None
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if loc.count() <= 0:
                            continue
                        t = _clean_text(loc.first.inner_text(timeout=2500))
                        if len(t) >= MIN_BODY_CHARS:
                            text, used = t, sel
                            break
                    except Exception:
                        continue

                if len(text) < MIN_BODY_CHARS:
                    t2, used2 = _largest_block(page)
                    if len(t2) > len(text):
                        text, used = t2, used2 or used

                body_all = ""
                try:
                    body_all = _clean_text(page.inner_text("body") or "")
                except Exception:
                    pass

                # only treat as WAF if still short after wait
                if len(text) < MIN_BODY_CHARS and _looks_like_waf(
                    title, text or body_all, html_snip
                ):
                    _save_context_state()
                    browser.close()
                    return JdFetchResult(
                        ok=False,
                        url=canon,
                        portal=portal,
                        title=title,
                        fail_reason="waf",
                        chars=len(text),
                    )

                if len(text) < MIN_BODY_CHARS:
                    browser.close()
                    return JdFetchResult(
                        ok=False,
                        url=canon,
                        portal=portal,
                        title=title,
                        text=text[:500],
                        fail_reason="empty",
                        selector=used,
                        chars=len(text),
                    )

                if len(text) > max_chars:
                    text = text[:max_chars] + "\n…"

                _save_context_state()
                browser.close()
                return JdFetchResult(
                    ok=True,
                    url=canon,
                    portal=portal,
                    text=text,
                    title=title,
                    selector=used,
                    chars=len(text),
                )
            except Exception as e:
                try:
                    browser.close()
                except Exception:
                    pass
                msg = str(e).lower()
                reason = "timeout" if "timeout" in msg else "error"
                return JdFetchResult(
                    ok=False, url=canon, portal=portal, fail_reason=reason
                )
    except Exception as e:
        return JdFetchResult(
            ok=False, url=canon, portal=portal, fail_reason="error"
        )


def _default_cache_root() -> Path:
    configured = os.environ.get("JOBSEARCH_ROOT")
    return Path(configured).expanduser() if configured else REPO


def _write_success_cache(result: JdFetchResult, root: Path | None) -> None:
    if not result.ok or not result.text or root is None:
        return
    try:
        from tools.fresh_24h.jd_cache import save_jd_cache

        save_jd_cache(
            result.url,
            result.text,
            source=f"browser_{result.portal}",
            root=Path(root),
        )
    except (OSError, ValueError, TypeError, ImportError):
        # Cache failure must not discard a successfully fetched JD.
        pass


def fetch_jd_body(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    storage_state: str | Path | None = None,
    channel: str | None = None,
    max_chars: int = MAX_CHARS,
    retry: int = 2,
    retry_delay: float = 30.0,
    save_storage_state: str | Path | None = None,
    cache_root: Path | None = None,
) -> JdFetchResult:
    """Fetch a JD with bounded retries, session reuse and shared caching."""
    raw = (url or "").strip()
    portal = detect_portal(raw)
    try:
        retry = int(retry)
        retry_delay = float(retry_delay)
        timeout_ms = int(timeout_ms)
        if (
            retry < 0
            or not math.isfinite(retry_delay)
            or retry_delay < 0
            or timeout_ms <= 0
        ):
            raise ValueError
        # Keep each browser attempt bounded even when a caller supplies a
        # larger value; the retry budget remains explicit and observable.
        timeout_ms = min(timeout_ms, 60000)
        save_path = _safe_storage_path(save_storage_state) if save_storage_state else None
    except (TypeError, ValueError, OSError):
        return JdFetchResult(
            ok=False,
            url=raw,
            portal=portal,
            fail_reason="error",
            attempts=0,
            last_reason="error",
        )

    last_reason: str | None = None
    total = retry + 1
    for index in range(total):
        result = _fetch_jd_body_once(
            raw,
            headless=headless,
            timeout_ms=timeout_ms,
            storage_state=storage_state,
            channel=channel,
            max_chars=max_chars,
            save_storage_state=save_path,
        )
        if result.ok:
            result.attempts = index + 1
            result.retried = int(index > 0)
            result.last_reason = last_reason
            _write_success_cache(result, cache_root or _default_cache_root())
            return result

        reason = _stable_fail_reason(result.fail_reason)
        result.fail_reason = reason
        last_reason = reason
        if reason not in RETRYABLE_REASONS or index >= retry:
            result.attempts = index + 1
            result.retried = int(index > 0)
            result.last_reason = reason
            return result

        delay = retry_delay
        if delay > 0:
            delay = max(0.0, delay + random.uniform(-5.0, 5.0))
            time.sleep(delay)

    # The loop always returns, but keep a stable soft-failure fallback for
    # defensive callers or future changes.
    return JdFetchResult(
        ok=False,
        url=raw,
        portal=portal,
        fail_reason="error",
        attempts=total,
        last_reason="error",
        retried=int(total > 1),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fetch job JD body via Playwright")
    ap.add_argument("--url", required=True, help="Job detail URL")
    ap.add_argument("--out", type=Path, default=None, help="Write markdown")
    ap.add_argument("--headed", action="store_true", help="Show browser window")
    ap.add_argument("--channel", default=None, help="Playwright channel e.g. chrome")
    ap.add_argument(
        "--storage-state",
        type=Path,
        default=None,
        help="Path to storage_state.json (cookies)",
    )
    ap.add_argument(
        "--save-storage-state",
        type=Path,
        default=None,
        help="Save cookies/localStorage after success or WAF (must be under home)",
    )
    ap.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Per-attempt timeout in ms (capped at 60000)",
    )
    ap.add_argument(
        "--retry",
        type=int,
        default=2,
        help="Retry waf/timeout/empty failures (default 2; 0 disables retries)",
    )
    ap.add_argument(
        "--retry-delay",
        type=float,
        default=30.0,
        help="Seconds between retries; ±5s jitter when greater than zero",
    )
    ap.add_argument("--json", action="store_true", help="Print full JSON result")
    args = ap.parse_args(argv)

    res = fetch_jd_body(
        args.url,
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
        storage_state=args.storage_state,
        channel=args.channel,
        retry=args.retry,
        retry_delay=args.retry_delay,
        save_storage_state=args.save_storage_state,
        cache_root=_default_cache_root(),
    )
    if args.json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        status = "OK" if res.ok else f"FAIL ({res.fail_reason})"
        print(f"{status} portal={res.portal} chars={res.chars} sel={res.selector}")
        print(f"url={res.url}")
        if res.ok:
            print("---")
            print(res.text[:2000])
            if len(res.text) > 2000:
                print(f"… ({res.chars} chars total)")
        else:
            print(res.text[:400] if res.text else "")
            if res.fail_reason == "waf":
                print(
                    "提示：如持续被拦截，请使用 --headed --save-storage-state "
                    "<path> 完成一次人工验证后重试。"
                )

    if args.out and res.ok:
        args.out = args.out.expanduser().resolve()
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            f"# JD — {res.title or res.url}\n\n"
            f"- url: {res.url}\n"
            f"- portal: {res.portal}\n"
            f"- selector: {res.selector}\n\n"
            f"{res.text}\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out}")

    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
