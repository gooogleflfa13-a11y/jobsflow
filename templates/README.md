# Public template boundary

The active template registry is private and lives under:

```text
JobSearch_2026/00_Profile/templates/<name>/
├── template.docx
└── TEMPLATE.md
```

`/add-template` stores profile-agnostic templates there, asks for the complete
conversion and validation contract, and performs a trial export before the
template can be used. `/apply` uses the documented DOCX → LibreOffice headless
PDF path; a LaTeX-only or two-page default is not part of the product contract.

Do not commit filled CVs, Cover Letters, fonts, or personal template files to
this tracked directory. Legacy `.tex` examples may remain for compatibility but
are not required by the validator or the current application workflow.
