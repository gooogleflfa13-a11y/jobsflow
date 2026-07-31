# job_materials — on-demand, company/JD-aware materials

This pipeline runs only after a user selects a job. Search and sheet updates
never create application materials.

## Quality boundary

- A–F base résumés represent the six role directions created during setup.
- Each base must pass fact-check before it can support tailoring.
- High-quality tailoring requires the full JD. If cache, structured retrieval and
  bounded browser fallback remain shallow, use `jd set` to paste the text.
- Tailoring may select, reorder and conservatively rephrase verified evidence. It
  may not invent responsibilities, metrics, qualifications, company facts or
  candidate motivation.
- Output is written into a job package; master DOCX files are never overwritten.

## Typical flow

```bash
python3 -m tools.job_materials base sync
python3 -m tools.job_materials base factcheck --lane A

PKG='JobSearch_2026/01_Masters/A_core/核心/A0-005_未投_Example'
python3 -m tools.job_materials pipeline --package "$PKG" --lane A
```

If the JD is missing:

```bash
python3 -m tools.job_materials jd set \
  --package "$PKG" --file ./jd.txt
```

If application preflight asks for salary, availability, authorization or another
explicit input:

```bash
python3 -m tools.job_materials preflight answer \
  --package "$PKG" --field expected_salary \
  --value 'currency and range'
```

## Company quick research

The pipeline first reuses a source-aware cache for the same company. If context
is incomplete it writes `company_research_request.json`, a constrained contract
for either a capable or lower-capability model. It requires:

- company nature and main business;
- JD-derived role priorities;
- a valid URL for every company fact;
- explicit uncertainties;
- potential interest angles for the user to confirm.

An interest angle is not a candidate fact. The model must not state admiration or
motivation until the user confirms it.

Save completed research:

```bash
python3 -m tools.job_materials company set \
  --package "$PKG" --file ./company_research.json
```

## Package outputs

| File | Purpose |
|------|---------|
| `application_preflight.json` | Deterministic questions and profile checks |
| `company_research_request.json` | Source-aware quick-research contract when needed |
| `company_research.json` / `.md` | Verified company context and sources |
| `tailor_plan.json` / `.md` | JD focus, evidence map, CV strategy and four-slot cover-letter blueprint |
| `materials_status.md` | Quality blockers and next action |
| `base_master_ref.txt` | Reference to the fact-checked A–F master |
| `jd_full.md` | Full JD and provenance |

`tailor_plan.json.low_model_contract` defines the required execution order so a
less capable model cannot skip preflight, company research, evidence mapping,
fact checking or PDF validation.

## PDF

After editing package copies of the DOCX masters:

```bash
python3 tools/fresh_24h/docx_to_pdf.py \
  'path/to/CV.docx' --engine libreoffice
python3 tools/fresh_24h/docx_to_pdf.py \
  'path/to/Cover Letter.docx' --engine libreoffice
```

Both PDFs must pass the one-page, text-layer, font and stale-cache checks in
`docs/system_rules.md`.
