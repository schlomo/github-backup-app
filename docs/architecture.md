# github-backup-app — architecture (current state)

github-backup-app backs up every GitHub account a GitHub App is
installed on (a public App, to cover several accounts) as local files:
git mirrors ready to push elsewhere or restore from, plus metadata and
release assets kept as a dump. It runs nightly, for people who keep
their own copy outside GitHub. It works when every run ends with a clean `status.json`
and the git mirrors restore by push (D9).

Everything here is current and settled. Nothing here restates what
another file owns:

| For | Read |
|---|---|
| What this project is, concepts, worked examples | this project's own [README.md](../README.md) |
| Vocabulary, defined once, used verbatim | [glossary.md](glossary.md) |
| Principles: engineering, AI working process, context economy | [principles/](principles/) |
| Decisions and rulings, dated, superseded ones kept | [decisions.md](decisions.md) |
| Detailed designs | [design/](design/) |
| Known failures, keyed by their exact error text | [troubleshooting.md](troubleshooting.md) |
| Work in flight, queued, deliberately deferred | [../backlog.md](../backlog.md) |

**Stakeholders:** users, operators, and the one responsible for the
code's and release chain's security: the maintainer, who is also the
only known user and the one paying. Legally affected: the
people whose personal data sits in the backups; each operator is the
controller for their own backups, and the maintainer speaks for the
maintainer's NAS (D6).

## 1. Guiding principles

Moved from `backlog.md` at setup; they shape every change below.

- **Correctness before speed.** A backup that silently misses data is
  worse than a slow one. Every "skip" must be provably safe.
- **One error model.** A repository either fully succeeds (and only
  then writes `repo.json`) or is reported in `status.json` as failed.
  No step may swallow an error and continue as if it had succeeded.
  Every defect found in the 0.4.0 review was a violation of this rule.
- **Refactors do not change behaviour.** Behaviour changes and
  structural changes never share a PR.
- **KISS.** Target about six modules of 300-600 lines each. No
  frameworks, no plugin system, no abstraction without a second user.

## 2. Shape

- **CLI `github-backup`** (`github_backup/__main__.py`,
  `github_backup/github_backup.py`): authenticates as the GitHub App,
  discovers every installation (filtered by positional account
  arguments), and per repository writes a git mirror, metadata JSON and
  release assets under `{output}/{owner}/repositories/{repo}/`, then a
  run summary in `status.json`. Today one module of about 3,500 lines;
  the split is queued in `backlog.md`.
- **Helper `github-backup-create-app`**
  (`github_backup/create_github_app.py`): a local web page that creates
  the GitHub App with the right permissions.
- **Distribution:** PyPI package and a multi-arch container image on
  GHCR (D2).

## 3. Decisions in force

### Delivery

GitHub, trunk `main`, squash merges by the maintainer; architect docs
go straight to `main` (D1). CI lints, tests and builds every PR and
every push that changes a build input; such a push to `main` publishes
the `:latest` image, docs-only pushes publish nothing, and a `v*` tag
publishes PyPI. The sdist holds only the package, its tests, README and
license (D2).
Agents push branches, open draft PRs and undraft them once reviewed
(D7, D11). Attribution is the tool's default (D8).

### Testing

The offline suite runs on every change and needs no network and no
credentials. It gates publishing (the image and PyPI jobs wait for it);
it does not yet block merging, since `main` has no required checks
(queued in `backlog.md`). A live backup test against GitHub in CI is
the one allowed exception to the third-party rule (D10), kept out of
the offline suite.

### Work tracking

`backlog.md`, with GitHub Issues for bug reports only (D3).

### Environments

One: the maintainer's NAS, configured outside this repo (D4).

### Constraints

MIT, Python 3.14 minimum (D5). Personal data in backups is each
operator's responsibility (D6). Only git mirrors are restorable;
metadata and release assets are a deliberate dump (D9).

## 4. Open questions

See [backlog.md](../backlog.md).
