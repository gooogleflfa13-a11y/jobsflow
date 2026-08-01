# Agent contract: daily and temporary scans

Read `docs/system_rules.md` first. Search relevance, exclusions, A-F directions
and scoring evidence come from the user's private setup configuration:

```text
JobSearch_2026/00_Profile/queries.json
```

The tracked `queries.json` is an industry-neutral setup-required template.

## Modes

| User request | Mode | Window |
|--------------|------|--------|
| default, temp, 临时 | `--mode temp` | since the last successful refresh, with bounded padding |
| daily, 日更, 24 hours | `--mode daily` | about 24 hours |
| explicit N hours | `--mode temp --hours N` | N hours |

If no refresh state exists, temp establishes a 24-hour baseline. Failed portal
runs must not advance the cursor. Use `--no-record` for previews and debugging.

```bash
./tools/fresh_24h/fresh_24h_scan.sh --show-state
./tools/fresh_24h/temp_two_pass.sh temp
./tools/fresh_24h/temp_two_pass.sh daily
```

## Two-pass contract

1. Scan titles and teasers using configured queries.
2. Score pass 1 with the private scoring profile.
3. Only rows meeting the default 3.3 gate continue.
4. Retrieve the JD cache/structured detail; use Playwright only as a bounded
   fallback.
5. Score pass 2 and record the actual JD depth.
6. For deep rows, process pending semantic resume-match tasks with
   `semantic_match_agent.py`; label each verdict as direct, transferable,
   upper_only or none. The profile calibration caps transferable/upper-only
   scores deterministically.
7. Write local/Google tracker rows only when requested.
8. Never create application materials during scan.

Use a full JD for materials. If a portal remains shallow, mark `paste_needed` and
ask for pasted text instead of fabricating requirements.

## Batch and identifiers

`JobSearch_2026/02_Tracker/fresh_refresh_state.json` stores the last successful
refresh and recent history. New rows use `本轮新增=是`, a batch ID and timestamp;
older rows are demoted and lose new-batch styling.

IDs use `{A-F direction}{0-3 tier}-{sequence}`. A-F meanings come from private
setup, never from a built-in profession. Continue the maximum existing prefix;
do not invent placeholder ranges.

## Required agent behavior

- Respect preview/no-record and never push implicitly.
- Follow the run JSON `model_contract` for counters, failures and next actions.
- Do not reinterpret an unconfigured template as search intent.
- Do not spend unbounded time on WAF, CAPTCHA or browser recovery.
- A single-job “deep analysis” request uses `deep_analyze_job.py`, not a teaser.
- A pending semantic task is an enhancement, not a failure; if it is not
  completed, keep the keyword score and report the pending count.
- Keep search, tracking, materials and submission as separate user-authorized
  stages.
