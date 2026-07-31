#!/usr/bin/env python3
"""Fetch full job-description body via Playwright (JobsDB / CTgoodjobs / LinkedIn).

Solves the "no reliable JD body from portal APIs" gap for two-pass scoring.

Design:
  - Headless Chromium by default; optional channel=chrome / storage_state
  - Only used after pass-1 gate (callers decide)
  - Fail soft: return ok=False + fail_reason (waf|empty|timeout|error)
  - Does NOT auto-apply or auto-tailor

Usage:
  python3 tools/fresh_24h/portal_jd_browser.py --url 'https://hk.jobsdb.com/job/93633598'
  python3 tools/fresh_24h/portal_jd_browser.py --url '…' --out /tmp/jd.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
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


def fetch_jd_body(
    url: str,
    *,
    headless: bool = True,
    timeout_ms: int = 45000,
    storage_state: str | Path | None = None,
    channel: str | None = None,
    max_chars: int = MAX_CHARS,
) -> JdFetchResult:
    """Open job URL in Playwright and extract description text."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return JdFetchResult(
            ok=False,
            url=url,
            portal=detect_portal(url),
            fail_reason=f"playwright_import: {e}",
        )

    raw = (url or "").strip()
    portal = detect_portal(raw)
    canon = normalize_job_url(raw, source=portal if portal != "generic" else "")
    if not canon:
        return JdFetchResult(ok=False, url=raw, portal=portal, fail_reason="empty_url")

    state = storage_state or os.environ.get("PORTAL_JD_STORAGE_STATE")
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
                    fail_reason=f"launch: {e}",
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
            if state and Path(state).expanduser().exists():
                ctx_kwargs["storage_state"] = str(Path(state).expanduser())

            context = browser.new_context(**ctx_kwargs)
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
                waf_wait_seconds = min(
                    15,
                    max(0, int(os.environ.get("PORTAL_JD_WAF_WAIT_SECONDS", "10"))),
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
                reason = "timeout" if "timeout" in msg else f"error: {e}"
                return JdFetchResult(
                    ok=False, url=canon, portal=portal, fail_reason=reason
                )
    except Exception as e:
        return JdFetchResult(
            ok=False, url=canon, portal=portal, fail_reason=f"playwright: {e}"
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
    ap.add_argument("--timeout-ms", type=int, default=45000)
    ap.add_argument("--json", action="store_true", help="Print full JSON result")
    args = ap.parse_args(argv)

    res = fetch_jd_body(
        args.url,
        headless=not args.headed,
        timeout_ms=args.timeout_ms,
        storage_state=args.storage_state,
        channel=args.channel,
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
