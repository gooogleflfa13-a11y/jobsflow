# System Rules: Documents, Search and Personal Boundaries

**Effective date:** 2026-07-31

**Authority:** Cross-platform forced procedure for every agent and script.
**Architecture:** `docs/adr/001-workflow-boundaries.md`

## 1. Product and private workspace are separate

- Tracked source is a cross-industry product. It must not contain a real
  candidate's identity, employment history, target companies or personal search
  defaults.
- `JobSearch_2026/` and `.env` are private, Git-ignored runtime state.
- First-time setup writes personal search configuration to
  `JobSearch_2026/00_Profile/queries.json` and profile facts to
  `JobSearch_2026/00_Profile/config.personal.json`.
- `tools/fresh_24h/queries.json` is an industry-neutral, setup-required template.
  It is not a usable candidate preset.
- Legal, engineering, healthcare, finance, operations and other professions use
  the same pipeline. Profession presets may help setup, but none is the global
  default.

## 2. PDF production

- Outbound CV and cover-letter PDFs are one-page A4 unless the user explicitly
  requests another format.
- Use LibreOffice headless first. A supported fallback is allowed only when
  LibreOffice is unavailable and its output passes the same checks.
- Never automate WPS menus or accessibility clicks.
- Preserve normal glyph proportions. Adjust paragraph spacing and content
  density; do not stretch text.
- Use clean filenames without dates or internal version tokens.
- Verify: one page, expected contact details from the private profile, no
  watermark, no missing glyphs, and no stale conversion cache.

```bash
python3 tools/fresh_24h/docx_to_pdf.py path/to/file.docx --engine libreoffice
```

## 3. Setup and personalized schema

`/setup` must always produce a valid deterministic configuration first. A capable
model may then propose a more useful A-F role mapping, scoring profile and tracker
columns based on:

- the user's stated roles and material constraints;
- evidence actually present in the résumé;
- relevant industry conventions, treated as fields to inspect rather than facts
  about the candidate.

The model proposal must pass `tools/setup_contract.py`. It may not overwrite base
columns, exceed limits, invent candidate facts or write into tracked product
configuration. Invalid output keeps the deterministic fallback. An existing
tracker with data rows is never migrated implicitly.

## 4. Search and two-pass scoring

The private setup configuration must contain at least three intent buckets:

1. core target roles;
2. adjacent target roles;
3. exploration roles.

Their actual queries and relevance rules are candidate- and profession-specific.

| Step | Rule |
|------|------|
| Scan | Collect title, URL and teaser with bounded portal budgets |
| Pass 1 | Score using the private profile |
| Gate | Default threshold is 3.3 |
| JD | Prefer cache/structured retrieval; use browser only as a bounded fallback |
| Pass 2 | Rescore with the best available JD depth |
| Track | Record pass-1, pass-2 and actual JD depth |
| Materials | Never auto-generate during scan |

- Preview means no sheet push and `--no-record`.
- Do not claim full-JD analysis when only a teaser is available.
- Follow the machine-readable run contract; do not ask a lower-capability model to
  reinterpret portal success, counters or next actions.
- Hard rejection and keyword relevance must come from the private configuration,
  not a built-in profession.

## 5. Materials

Generate materials only after the user selects a job.

```bash
python3 -m tools.job_materials pipeline --package "..." --lane A
```

- Require a full JD for high-quality tailoring. If it cannot be retrieved, ask the
  user to paste it.
- Research the company's nature, main business and role context. Store claims with
  source URLs and distinguish sourced facts from inference.
- Build a JD requirement map and connect every customized claim to verified résumé
  evidence. Unrelated evidence does not count.
- Tailoring may reorder, select and conservatively rephrase evidence; it may not
  invent duties, outcomes, tools, qualifications or motivation.
- The cover letter should express specific, evidence-based interest in the company
  or industry rather than generic praise.
- Deterministic preflight, evidence-map and quality-gate outputs are mandatory so
  lower-capability models cannot silently skip requirements such as salary,
  authorization, language, location or schedule.

## 6. Final checks

Before ending a relevant task, confirm:

- product/private boundary remains intact;
- configured search buckets are present and the tracked template remains neutral;
- scan and material generation stayed decoupled;
- company/JD claims have evidence or are explicitly unresolved;
- PDFs meet the one-page and rendering checks;
- public release checks and tests pass.

Changes to these system rules require matching code, tests and user-facing
documentation.
