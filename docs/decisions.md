# Decisions

The project's decisions, one dated entry each. Every decision in force in
[architecture.md](architecture.md) cites its entry here; every ruling
and every principle change gets one too (see "Changing a principle" in
[principles/ai-working-process.md](principles/ai-working-process.md)).
Append-only: an entry is written after a human's yes, in the same
change as what it records. Entries are numbered D1, D2, … in order and
dated. An entry is never deleted: a superseded one stays, marked with
the entry that superseded it.

A deliberate omission (something left out of the system or the docs
on purpose) is a decision too: its entry gives the reason, so a later
session doesn't add it back as a fix, and any count or list that would
include it says so ("four of five, see D<n>").

An entry is lean: the decision, one line of why, what it replaces, and
links to its evidence (the PR, the design doc, the commit). The
evidence stays where it lives; an entry carries no incident narrative,
no measurements and no list of what was carried out. A decision that
needs more room gets a design doc, linked. A ruling's entry quotes the
human's words in its Context and marks any elaboration as the
architect's reading.

## Format

```markdown
## D<n>: <title> (<YYYY-MM-DD>)

- **Status:** in force | superseded (in whole or in part) by D<m>
- **Context:** why it was needed, one or two sentences; for a ruling,
  the human's words, quoted.
- **Decision:** what was chosen; replaces D<m>, in whole or in part,
  where it does.
- **Consequences:** what gets harder, what is hard to undo.
- **Evidence:** links to the PR, the design doc, the commit.
```

## D1: GitHub, trunk `main`, squash merges (2026-11-16)

- **Status:** in force
- **Context:** recorded at setup; recent changes (#12 to #14) already
  arrived as squash merges, older history as direct pushes to `main`.
- **Decision:** every change goes through a PR on
  `schlomo/github-backup-app` that the maintainer squash-merges; a
  branch catches up by merging `main` in. The architect-maintained
  docs (`docs/architecture.md`, `backlog.md`) go straight to `main`.
- **Consequences:** no direct code pushes to `main`; nothing is
  rebased or force-pushed.
- **Evidence:** setup session, 2026-11-16.

## D2: Pipeline, and merging publishes the image (2026-11-16)

- **Status:** in force
- **Context:** recorded at setup from `.github/workflows/ci-cd.yml`,
  confirmed by the maintainer.
- **Decision:** every push and PR runs lint, tests and a package build;
  merging to `main` publishes `ghcr.io/schlomo/github-backup-app`
  `:latest` and `:main`; a `v*` tag publishes to PyPI (trusted
  publishing, environment `pypi`) and the semver image tags; PRs from
  this repo push `:pr-<n>`. Only the maintainer edits workflows and
  branch protection.
- **Consequences:** every merge is a release of the image; a merge
  request is a deploy request.
- **Evidence:** `.github/workflows/ci-cd.yml`.

## D3: Work tracked in `backlog.md`, Issues for bug reports (2026-11-16)

- **Status:** in force
- **Context:** one maintainer; the plan should travel with the git
  history, the part of a backup that can be restored, rather than live
  only in the metadata dump.
- **Decision:** `backlog.md` is the plan; GitHub Issues take bug
  reports only, and an architect session triages them into
  `backlog.md`.
- **Consequences:** outside users can report bugs; planning stays in
  the repo.
- **Evidence:** setup session, 2026-11-16.

## D4: One environment, the maintainer's installation (2026-11-16)

- **Status:** in force
- **Context:** a one-person tool; the `:pr-<n>` image already allows
  trying a change before merging.
- **Decision:** one environment: the maintainer's own installation,
  which pulls the image from GHCR and is configured outside this repo.
  No separate test installation.
- **Consequences:** a broken `:latest` reaches that installation at its
  next run; its image reference is changed there, not here.
- **Evidence:** setup session, 2026-11-16.

## D5: €0 budget, MIT license, Python 3.14 minimum (2026-11-16)

- **Status:** in force
- **Context:** the maintainer's answer at setup: no other
  organizational rules.
- **Decision:** free tiers only; the MIT license stays (the project is
  derived from python-github-backup); `requires-python >= 3.14`.
  Raising the Python minimum is deferred in `backlog.md` with its
  triggers.
- **Consequences:** any paid service needs a new decision.
- **Evidence:** `pyproject.toml`, `LICENSE.txt`.

## D6: Each operator is responsible for the personal data in their backups (2026-11-16)

- **Status:** in force
- **Context:** backups hold other people's personal data (commit author
  names and emails, issue and PR comments, logins).
