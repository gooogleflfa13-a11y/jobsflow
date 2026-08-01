# JobsFlow

[中文](README.md) · [English](README_EN.md)

## Find the right roles. Write like the role. Apply with confidence.

JobsFlow connects job search, company research, JD analysis, tailored CVs,
cover letters, and application review in one local-first workflow. It is not
just an AI resume writer: it helps you decide what to apply for, why you fit,
and how to tailor the application without giving up final control.

- **Fewer wasted applications:** two-pass scoring filters before deep JD work.
- **More relevant materials:** company context and JD priorities drive the CV and cover letter.
- **Reliable with smaller models:** deterministic preflight, evidence mapping, and quality gates prevent silent skips.
- **Always user-approved:** JobsFlow never auto-submits an application.

```text
CV + intent → setup → search → quick score → JD deep read
           → company research → tailored CV/cover letter → your approval
```

### Why JobsFlow?

| Generic AI job tool | JobsFlow |
|---|---|
| Generates as soon as it sees a JD | Checks salary, language, work authorization, qualifications and attachments first |
| Rewrites keywords only | Researches the company, business and role context |
| Reuses one resume everywhere | Builds direction-specific bases, then tailors per JD |
| Silently skips what a weaker model missed | Enforces schemas, gates, source checks and coverage checks |
| Uses a fixed industry template | Generates industry-aware directions from your CV and intent |

### Our LLMO strategy

JobsFlow does not rely on keyword stuffing. It connects **JD requirements →
verified evidence → CV / cover letter / application email** in one traceable
chain, then places the strongest supported evidence where ATS and model readers
can parse it early. The goal is to make real capability easier to understand—not
to fabricate experience, manipulate ATS, or promise a fixed score increase.

For deep-JD scoring, resume matching can also use **agent-in-the-loop semantic
matching**. JobsFlow keeps a fact anchor separate from a capability upper bound,
then asks the agent executing the job-search task to compare that profile with
the JD's core duties. During `/setup`, the user chooses a low (conservative),
medium (balanced), or high (broader) upper-bound calibration. This only changes
the permitted transfer range and deterministic score caps; no setting turns
potential into claimed experience. If a semantic verdict is not completed, the
keyword score remains the explicit fallback and scanning continues.

## Quick start

```bash
git clone https://github.com/gooogleflfa13-a11y/jobsflow.git
cd jobsflow
PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3)"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), "JobsFlow requires Python 3.10+"'
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes -r requirements.lock
python3 setup.py --doctor
python3 setup.py --resume-folder ~/Documents/my-cv
python3 setup.py --install-portals
```

Then use:

```text
/scan
/push (or /push --local-only for a CSV-only tracker)
/materials C0-005 C
/apply C0-005 C
```

During `/setup`, the assistant can propose A–F directions, scoring weights and
tracker columns based on the user's résumé evidence, stated constraints and
industry context. The proposal is constrained by a machine-readable schema and
is written only to the private workspace; invalid output falls back to the
deterministic cross-industry configuration.

Job intent can evolve safely after setup. Use `/intent add ...` to add a
direction or `/intent replace ...` to replace the search scope. JobsFlow turns
the natural-language update into role and industry keywords and shows a preview
first; only an explicit `/intent confirm` writes the private search
configuration. The next `/scan` uses the new configuration, while historical
tracker rows and existing materials remain unchanged. If it is unclear whether
the user wants to add or replace a direction, the assistant asks first.

`/scan` defaults to the period since the last successful refresh. Use `/scan daily` for 24 hours or `/scan 3` for three hours. A failed portal run does not advance the refresh cursor.

## Materials

Materials use a fact-checked A–F base, full-JD cache, and a source-aware company brief. CV emphasis changes with the JD capability themes and company context. Cover letters use verified company facts and a genuine candidate interest angle; unsupported metrics, experience, company claims, or interest are never invented.

A deterministic preflight extracts salary, availability, work authorization, language/licence, experience and attachment requirements. The system then produces an evidence map, four-slot cover-letter blueprint and quality gate, so models with different capability levels follow the same analysis rather than improvising or silently skipping questions.

DOCX masters remain the source. LibreOffice runs headlessly, CVs and cover letters default to one page (unless you explicitly need otherwise), and unchanged documents reuse a content-hash PDF cache.

Example: for a JD asking for experience developing, implementing and monitoring an
operational program, JobsFlow separates process design, execution and monitoring;
it prioritizes matching evidence and asks about gaps instead of inventing metrics.

### LLMO details: make real evidence easier to read correctly

