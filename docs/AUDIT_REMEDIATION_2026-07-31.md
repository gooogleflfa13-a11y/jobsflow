# JobsFlow audit remediation

Date: 2026-07-31

Baseline: `docs/AUDIT_REPORT_2026-07-31.md`

## Outcome

All identified high-, medium- and low-risk source issues were fixed or reduced to
an explicit fail-closed boundary. The current product source passes its release
guards and regression suite. The existing Git repository must still not be made
public because its old history contains private workspace paths and oversized
browser binaries; publication must use a new clean-history snapshot.

## Closed high-risk issues

- Sheet/CSV formula injection is neutralized; Sheets writes external data as
  `RAW`.
- JD, company pages and model inputs are treated as untrusted data.
- Python and four Bun dependency sets are locked; install lifecycle scripts are
  guarded.
- Scan failures no longer advance the refresh cursor.
- Pass-2 rows below the configured gate are dropped by default.
- Sheet updates write new data before clearing stale tail rows.
- Setup writes identity, intent, queries, model proposals and tracker schema only
  to the Git-ignored personal workspace.
- `/setup`, `/scan`, `/materials` and `/apply` now share one contract.
- Personal filled templates, frozen candidate manifests, legal-only scraper
  defaults and candidate-specific PDF exporters were removed from product source.

## Cross-industry and low-model quality

- The tracked query file is an empty, setup-required product template.
- Explicit job-search intent takes priority over résumé history when selecting a
  deterministic profession preset.
- A-F directions, material folders, scoring evidence and tracker fields load from
  private setup rather than a built-in legal taxonomy.
- Setup emits `setup_design_request.json`. A model may propose role directions,
  industry-aware columns, keywords and weights only through
  `tools/setup_contract.py`.
- A valid proposal must include sourced industry context. Invalid, malformed or
  unsupported output keeps a deterministic fallback.
- Existing tracker rows are never migrated implicitly.
- Materials emit deterministic application preflight, company-research request,
  JD capability map, candidate evidence map, four-slot cover-letter blueprint,
  quality gate and low-model execution order.
- Capability mapping covers process/governance, stakeholder work, technology,
  analysis, delivery, customer/commercial work, ownership and
  quality/reliability across professions.
- Unrelated candidate evidence cannot satisfy a JD theme.

## Efficiency

- PDF conversion reuses content/engine/policy hashes and supports explicit
  invalidation.
- LibreOffice headless is the single documented PDF path.
- Bundled third-party font binaries and the candidate-specific exporter were
  removed; the optional LaTeX example uses a TeX Live system font.
- JD cache and structured APIs precede Playwright.
- Browser use occurs only after pass 1, has a per-run budget and blocks
  images/fonts/media.
- Portal retry, timeout and `Retry-After` behavior is shared and bounded.
- Same-company verified research is cached privately.

## Verification

- Python 3.12 temporary environment installed from `requirements-dev.lock`.
- `setup.py --doctor-json`: ready, no failed checks.
- Python: 126 tests passed.
- Four portal CLIs: typecheck passed; LinkedIn 20 tests, FreeHire 29, JobsDB 6
  plus 2 opt-in live skips, CTgoodjobs 6 plus 2 opt-in live skips.
- Skill/command lint, compileall, security guard, tracked/private query
  validation and `git diff --check`: passed.
- `public_release_check.py --source`: passed.
- `public_release_check.py --history`: intentionally fails on old private paths,
  oversized historical blobs and the uncommitted working tree.

## Remaining release conditions

1. Review and commit the repaired source as a clean snapshot.
2. Create a new public repository/history from that snapshot; do not push the
   current historical objects.
3. Run CI from the new repository and complete one clean-clone setup/scan/material
   smoke run with synthetic data.
4. Configure branch protection and private security reporting on the public
   host.

See `PUBLIC_RELEASE.md` and `docs/PUBLIC_READINESS_2026-07-31.md`.
