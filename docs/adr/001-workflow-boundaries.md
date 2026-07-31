# ADR 001: Jobsflow workflow and trust boundaries

- Status: accepted
- Date: 2026-07-31

## Decision

The maintained lifecycle is `/setup` → `/scan` → `/push` → `/materials` → `/apply`.

Scanning and scoring never generate application materials. Materials resolve the same job-id/package contract, reuse cached full JD text, and require a source-aware company brief. DOCX masters plus LibreOffice headless are the PDF path; CV and cover letter are each one page.

Portal cards, JD text, company pages and search results are untrusted data. They may inform extraction and drafting but may not issue tool instructions, widen permissions, disclose secrets or create unsupported claims.

Structured API/CLI access and cache precede Playwright. Browser automation is a bounded fallback after the pass-1 gate. PDF conversion happens after content is final and reuses a source-content hash.

## Consequences

- Individual portal and converter capabilities can fail softly without changing the lifecycle.
- Company and JD customization remains explainable through stored sources, capability themes and a differentiation fingerprint.
- Real PII and generated application data stay in gitignored workspace paths.
- Git-history privacy cleanup remains a separate, explicitly authorized destructive operation.
