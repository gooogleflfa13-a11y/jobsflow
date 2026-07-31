# Public release procedure

The product source and a candidate's private job-search workspace are separate.
A release is public-ready only when both the current source and its Git history
are clean.

## Required checks

```bash
python3 tools/security_guards.py
python3 tools/public_release_check.py --source
python3 -m pytest -q
git diff --check
```

Before publishing an existing repository, also run:

```bash
python3 tools/public_release_check.py --history
```

`--history` checks the release `HEAD` by default. If you intentionally need to
audit unrelated local or upstream refs as well, use
`python3 tools/public_release_check.py --history --all-refs`; those refs are not
part of the public branch unless they are pushed.

If history contains `JobSearch_2026/`, filled templates or other candidate data,
do not push that history to a public remote. Create a new repository from a
reviewed source snapshot, preserve `LICENSE` and upstream attribution, run the
checks again in the clean repository, and publish only that new history.

Never “clean” the working repository by deleting the user's private workspace.
History repair and personal-data retention are different operations.
