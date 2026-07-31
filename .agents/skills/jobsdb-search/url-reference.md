# JobsDB (Hong Kong) API reference

The endpoints, parameters, and response shapes this skill depends on. This is the
file to update if JobsDB changes its API. Base path: `https://hk.jobsdb.com`
(Seek group "HK-Main" market).

## Authentication

**None for reads.** The search endpoint returns HTTP 200 with no API key, no
session cookie, and no token. Verified live on 2026-07-17: a plain `fetch` with a
browser User-Agent and `Accept: application/json` returns the full JSON payload.

> Note: an older community scraper (`okdarnoc/Jobsdb-All-Jobs-Scrapper`) targeted
> `xapi.supercharge-srp.co/job-search/graphql`. That host is **dead** (resolves to
> a black-hole IP, TLS fails). This skill uses the current REST endpoint instead.

## Search endpoint

`GET https://hk.jobsdb.com/api/jobsearch/v5/search`

Returns a JSON envelope (not wrapped in `data`/`meta` — flat top level):

```jsonc
{
  "data": [ /* job objects */ ],
  "totalCount": 377,
  "info": { "serverTimeMs": 28 },
  "userQueryId": "API3617637584885724781",
  "sortModes": [ { "isActive": true, "name": "Relevance", "value": "KeywordRelevance" },
                 { "isActive": false, "name": "Date", "value": "ListedDate" } ],
  "solMetadata": { "searchRequestToken": "…" },
  "facets": { … },
  "searchParams": { "sitekey": "HK-Main", "keywords": "paralegal", "page": "1", "pagesize": "3" }
}
```

### Query parameters used by the skill

| Param | Maps to CLI flag | Notes |
|-------|------------------|-------|
| `siteKey` | (fixed `HK-Main`) | Hong Kong market. |
| `keywords` | `--query` / `-q` | Free-text keyword (title/skill/role/company). |
| `page` | `--page` | 1-indexed. Default 1. |
| `pageSize` | (derived from `--limit`) | Page size; `--limit` caps client-side too. |
| `daterange` | `--jobage` | `7`, `14`, `30` (days). Omit for all postings. |
| `sortmode` | (fixed `ListedDate` when `--jobage` set) | Newest first for recency queries. |
| `location` | (reserved) | District/city label; not yet wired (see Quirks). |

`totalCount` drives pagination: `totalPages ≈ ceil(totalCount / pageSize)`.

### Job object (fields the skill reads)

```jsonc
{
  "id": "93369834",                         // -> result.id; detail URL is /job/<id>
  "title": "Paralegal / Paralegal Trainee",// -> result.title
  "companyName": "Kao, Lee & Yip Solicitors", // -> result.company
  "teaser": "FIRST HAND SALE PARALEGAL/TRAINEE PROGRAMME", // short summary
  "bulletPoints": ["5 days work", "…"],    // highlights
  "listingDate": "2026-07-16T08:31:56Z",   // -> result.date (ISO 8601)
  "listingDateDisplay": "21h ago",         // human relative date
  "salaryLabel": "$20k - $30k / month",    // may be "" when undisclosed
  "locations": [ { "label": "Central and Western District",
                   "countryCode": "HK",
                   "seoHierarchy": [ { "contextualName": "…" } ] } ], // -> result.location
  "classifications": [ { "classification": { "id": "1216", "description": "Legal" },
                         "subclassification": { "id": "1429",
                                                "description": "Law Clerks & Paralegals" } } ],
  "workTypes": [ "Full time" ],            // employment type
  "workArrangements": [ { "id": "1", "label": { "text": "On-site" } } ],
  "advertiser": { "id": "…", "description": "…" },
  "employer": { "id": "…", "name": "…", "companyUrl": "https://hk.jobsdb.com/companies/…" },
  "roleId": "paralegal",
  "displayType": "standard",
  "branding": { "serpLogoUrl": "https://…" }
}
```

`id` is numeric (e.g. `93369834`). The public job URL is
`https://hk.jobsdb.com/job/<id>`.

## Detail endpoint

The job detail page `https://hk.jobsdb.com/job/<id>` is a **client-rendered SPA**
(React). A plain `fetch` of that URL returns the app shell, not the job description,
so the full description is **not** available via a simple GET.

To keep this skill zero-dependency and avoid a headless browser, `detail` returns
the rich fields already present in the **search** response (teaser, bullet points,
salary, classification, work types, work arrangement, location, date) by fetching
the search API filtered to that single job id, rather than scraping the SPA. This
gives a readable, structured detail without the description body. If the description
body is required later, it needs either a documented detail API or a browser; note
that in SKILL.md's Notes.

### How `detail` resolves a single job

The v5 search API supports a `jobid` filter that returns exactly the one matching
job (`totalCount: 1`). The skill calls:

`GET https://hk.jobsdb.com/api/jobsearch/v5/search?siteKey=HK-Main&jobid=<id>&page=1&pageSize=5`

and picks the entry whose `id` matches. The plain `/job/<id>` page is a
client-rendered SPA (plain GET returns the app shell), so we use the `jobid`
filter instead of scraping. If no match, it reports `NOT_FOUND`. Verified live:
`jobid=93392037` returns `totalCount: 1` with the full job object.

## Parsing notes

- The response is JSON (flat envelope, not `{data,meta}`). No HTML card parsing —
  unlike the scraping portals. Only `teaser`/`bulletPoints` are short text; no HTML
  stripping needed.
- Fetch uses a browser User-Agent, `Accept: application/json`, and exponential
  backoff with jitter on 429/5xx (max 6 retries). A connection error fails fast with
  a clear message (graceful-degradation contract: an outage degrades this source
  quickly rather than hanging the caller).
- `salaryLabel` is often empty (`""`) for HK legal/paralegal postings — surface it
  as `null`, never a fake value.

## Quirks / open items

- **Location filter is not wired.** The search API accepts `location` as a district
  label, but the exact param shape for arbitrary districts wasn't confirmed; the
  skill scopes by keyword + daterange only. Add `--location` once the param is
  verified against a live district query.
- **Date is ISO (`listingDate`)**, already machine-friendly; `result.date` passes it
  through as-is.
- **Anti-bot potential.** The endpoint is currently open, but Seek/Cloudflare may
  rate-limit bulk use. Keep volume low (personal use). See the personal-use warning
  in SKILL.md.
