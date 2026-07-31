# Security policy

## Supported version

Security fixes are applied to the current `main` branch.

## Reporting

Do not open a public issue containing secrets, résumé data, tracker exports,
application materials or a reproducible exploit. Use GitHub's private security
advisory feature for this repository. If that feature is unavailable, contact the
maintainer through the private address listed on the repository profile.

Include the affected version, impact, minimal reproduction and suggested
mitigation. Remove real candidate data from logs and examples.

## Data boundary

`JobSearch_2026/`, `.env` and personal configuration are local runtime data and
must never be committed. External LLMs, Google Sheets and portal requests are
opt-in data transfers governed by their providers. JobsFlow does not
automatically submit applications.