JobsFlow treats LLMO as an auditable material contract—not writing a candidate into
model memory and not an ATS-score promise:

- every fact-checked experience gets a stable `evidence_id`, allowed wording and forbidden inferences;
- JD anchors are tiered and labelled `covered`, `partial`, `uncovered` or `prohibited_to_claim`;
- the CV, cover letter and application email share one evidence graph and the same numeric facts;
- parseability is protected with selectable single-column text, standard sections and contact details outside images/text boxes/headers/footers;
- QA metrics are internal engineering indicators, never an official ATS score or hiring prediction.

This gives models with different capability levels an executable boundary: the model
reorders and rephrases mapped evidence instead of having to infer the whole JD or
fill unsupported gaps.

## Sources and privacy

Supported sources are LinkedIn, JobsDB, CTgoodjobs and FreeHire. Browser automation is a last fallback after structured APIs and cache.

| Source | Search | Deep JD | Materials note |
|---|:---:|:---:|---|
| LinkedIn | ✓ | ✓ | Deep JD is preferred and cached for reuse |
| JobsDB | ✓ | Partial | Paste the full JD when preparing materials |
| CTgoodjobs | ✓ | Partial | Paste the full JD when preparing materials |
| FreeHire | ✓ | Manual | Additional job source; detail can be queried by posting ID |

The default workflow is local-first. Data leaves the machine only when you explicitly enable Google Sheets, an external LLM, or a portal request. Review each service’s terms and privacy policy. JobsFlow never auto-submits an application.
Google Sheets is not a job source; it is an optional tracker-sync destination. Local CSV tracking works without it.
LinkedIn accepts a user-specified location; the current JobsDB and CTgoodjobs integrations target Hong Kong; FreeHire covers multiple markets but its strongest filtering is currently technical roles.

## Folder + tracker: a portable application workspace

JobsFlow uses two layers: **folders hold materials and evidence; CSV or Google
Sheets holds job metadata and status**. This keeps the application record portable
and prevents important files from getting lost in a spreadsheet or chat thread.

```text
JobSearch_2026/
├── 00_Profile/                    # CV facts, intent and search configuration
├── 01_Masters/                   # A–F direction masters and job packages
│   └── <direction>/<tier>/<job-id_company>/
│       ├── jd_full.md             # Full JD
│       ├── company_research.md    # Company facts, business and sources
│       ├── application_preflight.json
│       ├── tailor_plan.md         # JD → candidate evidence map
│       └── CV / Cover Letter / PDF
├── 02_Tracker/                   # CSV tracker, JD cache and scan outputs
└── 03_Applications/              # Optional final-application archive
```

| Content | Folder workspace | CSV / Google Sheets |
|---|:---:|:---:|
| JD, company research and evidence map | ✓ | — |
| CV, cover letter and PDF | ✓ | — |
| Match score, priority and application status | — | ✓ |
| Material versions and change history | ✓ | Link only, if useful |

Each job ID connects the tracker row to its material package. You can back up the
whole private workspace, review why a decision was made, and use local CSV without
Google Sheets; Sheets is an optional tracker sync, not a CV or cover-letter store.

See [SETUP.md](SETUP.md), [docs/system_rules.md](docs/system_rules.md), and [docs/tracker_defaults.md](docs/tracker_defaults.md).

## Privacy, safety and public release

The public source is the product line. A user's résumé, queries, job descriptions,
scores, and application tracker belong to the separate private `JobSearch_2026/`
workspace and are ignored by default. `/setup` generates industry-aware directions,
tracker headers, scoring weights, and material priorities from that user's intent;
legal/compliance is not a built-in default.

Deterministic preflight, schema validation, scoring gates, source checks, evidence
mapping, coverage checks, and PDF checks remain in force even with a model of limited
capability. A stronger model improves research and wording, but cannot bypass the safety
boundaries or invent facts.

Before publishing a reviewed snapshot, run:

```bash
python3 setup.py --doctor-json
python3 tools/security_guards.py
python3 tools/public_release_check.py --source
python3 tools/public_release_check.py --history
pytest -q
```

See [PUBLIC_RELEASE.md](PUBLIC_RELEASE.md) for release hygiene and history handling.

## FAQ

**Can I use it outside legal or compliance?** Yes. Setup generates directions and
tracker headers from your target industry; legal/compliance is not a default.

**Does it work with models with different capability levels?** Yes. Models improve research and
wording, while deterministic checks enforce the important boundaries.

**Does it upload my CV?** Not by default. Data leaves the machine only when you
explicitly enable an external LLM, Google Sheets, or a portal request.