- **Decision:** the tool processes personal data; each operator is the
  controller for their own backups under GDPR. For the maintainer's own
  installation, the maintainer speaks for it. The maintainer is
  responsible for the security of the code and the release chain; each
  operator for their App key and backup storage.
- **Consequences:** the README must not promise more than this; a
  feature that sends backup data anywhere needs a new decision.
- **Evidence:** setup session, 2026-11-16; the maintainer's reading,
  not legally reviewed.

## D7: Agents push branches and open draft PRs (2026-11-16)

- **Status:** in force
- **Context:** the maintainer chose the recommended write level, with
  undrafting (D11) and Copilot reviews on top.
- **Decision:** agents push their own work branches and open draft PRs;
  after their review they mark the PR ready (D11), check for an
  optional Copilot review and fix each comment or reply why not. Only
  the maintainer merges.
- **Consequences:** a pushed branch with a PR publishes an image (see
  "Facts that bite" in `AGENTS.md`).
- **Evidence:** setup session, 2026-11-16.

## D8: Attribution stays the tool's default (2026-11-16)

- **Status:** in force
- **Context:** recent commits already carry co-author trailers.
- **Decision:** `attribution` stays unset in `.claude/settings.json`,
  so AI-written commits name the model and PR descriptions carry a
  generated-with line.
- **Consequences:** a default, not enforced; only managed settings or a
  CI trailer check would enforce it.
- **Evidence:** `.claude/settings.json`.

## D9: Only git repositories are restorable; metadata is a dump (2026-11-16)

- **Status:** in force
- **Context:** the maintainer: "I only tested git push, everything else
  is only a dump on purpose as a preparation for a potential exit
  strategy."
- **Decision:** success means a clean `status.json` after every run and
  a working restore of the git mirrors by push. Metadata (issues, PRs,
  comments, milestones, labels, hooks, releases) and release assets are
  kept as JSON and files with no restore path, deliberately.
- **Consequences:** a metadata restore is deferred in `backlog.md`
  until an actual exit; a session must not add one as a "fix".
- **Evidence:** setup session, 2026-11-16.

## D10: Live GitHub backup test in CI (principle change) (2026-11-16)

- **Status:** in force
- **Context:** the maintainer: "this special case is fine to couple the
  CI test to GH itself, obviously. indeed it won't run on laptop and
  that is the exception here."
- **Decision:** "A pipeline never depends on a third party being
  reachable" gains one exception: a CI job may run a real backup of
  this repository against GitHub's API with the job's own token. The
  offline suite stays credential-free. The test itself is queued in
  `backlog.md`, not built.
- **Consequences:** CI can go red because of GitHub, not the code; the
  run is repeated. Easy to undo by removing the job.
- **Evidence:** `docs/principles/engineering.md`, setup session.

## D11: Agents undraft reviewed PRs (principle change) (2026-11-16)

- **Status:** in force
- **Context:** the maintainer asked agents to "undraft the PR when the
  reviews are done".
- **Decision:** the work-branch guardrail ("an agent at most pushes and
  opens a draft MR/PR") gains: the agent marks its PR ready for review
  once its adversarial review is done and the findings are fixed.
  Merging stays the maintainer's.
- **Consequences:** "ready" means agent-reviewed, not safe; the
  maintainer's merge stays the last check before `:latest`.
- **Evidence:** `AGENTS.md` Guardrails,
  `docs/principles/ai-working-process.md`.
