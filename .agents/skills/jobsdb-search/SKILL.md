---
name: jobsdb-search
version: 1.1.0
description: >
  Search or inspect JobsDB Hong Kong listings for any profession. Use for JobsDB,
  HK job search, find jobs in Hong Kong, search a role or company, look up a job
  ID or URL, recent vacancies, salary/work-type checks, 搵工, 求職, 香港招聘, or
  when another workflow needs structured JobsDB results. Supports engineering,
  healthcare, finance, operations, marketing, legal and all other keyword queries.
context: fork
allowed-tools: Bash(bun run .agents/skills/jobsdb-search/cli/src/cli.ts *)
---

# JobsDB Hong Kong search

Use JobsDB's structured search results for a user-supplied or private
setup-generated query. Never substitute a built-in profession.

## Step 1: Detect the available path

```bash
bun run .agents/skills/jobsdb-search/cli/src/cli.ts --help
```

Decision tree:

1. If help succeeds, use the CLI.
2. If Bun or the CLI is missing, use JobsFlow's normal `/scan` orchestration if
   available.
3. If neither path is available, give the user a direct JobsDB search URL and
   clear setup instructions; do not fabricate results.

Gate: continue only after identifying one usable path.

## Defaults

| Parameter | Default | Reason |
|-----------|---------|--------|
| Query | private setup query; otherwise user's exact role text | no profession bias |
| Recency | 7 days | useful balance of freshness and coverage |
| Page | 1 | bounded request volume |
| Limit | 20 | enough to compare without bulk collection |
| Format | JSON | deterministic downstream processing |
| Location | Hong Kong market | this integration targets hk.jobsdb.com |

## Step 2: Search

```bash
bun run .agents/skills/jobsdb-search/cli/src/cli.ts search \
  --query "<keywords>" --jobage 7 --limit 20 --format json
```

Use the user's query verbatim unless the private setup supplies scoped terms.
For broader discovery, issue separate core/adjacent/exploration queries rather
than joining unrelated professions.

Gate: JSON must contain the CLI contract envelope. A successful empty result is
different from a failed request.

## Step 3: Inspect promising results

```bash
bun run .agents/skills/jobsdb-search/cli/src/cli.ts detail <id-or-url> \
  --format json
```

`detail` returns structured fields such as teaser, salary, classification, work
type, arrangement, location and date. It does not guarantee the full
client-rendered description. Mark the actual JD depth; for materials, request a
full-JD paste if deeper retrieval fails.

Gate: never label structured fields or a teaser as a full JD.

## Step 4: Handle failures safely

- The CLI retries 429/5xx with bounded exponential backoff.
- On rate limit, network error or malformed output, report the portal failure and
  preserve other portal results.
- Keep volume low and do not use the endpoint for bulk/commercial collection.
- Never invent salary, employer, date or requirements when a field is absent.

## Step 5: Respond

Return:

1. **Run status** — method, query, recency and any failure.
2. **Results** — title, company, location, date, salary when disclosed and URL.
3. **Depth** — `search_teaser`, `structured_detail` or `full_jd`.
4. **Next action** — shortlist, inspect detail, paste full JD, or broaden one
   configured bucket.

Data source: `https://hk.jobsdb.com/api/jobsearch/v5/search`. Use is
personal/low-volume and subject to the portal's current terms and rate limits.
