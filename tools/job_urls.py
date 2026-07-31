"""Shared canonical job URL normalization across scan and materials domains."""

from __future__ import annotations

import re
from urllib.parse import urlparse


def normalize_job_url(url: str, *, source: str = "") -> str:
    u = (url or "").strip()
    if not u:
        return u
    src = (source or "").lower()
    if "ctgoodjobs.hk" in u or src in {"ctgoodjobs", "ctjobs"}:
        match = re.search(r"ctgoodjobs\.hk/job/(\d+)", u, re.I)
        if match:
            return f"https://jobs.ctgoodjobs.hk/job/{match.group(1)}/"
        if re.fullmatch(r"\d+", u):
            return f"https://jobs.ctgoodjobs.hk/job/{u}/"
    if "jobsdb.com" in u or src == "jobsdb":
        match = re.search(r"jobsdb\.com(?:/[^?\s]*)?/job/(\d+)", u, re.I)
        if match:
            host = urlparse(u).netloc or "hk.jobsdb.com"
            return f"https://{host}/job/{match.group(1)}"
    if "linkedin.com" in u or src == "linkedin":
        match = re.search(r"linkedin\.com/jobs/view/(?:[^/\s]*-)?(\d+)", u, re.I)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}/"
        match = re.search(r"[?&]currentJobId=(\d+)", u)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}/"
    match = re.search(r"^(https?://[^/]+/job/)(\d+)(?:-/[^?\s]*)?", u, re.I)
    return f"{match.group(1)}{match.group(2)}/" if match else u


def extract_job_id(url_or_id: str) -> str | None:
    value = (url_or_id or "").strip()
    if re.fullmatch(r"\d+", value):
        return value
    for pattern in (
        r"/job/(\d+)",
        r"linkedin\.com/jobs/view/(?:[^/\s]*-)?(\d+)",
        r"[?&]currentJobId=(\d+)",
    ):
        match = re.search(pattern, value, re.I)
        if match:
            return match.group(1)
    return None
