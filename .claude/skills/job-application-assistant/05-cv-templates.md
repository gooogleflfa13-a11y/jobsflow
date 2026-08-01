# CV Template and Tailoring Guide

The public repository contains only placeholders. Filled DOCX masters and
generated PDFs belong in `JobSearch_2026/`.

## Source and output

- Source of truth: the latest fact-checked A–F DOCX master.
- Output: one-page A4 DOCX and PDF.
- PDF engine: LibreOffice headless through
  `tools/fresh_24h/docx_to_pdf.py`.
- Never generate a candidate-specific file under tracked `cv/`.

## Required placeholders

- [YOUR_NAME]
- [YOUR_EXPERIENCE]
- [YOUR_PRIMARY_SKILLS]
- [YOUR_CONTACT_DETAILS]

## Tailoring rules

1. Run application preflight and resolve its blockers.
2. Require a full JD and sourced company context.
3. Use `evidence_map`; an empty capability mapping remains an explicit gap.
4. Reorder or lightly rephrase only fact-checked bullets.
5. Never invent an achievement, metric, tool, qualification, or industry
   interest.
6. Verify one page, readable text extraction, correct contact details, and the
   `tailor_plan.json.material_filenames` send name. Use only a verified hiring
   employer in that name; never expose a recruiter or staffing agency.

See `docs/system_rules.md` and `.claude/commands/materials.md`.
