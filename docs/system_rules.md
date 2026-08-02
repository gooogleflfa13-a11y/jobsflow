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

`/setup` also asks the user to calibrate semantic resume matching as low
(conservative), medium (balanced) or high (broader). This setting is private and
only changes how far `capability_upper` may support a JD comparison. It never
turns potential into completed experience and never relaxes fact, qualification
or forbidden-claim checks.

### Incremental intent changes

After setup, intent changes use the two-phase `tools/update_intent.py` contract:

1. `/intent add ...` or `/intent replace ...` creates a private preview only;
2. the assistant summarizes recognized role/industry terms and explicit
   constraints;
3. only `/intent confirm` writes `queries.json` and `intent_state.json`;
4. the next `/scan` consumes the confirmed configuration.

Casual conversation must not mutate search scope. A stale preview is rejected if
the private configuration changed in the meantime. Historical tracker rows and
existing application materials are not rewritten by an intent update.

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
- Deep-JD resume matching may create a pending agent task. A completed verdict
  must declare a direct, transferable, upper-only or none basis; missing verdicts
  fall back to the deterministic keyword score.
- The URL-keyed JD cache is checked before every portal branch. A valid entry
  (default: 60 days, at least 100 non-whitespace characters) is reused with no
  network request. A successful deep retrieval is written immediately to
  `02_Tracker/jds/cache/<sha256(url)[:16]>.json`.
- Deep position profiling creates a separate `position_profile` task containing
  the cached JD, company/role context and lane labels. Its completed verdict may
  set the lane and a sourced-or-explicitly-unverified `company_brief`; otherwise
  deterministic lane and company-brief fallbacks remain in force.
- Agent tasks are executable as `list -> show -> complete` and must not ask a
  lower-capability model to rediscover a portal, reinterpret fetch status, or
  invent missing evidence.

## 5. Materials

Generate materials only after the user selects a job.

```bash
python3 -m tools.job_materials pipeline --package "..." --lane A
```

- Require a full JD for high-quality tailoring. If it cannot be retrieved, ask the
  user to paste it.
- Prefer researching the company's nature, main business and role context. Store
  claims with source URLs and distinguish sourced facts from inference; if no
  reliable source is available, use JD-only/role context rather than guessing.
- Build a JD requirement map and connect every customized claim to verified résumé
  evidence. Unrelated evidence does not count.
- Emit stable evidence IDs, requirement coverage states (`covered`, `partial`,
  `uncovered`, `prohibited_to_claim`) and one cross-material contract for CV,
  cover letter and application email. The same evidence ID and numeric fact must
  retain the same meaning in every material view.
- Optimize evidence density and reading order (summary/role-leading evidence)
  without keyword stuffing. LLMO is parseability and evidence alignment, not
  model-memory writing or an ATS score guarantee.
- Tailoring may reorder, select and conservatively rephrase evidence; it may not
  invent duties, outcomes, tools, qualifications or motivation.
- The tailored cover letter should use the existing company-interest slot for one
  compact 1–2 sentence role/industry-match paragraph: role requirement or business
  context → fact-checked candidate evidence → value contribution. Use real JD
  anchors; do not repeat the full résumé or write generic praise.
- This paragraph replaces a generic slot and must stay within the generic Cover
  Letter's one-page/length budget. If reliable company facts are unavailable, use
  JD-only or role context; if evidence is insufficient, omit the optional paragraph
  and allow the generic letter to proceed. Its absence is not an `/apply` blocker.
- A–F should emphasize job function and business context. G may add a concrete,
  evidence-supported interest in AI, fintech, digital assets or another technology
  context when the JD supports it.
- Identify whether the listing is posted directly by the hiring company or via a
  recruiter / staffing agency / consultancy. If the poster is a recruiter or
  agency, do NOT use the recruiter's name in the output file name or in the
  cover letter; address the letter to the end employer (the actual company), not
  the recruiter.
- Persist this boundary as `publisher_type`, `publisher_name` and
  `employer_name`. A disclosed client may be used as the outbound target; an
  undisclosed client remains unnamed and must not be guessed. Use the generated
  `material_filenames` values for external CV/CL filenames while retaining the
  publisher only inside the private package for traceability.
- Deterministic preflight, evidence-map and quality-gate outputs are mandatory so
  lower-capability models cannot silently skip requirements such as salary,
  authorization, language, location or schedule.

## 6. Final checks

Before ending a relevant task, confirm:

- product/private boundary remains intact;
- configured search buckets are present and the tracked template remains neutral;
- scan and material generation stayed decoupled;
- company/JD claims have evidence or are explicitly unresolved;
- active material selectors exclude `_archive`/`archive`/`archives` versions;
- PDFs meet the one-page and rendering checks;
- public release checks and tests pass.

Changes to these system rules require matching code, tests and user-facing
documentation.
