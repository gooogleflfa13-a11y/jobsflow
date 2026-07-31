# Tracker Defaults

**Edit the CSV tracker in your personal workspace (or use the optional Google
Sheets sync):**

```text
JobSearch_2026/02_Tracker/hk_apply_list_YYYY-MM-DD.csv
```

| File | Description |
|------|-------------|
| `hk_apply_list_YYYY-MM-DD.csv` | **Main local management table** (tier, résumé version, materials status, customized requirement fields) |
| Google Sheets | Optional synced management view; scripts read/write CSV locally first |
| `fresh_24h_YYYY-MM-DD.csv` | Daily/temp scan raw candidates (title + teaser) |
| `fresh_24h_YYYY-MM-DD_*_twopass_scored.csv` | **Two-pass scored** results (with pass-1/pass-2 columns) |
| `fresh_24h_YYYY-MM-DD_run.json` | Scan run log |
| `jds/` | Full-text JDs (pasted/enriched after user selects a job) |
| `deep_analysis/` | Single-job deep analysis reports |

---

## Product Rule: Search != Materials

| Phase | Does | Does NOT |
|-------|------|----------|
| **Search + two-pass** | Scan -> pass-1 -> gate -> deep -> pass-2 -> sheet | Auto-tailor CV / auto-generate packages |
| **Materials** | Only after user picks a package -> `job_materials` | Decoupled from scan |

Implementation: `tools/fresh_24h/two_pass_score.py`, `temp_two_pass.sh`, `push_to_gsheet.py`; materials: `tools/job_materials/`.

The base columns are industry-neutral. `/setup` may add up to eight validated
fields that matter for the user's target profession or constraints. Model
proposals only update an empty tracker automatically; populated trackers require
an explicit migration.

---

## Two-Pass Scoring (temp / daily - default)

```text
1 Scan temp/daily -> title + teaser candidate CSV
2 Pass-1          -> CareerOps score on teaser
3 Gate            -> Only score >= 3.3 passes (below dropped, no full JD)
4 Deep JD         -> LinkedIn-primary full; CT URL normalize; JobsDB often teaser
5 Pass-2          -> Rescore on pass-2 text (may still be teaser)
6 Sheet           -> Main CareerOps* = pass-2; also pass-1* / pass-2* / JD depth
7 Materials       -> Only when user picks a job - never auto
```

**Gate default 3.3**. Legacy single-pass: `--legacy-single-pass` (shallow enrich + custom min, old default 3.0).

> **Honesty:** JobsDB/CT pass-2 is often **teaser + URL fix**, not full JD. Use `job_materials jd set` to paste full text for materials.

---

## Daily / Temp Scan

| Mode | Command | Window |
|------|---------|--------|
| Daily | `./tools/fresh_24h/fresh_24h_scan.sh daily` | Last ~24h |
| **Temp** | `./tools/fresh_24h/fresh_24h_scan.sh temp` | **Since last refresh** |
| **Recommended** (scan + two-pass) | `./tools/fresh_24h/temp_two_pass.sh temp` | Same + gate 3.3 |

State file: `fresh_refresh_state.json`

```bash
./tools/fresh_24h/fresh_24h_scan.sh --show-state
./tools/fresh_24h/temp_two_pass.sh temp          # temp + two-pass (default)

# Push to Google Sheet (default two-pass, gate 3.3)
python3 tools/fresh_24h/push_to_gsheet.py --also-local --min-score 3.3 --mode temp
```

See `tools/fresh_24h/README.md` and `tools/fresh_24h/AGENT_REFRESH.md`.

---

## Materials (on request - decoupled from search)

```bash
# Only when you select a specific package (never triggered by scan/push)
python3 -m tools.job_materials pipeline \
  --package 'JobSearch_2026/01_Masters/.../C0-xxx_...' \
  --lane C
```

- A-F **base versions** need fact-check; single-job tailor **only reorders emphasis**.
- Deep full text: **LinkedIn primary**; CT/JobsDB use `jd set` paste.
- PDF: `docx_to_pdf.py` with LibreOffice headless (see `docs/system_rules.md`)

---

**Materials status flow:**  
`未做` -> `master可用` -> `已定制` -> `已投` -> `面试中` -> `关闭`
