# Backlog

Plan for turning `github-backup-app` into maintainable software, plus known
gaps. Written alongside the 0.4.0 mirror rewrite; each numbered step is meant
to be its own PR that is tested and can be undone on its own.

## Guiding rules

- **Correctness before speed.** A backup that silently misses data is worse
  than a slow one. Every "skip" must be provably safe.
- **One error model.** A repository either fully succeeds (and only then
  writes `repo.json`) or is reported in `status.json` as failed. No step may
  swallow an error and continue as if it had succeeded. Every defect found in
  the 0.4.0 review was a violation of this rule.
- **Refactors do not change behaviour.** Behaviour changes and structural
  changes never share a PR.
- **KISS.** Target about six modules of 300-600 lines each. No frameworks, no
  plugin system, no abstraction without a second user.

## Refactoring plan

1. **Extract the git layer unchanged** into `github_backup/git_mirror.py`
   (everything from `GIT_FETCH_REFSPECS` to `fetch_repository`, plus
   `get_git_auth_env`'s git half). Pure move; `tests/test_git_mirror.py`
   pins the behaviour. Low risk, do first.
2. **Characterization tests for the API side**, before touching it. Fake
   `requests.Session` with recorded GitHub responses (REST pages, GraphQL
   bundle), covering:
   - per-item `updated_at` skips for issues, pull requests, milestones
   - pagination and rate-limit/throttle handling
   - partial failures (one sub-resource fails, which must fail the
     repository, not write `repo.json`)
   - release asset download skip
   - multi-installation discovery and the positional account filter
   Today this part has **no tests**; it is where silent data gaps would
   occur.
3. **Split the remaining module** (`github_backup.py`, ~3,200 lines) into:
   - `auth.py`: GitHub App JWT, installation tokens and their refresh
   - `api.py`: REST/GraphQL client on the shared session, retries, throttling
   - `metadata.py`: issues, pulls, milestones, labels, hooks, releases
   - `run.py`: orchestration, the per-repository error model, `status.json`
   - `cli.py`: argparse, mapped to a typed config dataclass instead of
     passing `argparse.Namespace` everywhere
4. **Delete code left over from the fork** while splitting: the `urllib`
   request path next to `requests`, `mask_password`, Windows-only branches,
   unused imports (`getpass`, `ssl`, ...), deprecated `codecs.open` (emits
   DeprecationWarning on 3.14). Use a coverage report to find dead code.
5. **Coverage gate in CI** (`pytest-cov`) for the new modules; keep the
   whole suite free of network access.

## Test and release gaps

- **PR images accumulate in GHCR.** Pull requests now publish `:pr-<number>`
  (with a `--help` smoke test and the build-time git version check). Add a
  cleanup of PR tags after merge/close, e.g. a scheduled
  `actions/delete-package-versions` job.
- **`--lfs` has no automated test.** git-lfs with the auth header was verified
  by hand during review (git-lfs 3.4.1: header reaches the LFS API, is not
  sent to storage on another host). Add a test with a local LFS server or the
  standalone file transfer agent.
- **No end-to-end test against real GitHub.** Consider a nightly job with a
  dedicated test organization and GitHub App that backs up a fixture repo
  (force-push, branch deletion, fork PR, wiki, LFS) and asserts the result.
- **`latest` follows `main`.** Users who pull `:latest` get storage-layout
  changes unattended. Publish versioned image tags from releases and document
  pinning them.

## Known limitations and follow-ups

- **Archive refs are kept forever.** `refs/backup/*` grows with every
  deletion/force-push. Usually tiny, but a retention option (e.g. keep N days)
  may be wanted eventually; it must never drop the only copy of a commit
  silently.
- **Duplicate archive refs** can appear if a run is killed while archiving
  (the journal is replayed under a new timestamp). Harmless, but noisy.
- **Ownership is not auto-trusted.** A backup directory owned by a different
  uid fails with a clear "dubious ownership" error rather than setting
  `safe.directory`; deliberate, documented in the README.
- **Feature gaps vs. python-github-backup:** gists, starred repositories,
  discussions, security advisories, user attachments.
