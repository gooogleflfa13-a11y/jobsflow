---
name: ctgoodjobs-search
version: 1.1.0
description: >
  Search or inspect CTgoodjobs Hong Kong listings for any profession. Use for
  CTgoodjobs, HK job search, find jobs in Hong Kong, search a role or company,
  look up a job ID or URL, recent vacancies, salary/career-level checks, 搵工,
  求職, 香港招聘, or when another workflow needs structured CTgoodjobs results.
  Supports engineering, healthcare, finance, operations, marketing, legal and
  all other keyword queries.
context: fork
allowed-tools: Bash(bun run .agents/skills/ctgoodjobs-search/cli/src/cli.ts *)
---

# CTgoodjobs Hong Kong search

Use CTgoodjobs structured results for a user-supplied or private
setup-generated query. Never substitute a built-in profession.

## Step 1: Detect the available path

```bash
bun run .agents/skills/ctgoodjobs-search/cli/src/cli.ts --help
```

Decision tree:

1. If help succeeds and session bootstrap works, use the CLI.
2. If the CLI exists but session bootstrap fails, use configured
   `CTGOOD_SID`/`CTGOOD_VISITOR_ID` from the user's private environment.
3. If Bun or the CLI is unavailable, use JobsFlow `/scan` orchestration or give a
   direct CTgoodjobs search URL; do not fabricate results.

Gate: continue only after identifying one usable path.

## Defaults

| Parameter | Default | Reason |
|-----------|---------|--------|
| Query | private setup query; otherwise user's exact role text | no profession bias |
| Recency | 7 days | useful balance of freshness and coverage |
| Page | 1 | bounded request volume |
| Limit | 20 | avoids bulk collection |
| Format | JSON | deterministic downstream processing |
| Channel ID | `1` | CTgoodjobs default |

## Step 2: Resolve session

The CLI first tries the user's private environment:

- `CTGOOD_SID`
- `CTGOOD_VISITOR_ID`
- `CTGOOD_CHANNEL_ID` (optional; default `1`)

If unset, it makes one bounded homepage request to bootstrap cookies. Never
print cookie values or write them into product files.

Gate: if both configured credentials and bootstrap fail, report the portal as
failed and preserve results from other sources.

## Step 3: Search

```bash
bun run .agents/skills/ctgoodjobs-search/cli/src/cli.ts search \
  --query "<keywords>" --jobage 7 --limit 20 --format json
```

Use the user's query verbatim unless private setup supplies scoped terms. Treat
an empty result as valid only when the command succeeded and emitted the
contract envelope.

## Step 4: Inspect promising results

```bash
bun run .agents/skills/ctgoodjobs-search/cli/src/cli.ts detail <id-or-url> \
  --format json
```

Detail uses the search API's job-ID filter and returns structured fields. The
full page is often WAF/client-rendered and is not guaranteed. Mark actual JD
depth and request a paste before materials when full text is unavailable.

- Retries for 429/5xx are bounded.
- Keep use personal and low-volume.
- Never invent undisclosed salary or missing requirements.

## Step 5: Respond

Return:

1. **Run status** — method, query, recency and any auth/network failure.
2. **Results** — title, company, location, date, salary when disclosed and URL.
3. **Depth** — `search_teaser`, `structured_detail` or `full_jd`.
4. **Next action** — shortlist, inspect detail, paste full JD, or broaden one
   configured bucket.

Data source: `https://api01.ctgoodjobs.hk/job/api/jobs/search`. Use is
personal/low-volume and subject to the portal's current terms and rate limits.
