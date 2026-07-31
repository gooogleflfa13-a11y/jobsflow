# JobsFlow

JobsFlow is a local-first job-search workflow: configure from an existing CV, scan scoped portals, rank jobs in two passes, track them, and create a company/JD-aware application package only when you select a role.

## Quick start

```bash
git clone https://github.com/gooogleflfa13-a11y/jobsflow.git
cd jobsflow
PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3)"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), "JobsFlow requires Python 3.10+"'
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.lock
python3 setup.py --doctor
python3 setup.py --resume-folder ~/Documents/my-cv
python3 setup.py --install-portals
```

Then use:

```text
/scan
/push
/materials C0-005 C
/apply C0-005 C
```

During `/setup`, the assistant can propose A–F directions, scoring weights and
tracker columns based on the user's résumé evidence, stated constraints and
industry context. The proposal is constrained by a machine-readable schema and
is written only to the private workspace; invalid output falls back to the
deterministic cross-industry configuration.

`/scan` defaults to the period since the last successful refresh. Use `/scan daily` for 24 hours or `/scan 3` for three hours. A failed portal run does not advance the refresh cursor.

## Materials

Materials use a fact-checked A–F base, full-JD cache, and a source-aware company brief. CV emphasis changes with the JD capability themes and company context. Cover letters use verified company facts and a genuine candidate interest angle; unsupported metrics, experience, company claims, or interest are never invented.

A deterministic preflight extracts salary, availability, work authorization, language/licence, experience and attachment requirements. The system then produces an evidence map, four-slot cover-letter blueprint and quality gate, so lower-capability models follow the same analysis rather than improvising or silently skipping questions.

DOCX masters remain the source. LibreOffice runs headlessly, both CV and cover letter are one page, and unchanged documents reuse a content-hash PDF cache.

## Sources and privacy

Supported sources are LinkedIn, JobsDB, CTgoodjobs and FreeHire. Browser automation is a last fallback after structured APIs and cache.

The default workflow is local-first. Data leaves the machine only when you explicitly enable Google Sheets, an external LLM, or a portal request. Review each service’s terms and privacy policy. JobsFlow never auto-submits an application.

See [SETUP.md](SETUP.md), [docs/system_rules.md](docs/system_rules.md), and [docs/tracker_defaults.md](docs/tracker_defaults.md).

## Public release and product/personal isolation

The public source is the product line. A user's résumé, queries, job descriptions,
scores, and application tracker belong to the separate private `JobSearch_2026/`
workspace and are ignored by default. `/setup` generates industry-aware directions,
tracker headers, scoring weights, and material priorities from that user's intent;
legal/compliance is not a built-in default.

Deterministic preflight, schema validation, scoring gates, source checks, evidence
mapping, coverage checks, and PDF checks remain in force even with a lower-capability
model. A stronger model improves research and wording, but cannot bypass the safety
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
