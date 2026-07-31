# Private documents intake (optional)

`documents/` is a gitignored convenience folder for source material you want
`/setup`, `/expand`, or `/interview` to read. It is not the product's public
profile and it is not the primary application-materials store.

## Accepted intake files

`/setup` reads `.pdf`, `.docx`, `.txt`, `.md`, and `.json` files from the folder
passed with `--resume-folder` (or from a folder selected in chat). A `.tex` file
is not required or treated as the default CV format. Keep the most complete CV
here; tailored files belong in the private JobSearch workspace.

```text
documents/
├── cv/            # source CVs or résumé exports
├── linkedin/      # optional LinkedIn PDF export
├── diplomas/      # optional qualifications/transcripts
├── references/    # optional reference letters
└── applications/  # compatibility intake archive, if you already have one
```

The current runtime keeps parsed résumé evidence in:

```text
JobSearch_2026/00_Profile/resume_runtime/resume.txt
```

That private file is what the A–F base fact-check can consume after `/setup`.
Tracked files under `.claude/skills/` remain placeholders and must never be
filled with personal details.

## Application archive

New application packages live under the private workspace, not in tracked
product files:

```text
JobSearch_2026/01_Masters/<direction>/<tier>/<job-id>_<status>_<company>/
JobSearch_2026/03_Applications/<company>_<role>/
```

The package holds the selected JD, company research, tailor plan, copied DOCX
materials, and generated PDFs. The application archive holds the submitted
versions and outcome history. `/outcome` writes the archive and updates the
local tracker; it does not create the removed legacy `job_search_tracker.csv`.

An outcome file uses this stable format:

```markdown
# Outcome: <Company> — <Role>

**Status:** in_progress | hired | offer_declined | rejected | no_response | interview_only

**Date resolved:** YYYY-MM-DD

## Interview stages reached
- [ ] Phone screen
- [ ] Technical interview
- [ ] Case interview
- [ ] Final round
- [ ] Offer received

## Notes
What happened? What feedback did you receive? What would you do differently?
```

Only final outcomes are used for later calibration. Do not place real names,
contact details, or filled CV/CL files in the tracked repository; reset or remove
the private intake files when you no longer want them retained.
