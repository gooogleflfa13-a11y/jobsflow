# CTgoodjobs (Hong Kong) API reference

The endpoints, parameters, and response shapes this skill depends on. This is the
file to update if CTgoodjobs changes its API. Base path: `https://api01.ctgoodjobs.hk`
(confirmed live on 2026-07-17; the search endpoint returns real HK job data).

## Authentication

The search API requires **three HTTP headers** that a real browser session
normally receives as cookies from `www.ctgoodjobs.hk`:

| Header | Source | Example |
|--------|--------|---------|
| `sid` | `sid` cookie | `<your-sid>` |
| `channel-id` | fixed (web channel) | `1` |
| `visitor-id` | `visitor_id` cookie | `v20260717143801<your-sid>` |

> **Important:** these are **request headers**, NOT body fields. Sending them in
> the JSON body yields `400 The sid field is required.` (the validator reports the
> *expected* header name). They must be sent as HTTP headers on every request.

The CLI resolves them in this order:
1. Environment variables `CTGOOD_SID` and `CTGOOD_VISITOR_ID` (and optional
   `CTGOOD_CHANNEL_ID`, default `"1"`).
2. Otherwise it loads `https://www.ctgoodjobs.hk/` once and reads `sid` /
   `visitor_id` from the `set-cookie` response header, then reuses them.

For stable automation, set the env vars from a real browser session (DevTools →
Network → any request → copy the `sid` and `visitor_id` request headers). The
homepage bootstrap works but cookies rotate.

## Search endpoint

`POST https://api01.ctgoodjobs.hk/job/api/jobs/search`

Content-Type `application/json`, with the three auth headers above. Body:

```jsonc
{
  "PagingInputs": { "page": 1, "pageSize": 10 },
  "keyword": "paralegal",          // free-text; omit for all jobs
  "jobIds": ["10189838"]           // optional: filter to one job (detail command)
}
```

Response (flattened):

```jsonc
{
  "statusCode": 1,
  "serverTime": "2026-07-17T…",
  "data": {
    "meta": { "jobsTotal": 33, "title": "…", "desc": "…" },
    "total": 9,                    // jobs on this page
    "jobs": [ /* job objects */ ]
  }
}
```

`data.meta.jobsTotal` is the true match count (used for `meta.total`); `data.total`
is the page slice size.

### Job object (fields the skill reads)

```jsonc
{
  "jobId": "10189838",             // -> result.id
  "jobTitle": "<strong>Paralegal</strong> - Commercial Litigation", // HTML-wrapped; stripped
  "url": "https://jobs.ctgoodjobs.hk/job/10189838-/a",              // -> result.url
  "companyId": "00013807",
  "companyName": "Michael Page",   // -> result.company
  "publishTime": {                 // -> result.date (ISO timestamp)
    "display": "5h ago",
    "date": "2026-07-17",
    "timestamp": "2026-07-17T09:30:00"
  },
  "validThrough": { "display": "1m ago", "date": "2026-08-16" },
  "salary": {                      // -> result.salary (case 1 = N/A)
    "case": 1, "salaryValue": "N/A",
    "salaryFrom": null, "salaryTo": null,
    "salaryMonthHour": "MON", "isNegotiable": false
  },
  "locations": ["Central and Western District"],   // -> result.location
  "jobareas": ["Professional Services - Legal & Compliance"], // -> result.areas
  "benefits": [],
  "empTypes": [ { "id": "001", "name": "Full-time" } ],        // -> result.employmentTypes
  "careerLevels": [ { "id": "004", "name": "Non-management level" } ], // -> result.careerLevels
  "highlights": null               // -> result.teaser
}
```

`jobId` is numeric. The **openable** public job URL is `https://jobs.ctgoodjobs.hk/job/<id>/` (API sometimes returns `/job/<id>-/slug` or `/job/<id>-/a` which does not open cleanly — normalize to `/job/<id>/`).

## Detail endpoint

There is **no documented single-job REST endpoint**, and the job detail *page*
(`jobs.ctgoodjobs.hk/job/<id>`) is behind an **AWS WAF challenge** / client-rendered
SPA — a plain GET returns the captcha/WAF shell, not the job description.

To keep this skill zero-dependency, `detail` re-queries the search API with a
`jobIds` filter:

`POST https://api01.ctgoodjobs.hk/job/api/jobs/search`
body: `{ "PagingInputs": { "page": 1, "pageSize": 5 }, "jobIds": ["<id>"] }`

This returns exactly the matching job (`data.total: 1`), giving the rich card
fields (title, company, location, salary, areas, employment type, career level,
date, URL). It does **not** include the full description body — that requires the
gated page or a headless browser. Note this in SKILL.md's Notes.

## Parsing notes

- Responses are JSON. `jobTitle` and `highlights` may contain `<strong>` HTML
  highlighting — stripped via a regex before display.
- `salary.case === 1` means undisclosed (`salaryValue: "N/A"`) → surface as `null`.
- `--jobage` is not a first-class server param here; the skill narrows by
  `publishTime.timestamp` on the client (based on `--jobage` days).
- Fetch uses a browser User-Agent, exponential backoff with jitter on 429/5xx
  (max 6 retries). Connection failure fails fast (graceful degradation).
- Keep request volume low (personal use). CTgoodjobs may rate-limit bulk access.

## Quirks / open items

- **AWS WAF on detail pages.** The job description requires either the gated page
  (browser) or a future documented detail API. Current `detail` returns the card.
- **Cookie rotation.** `sid` / `visitor_id` may expire; re-bootstrap from the
  homepage or refresh env vars if you see 400s.
- **`channel-id` value.** `1` works for the web channel; other values (2, 3) also
  return 200 but were not compared for result differences.
