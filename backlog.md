# Backlog

Plan for `github-backup-app` and its known gaps. The guiding rules for
every change live in [docs/architecture.md](docs/architecture.md)
("Guiding principles"). Each numbered step is meant to be its own PR
that is tested and can be undone on its own. Bug reports arrive as
GitHub Issues and are triaged into this file.

## Next session starts here

Setup is done (2026-11-16). Start with Queued item 1, the supersession
research: its answer decides whether the rest is worth building.

## In flight

Nothing.

## Queued

In this order:

1. **Is this project still needed?** Thorough research whether a
   better-maintained tool now covers multi-account GitHub App backups
   with incremental runs, git mirrors that never lose refs, and a
   metadata dump. Outcome: continue, or a migration recommendation. Its
   comparison also feeds the README cleanup (item 4).
2. **PR images share the release package** (security; promoted from
   the known limitations because agents now push branches).
   Anyone who can push a branch to
   this repository can change the workflow and push any tag, including
   `:latest`. Move PR images to a separate package or gate them behind an
   approval; pin actions by commit SHA instead of tag; pin `uv`.
3. **Agent-driven release minting.** The agent bumps the version and
   writes release notes from the merged PRs in a PR, then prepares a
   draft GitHub release; the maintainer publishes it, which tags `v*`
   and triggers PyPI. Replaces copy-pasting release text by hand.
   Needs a design first.
4. **Refactor**, the plan below, extended by:
   - **Token injection seam:** the backup code takes a token and never
     cares where it came from (App installation token, CI job token),
     so the same code runs in production and in the live test.
   - **Live backup test in CI** (allowed by D10): back up this
     repository with the CI job's `GITHUB_TOKEN` against the real API
     and assert the result. It does not cover the App's JWT-to-token
     exchange; the dedicated test App idea under "Test and release
     gaps" would. Whether it gates merges is decided in its design.
   - **More exhaustive tests** beyond the characterization tests of
     the refactoring plan's step 2.
   - **README cleanup:** describe the tool in its own terms and shrink
     the comparison with python-github-backup as the two diverge.

### Refactoring plan

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

### Test and release gaps

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

### Known limitations and follow-ups

From the second adversarial review (not fixed in 0.4.0):

- **First clones cannot resume.** A failed first clone is discarded
  (`repository.new-mirror/`) and starts over on the next run; a very large
  repository on a flaky connection may never finish.
- **Case-insensitive filesystems** (some NAS/SMB mounts, macOS): refs that
  differ only in case make the fetch fail on every run (loudly).
- **A wiki that was never backed up** is skipped when GitHub answers "not
  found", which GitHub also says for some permission problems.
- **Tests that change file ownership need root** and are skipped on
  GitHub-hosted CI.
- **Duplicate archive refs** can appear if a run is killed while archiving
  (the journal is replayed under a new timestamp). Harmless, but noisy.
- **Ownership is not auto-trusted.** A backup directory owned by a different
  uid fails with a clear "dubious ownership" error rather than setting
  `safe.directory`; deliberate, documented in the README.
- **Feature gaps vs. python-github-backup:** gists, starred repositories,
  discussions, security advisories, user attachments.

## Deliberately deferred

- **Raising the Python minimum above 3.14.** Deferred: 3.14 is fine
  (D5). Revisit when a dependency drops 3.14, a newer Python offers
  something the code clearly benefits from, or 3.14 nears end of life
  (October 2030); a session that notices one says so.
- **Restoring metadata and release assets.** Deferred on purpose: they
  are a dump kept for a possible exit from GitHub (D9). Revisit only
  for an actual exit.
- **Archive refs are kept forever.** `refs/backup/*` grows with every
  deletion/force-push. Usually tiny, but a retention option (e.g. keep N days)
  may be wanted eventually; it must never drop the only copy of a commit
  silently.

## Done (recent)

- 2026-11-16: project setup recorded (`AGENTS.md`, `docs/`).
