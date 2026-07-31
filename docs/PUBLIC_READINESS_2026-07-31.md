# JobsFlow public-readiness score

Date: 2026-07-31

## Verdict

The repaired **source is suitable for a clean public release candidate**, but the
current Git repository is **not publishable as-is**.

- Engineering/product quality: **86/100**
- Clean-snapshot release readiness: **88/100**
- Current repository publish readiness: **74/100**

The difference is release hygiene, not the user's private working data: old Git
objects contain private workspace paths and two oversized binaries, while the
working tree has not yet been reviewed and committed.

## Audit-domain scoring

| Domain | Score | Current evidence |
|--------|------:|------------------|
| Security and supply chain | 4.5/5 | locked dependencies, CI guards, minimal Sheets scope, injection defenses |
| Privacy and data protection | 3.6/5 | current source/private boundary is strong; old history remains unsafe |
| Code quality and architecture | 4.0/5 | policy/IO/research/contracts extracted; some orchestration modules remain large |
| Reliability and resilience | 4.4/5 | atomic local writes, cursor protection, bounded retries/browser budgets, honest degradation |
| Tests and verification | 4.5/5 | 126 Python tests, four portal suites/typechecks, Python 3.12 doctor clean |
| Documentation and onboarding | 4.5/5 | unified commands, private setup, machine-readable doctor, public release/security docs |
| Workflow completeness | 4.5/5 | setup→scan→track→materials→apply contracts align; clean synthetic E2E remains |
| AI agent governance | 4.8/5 | deterministic preflight, schema validation, source/evidence gates, untrusted-content boundary |
| **Overall** | **4.3/5** | **86/100** |

## Public gates

| Gate | Status |
|------|--------|
| Industry-neutral source and examples | PASS |
| Product/private workspace isolation | PASS for current source |
| Personal template guard | PASS |
| Source release check | PASS |
| Python 3.12 locked-environment tests | PASS |
| Portal offline tests/typechecks | PASS |
| Security and onboarding documentation | PASS |
| Clean Git history | FAIL on current repository |
| Clean working tree / reviewed commit | FAIL |
| Clean-clone synthetic end-to-end smoke | PENDING |
| Hosted CI and branch protection | PENDING |

## Publication decision

Do not switch the current remote to public. Build a new repository from the
reviewed source snapshot, preserve the MIT license and upstream attribution, run
the full checks there, and publish only that clean history. The existing private
repository and `JobSearch_2026/` remain the user's separate job-search line.
