# Fresh job scan

This directory implements cross-industry, local-first job discovery and two-pass
scoring for LinkedIn, JobsDB, CTgoodjobs and FreeHire.

## Configuration boundary

Run `/setup` before scanning. Runtime search intent lives at:

```text
JobSearch_2026/00_Profile/queries.json
```

It contains three candidate-specific buckets—core, adjacent and exploration—
plus configurable relevance, exclusions, A-F mappings and scoring evidence. The
tracked `queries.json` intentionally contains no usable candidate search and
raises a clear setup-required error.

```bash
python3 tools/fresh_24h/validate_queries.py \
  JobSearch_2026/00_Profile/queries.json
```

## Recommended workflow

```bash
./tools/fresh_24h/temp_two_pass.sh temp
python3 tools/fresh_24h/push_to_gsheet.py \
  --also-local --min-score 3.3 --mode temp
```

Local-only tracking (no Google credentials):

```bash
python3 tools/fresh_24h/push_to_gsheet.py \
  --local-only --min-score 3.3 --mode temp
```

This merges scored rows into the main local
`JobSearch_2026/02_Tracker/hk_apply_list_YYYY-MM-DD.csv`, including batch and
status fields. Google Sheets remains an optional sync destination.

Deep rows expose `语义匹配来源`, `语义待处理数` and pending task keys. A scan
preview may show a conservatively capped `pending_fallback`, but formal push
blocks until those tasks are completed and the score is rerun. Use
`--allow-pending-semantic` only for an explicitly marked diagnostic push.

`temp` scans only since the last successful refresh; `daily` scans about 24
hours. Add `--no-record` to preview without changing state.

The pipeline scores title/teaser first, retrieves deeper text only for rows that
meet the gate, then scores again. Cache and structured retrieval precede a
time-budgeted browser fallback. Each row records pass-1, pass-2 and actual JD
depth; shallow text is never labeled as a full JD.

## Rules

- Search filters and hard rejects must come from the private configuration.
- A-F meanings are personalized during setup and apply across IDs, base résumés
  and tracker rows.
- Failed portals remain visible in run metadata and do not silently count as
  successful empty results.
- Scanning never creates CVs or cover letters.
- Materials require a selected job and full JD; unresolved portals become an
  explicit paste request.
- Browser calls are bounded. CAPTCHA and WAF are reported, not fought
  indefinitely.

See `AGENT_REFRESH.md`, `docs/system_rules.md` and
`docs/tracker_defaults.md`.
