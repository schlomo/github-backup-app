# GitHub Backup App

A modern Python application for backing up GitHub repositories and metadata using **GitHub App authentication**. It creates local backups of your git repositories, JSON metadata, and release assets — organized by account, ready to push elsewhere or restore from.

The intended workflow: create one private GitHub App, install it on every org and user account you want to back up, then run nightly. The tool discovers all installations automatically and backs up every accessible repository.

This project is a fork of [python-backup](https://github.com/josegonzalez/python-github-backup) with a different focus: **multi-installation GitHub App backups**, **automatic incremental runs**, and **much faster repeat backups** on large estates.

## What This Tool Does

- **Git repositories** — bare mirrors of all branches, tags and pull-request heads; deleted or force-pushed refs are archived, never lost; fetch skipped when no ref changed on GitHub
- **JSON metadata** — issues, pull requests, comments, milestones, labels, hooks, releases
- **Organized storage** — `{output}/{owner}/repositories/{repo}/…` mirrors GitHub's structure
- **GitHub App auth** — one app, many installations; no personal access tokens or SSH keys to rotate

## Key features

| Feature | Description |
|---------|-------------|
| **Multi-installation discovery** | One run backs up every org/user where the app is installed; filter with positional args (`jschule myorg`) |
| **Automatic incremental** | No `-i` flag and no separate state files — skip decisions come from the backup data on disk (`repo.json`, per-item JSON) |
| **Git skip** | One `git ls-remote` per repository; `git fetch` is skipped when every ref equals the backup |
| **Per-item metadata skip** | Unchanged issues/PRs/milestones skip comment/event/commit fetches and file rewrites |
| **GraphQL metadata bundle** | One paginated query per repo fetches issues, PRs, milestones, labels, and releases together |
| **HTTP keep-alive** | Shared `requests.Session` reuses TLS connections across API calls |
| **`status.json` monitoring** | Machine-readable run summary with `last_success_at`, skip counters, and exit codes for cron/NAS alerting |
| **Resilient runs** | Per-repository error isolation; Ctrl-C saves partial progress (exit `130`) |

## Comparison with python-backup

[python-backup](https://github.com/josegonzalez/python-github-backup) (PyPI: `github-backup`, v0.62+) is what this fork started from. It remains excellent for PAT-based backups with many optional resources (gists, starred repos, discussions, security advisories, attachments, …).

**What python-backup does *not* do** (and why repeat backups here are much faster):

| | python-backup | github-backup-app |
|---|---------------------|-------------------|
| **Git fetch on repeat runs** | Always runs `git fetch` when a clone exists | Skips fetch when `git ls-remote` shows no changed ref |
| **Metadata list API calls** | Separate REST list call per resource (issues ×2 states, pulls ×2, milestones, labels, releases, …) | One GraphQL query bundles issues, PRs, milestones, labels, releases |
| **HTTP connections** | `urllib` — new connection per request | `requests.Session` with keep-alive (~3× lower per-call latency) |
| **Incremental model** | Opt-in `-i` flag; `last_update` checkpoint files; API `since=` time filter | Always on; compares stored JSON timestamps; no checkpoint files |
| **Per-item skip** | Re-fetches and rewrites all items since the resource checkpoint | Skips unchanged items entirely (comments/events/commits not re-fetched) |
| **GraphQL usage** | Discussions only (REST has no discussions API) | Bulk metadata (issues, PRs, milestones, labels, releases) |
| **Run monitoring** | None | `status.json` with `last_success_at` and skip statistics |
| **Multi-installation App** | Single installation context | Auto-discovers all app installations |

python-backup still has features this fork does not yet support like gists, starred repos, discussions, security advisories, user-attachments, more granular flags. Or will not support like `--prefer-ssh`.

### Observed performance

Real runs on the same backup directory (incremental, `--all`):

| Scenario | Duration | Notes |
|----------|----------|-------|
| 5 repos — REST baseline | ~65s | Git skip only |
| 5 repos — GraphQL + Session | **~18s** | ~3.7× faster |
| 111 repos (5 installations) — GraphQL + Session | **~381s** | 110 git skips, 2223 issues + 1661 PRs skipped unchanged |

On a quiet estate where most repos haven't changed, the dominant cost shifts from git fetches and metadata listing to wiki probes and hooks (still REST-only). These numbers were measured with
the earlier `pushed_at`-based git skip, which needed no network call for
unchanged repositories; the current ref comparison adds one `git ls-remote`
round trip per repository and wiki.

## Quick Start

### Docker Quick Start (Recommended)

The fastest way to get started is with Docker:

```bash
# 1. Create GitHub App
mkdir -p ./creds
docker run --rm -it \
  --entrypoint github-backup-create-app \
  -u $(id -u):$(id -g) \
  -p 3000:3000 \
  -v "$(pwd)/creds:/creds" \
  ghcr.io/schlomo/github-backup-app:latest \
  --host 0.0.0.0 \
  /creds
```
This will:
1. Start a web server on port 3000
2. You'll need to open your browser to [http://localhost:3000](http://localhost:3000) to access the app creation interface
3. Guide you through creating a GitHub App
4. Save credentials to the `./creds` directory

```bash
# 2. Run backup
mkdir -p ./backup
docker run --rm -it \
  -u $(id -u):$(id -g) \
  -v "$(pwd)/backup:/data" \
  -v "$(pwd)/creds:/creds:ro" \
  ghcr.io/schlomo/github-backup-app:latest \
  --app-id $(cat ./creds/*-app-id.txt) \
  --private-key /creds/$(ls ./creds/*-private-key.pem | head -1 | xargs basename) \
  --all \
  --output-directory /data
```

## Installation

NOTE: Publication on PyPI is not planned, please use the Docker image instead or run your own build & delivery to where you need the package.

### Manual Installation with uv from GitHub

You can install it directly from the GitHub repository using [uv](https://github.com/astral-sh/uv):

```bash
# Install from GitHub repository
uv tool install github-backup-app --source https://github.com/schlomo/github-backup-app

# Or install in a virtual environment
uv venv
source .venv/bin/activate
uv pip install https://github.com/schlomo/github-backup-app
```

### 1. Create a GitHub App

#### Option A: Automated Creation (Recommended)

Use the provided automation script to create a GitHub App with the correct permissions:

```bash
source .venv/bin/activate
github-backup-create-app .
```

The script will:
1. Start a local web server with an HTML interface
2. Open your browser to the app creation interface
3. Guide you through a 3-step process to configure your app
4. Automatically handle the GitHub App creation and callback
5. Exchange the temporary code for permanent credentials
6. Save all credentials (App ID, private key, client secret) securely
7. Provide installation instructions

Take note of the App ID and private key. You will need them to run a backup.

#### Option B: Manual Creation

1. Go to your GitHub organization settings `https://github.com/organizations/YOUR_ORG/settings/apps` or your user settings [https://github.com/settings/apps](https://github.com/settings/apps)
2. Click "New GitHub App" and select "Private"
3. Configure permissions (see [GitHub App Setup](#github-app-setup) below) and click "Save"
4. Note the App ID
5. Generate and download the private key (PEM file)
6. Install the app on your organization or user account

Take note of the App ID and private key. You will need them to run a backup.

For detailed automation instructions, see [scripts/README.md](scripts/README.md).

### 2. Dry Run (See What Would Be Backed Up)

```bash
github-backup \
  --app-id YOUR_APP_ID \
  --private-key /path/to/your-app.pem \
  --dry-run
```

### 3. Run a Backup

```bash
# Basic backup of all repositories from all installations
github-backup \
  --app-id YOUR_APP_ID \
  --private-key /path/to/your-app.pem \
  --all \
  --output-directory ./backup

# Backup specific users/organizations only (using positional arguments)
github-backup \
  --app-id YOUR_APP_ID \
  --private-key /path/to/your-app.pem \
  --all \
  --output-directory ./backup \
  myorg myuser
```

## GitHub App Setup

NOTE: You can choose between *Public* and *Private* GitHub Apps. *Public* GitHub Apps are visible to the public and can be installed by anyone. *Private* GitHub Apps are only visible to the organization or user account that owns them and can only be installed by that organization or user account. If you choose *Public* GitHub Apps, you need to be careful with the organization filtering to avoid backing up unintended orgs as anybody can install your app. If you don't choose an organization filtering, the app will backup all orgs and users it has access to.

### Required Permissions

**Repository permissions** (Read access):
- Contents
- Issues
- Metadata
- Pull requests
- Repository hooks

**Organization permissions** (Read access):
- Members

### Installation

1. Install the app on your organization and/or user account
2. Choose "All repositories" for comprehensive access

## Command Line Options

```bash
github-backup --help
```

Key options:
- `--app-id`: Your GitHub App ID
- `--private-key`: Path to your GitHub App private key file
- `--output-directory`: Where to store the backup
- `--all`: Include nearly everything in backup
- `--dry-run`: Show what would be backed up without doing it

## Output Structure

Backups are organized as follows:

```
backup/
├── status.json                      # Run status for monitoring (see below)
├── organization1/
│   └── repositories/
│       ├── repo1/
│       │   ├── repo.json            # Repository metadata (also drives incremental skip)
│       │   ├── repository/          # Bare git mirror (see "Git repositories")
│       │   ├── wiki/                # Bare git mirror of the wiki (if any)
│       │   ├── issues/              # JSON files
│       │   ├── pulls/               # JSON files
│       │   └── milestones/          # JSON files
│       └── repo2/
└── organization2/
    └── repositories/
```

### Monitoring (`status.json`)

At the end of every run, a `status.json` file is written (atomically) to the
root of the output directory so you can monitor backups from cron/CI/NAS. It
always contains at least a `status` and a `finished_at` field:

```json
{
  "status": "success",
  "started_at": "2026-06-30T08:45:10.000000+00:00",
  "finished_at": "2026-06-30T08:49:58.755971+00:00",
  "duration_seconds": 288.756,
  "last_success_at": "2026-06-30T08:49:58.755971+00:00",
  "tool": "github-backup-app",
  "url": "https://github.com/schlomo/github-backup-app",
  "version": "0.3.0",
  "python_version": "3.14.6",
  "summary": {
    "installations": 5,
    "accounts": ["org1", "org2"],
    "repositories_total": 42,
    "repositories_succeeded": 42,
    "repositories_failed": 0,
    "repositories_git_skipped_unchanged": 110,
    "issues_skipped_unchanged": 2223,
    "pulls_skipped_unchanged": 1661,
    "milestones_skipped_unchanged": 24,
    "git_refs_archived": 3,
    "recovered_repositories": [],
    "failed_repositories": []
  }
}
```

The `status` field is one of:

- `success` — all repositories backed up successfully (exit code `0`)
- `partial` — the run completed but some repositories failed; see
  `summary.failed_repositories` (exit code `2`)
- `failed` — the run aborted with a fatal error; see the `error` field
  (exit code `1`)
- `interrupted` — the run was stopped with Ctrl-C; partial progress was saved
  (exit code `130`)

**Recommended monitoring:** alert when `last_success_at` is older than your
backup interval allows (e.g. > 48h). This field carries forward across failed
runs, so it stays accurate even if the tool has been failing for a long time —
catching exactly the kind of silent, long-running breakage that a simple
"did it run?" check would miss. The non-zero exit codes above also let cron/CI
detect failures directly.

### Git repositories

Each repository (and wiki) is stored as a **bare mirror** under `repository/`
(`wiki/`). A mirror contains:

| Ref | Content |
|-----|---------|
| `refs/heads/*` | every branch, exactly as on GitHub |
| `refs/tags/*` | every tag |
| `refs/notes/*` | git notes |
| `refs/pull/<n>/head` | the head of every pull request, including PRs from forks whose commits exist nowhere else in the repository |
| `refs/backup/<timestamp>/<ref>` | refs that GitHub **deleted or force-moved** since the previous run, preserved at their old commit |

GitHub's synthetic `refs/pull/<n>/merge` commits are not backed up.

**Nothing is silently destroyed.** Every branch, PR head or note that
disappeared on GitHub or moved in a way that drops commits (force-push), and
every tag that changed at all, is preserved as
`refs/backup/<UTC timestamp>/<original ref>`. The mirror's `refs/heads` and
`refs/tags` therefore always equal GitHub's current state, while the rewritten
history stays reachable (and is never garbage collected). Archive refs are
never overwritten. `status.json` counts them in `git_refs_archived`.
`--no-prune` is deprecated and has no effect.

This also holds when a run fails or is killed: before each fetch the current
refs are written to a journal (`backup-refs-journal` inside the mirror), and
whatever changed is archived after the fetch - successful or failed - or at
the start of the next run. A first clone is built in `repository.new-mirror/`
and only moved into place once it succeeded.

**A fresh copy is the fallback for any broken backup.** If the local backup
of a repository is unusable - it fails `git fsck`, a migration cannot be
finished, the directory is not a git repository, or a git operation fails and
the mirror is damaged - it is moved aside as `repository.broken-<timestamp>/`
(never deleted) and a fresh copy is cloned from GitHub in the same run. The
repository counts as backed up; `status.json` lists it under
`recovered_repositories` with the reason and where the old copy went, and the
log shows a warning. Inspect the old copy (its `refs/backup/*` archive is not
carried over) and delete it when no longer needed. Problems on the GitHub side
(network, authentication, outages) and ownership problems never trigger this:
they fail the repository and leave the backup alone.

**No credentials on disk.** The GitHub App installation token is passed to git
as an HTTP header through `GIT_CONFIG_*` environment variables of each git
process (requires git >= 2.31, checked at startup). It never appears in
`.git/config`, on the command line (`ps`) or in logs; the stored remote URL is
a plain `https://github.com/<owner>/<repo>.git`. Git LFS uses the same header
for its API; LFS storage on other hosts does not receive it.

**Ownership.** git refuses repositories owned by another user ("dubious
ownership"). Run the backup as the user that owns the backup directory (for
Docker: `--user <uid>` matching the volume).

**Restore** a repository into a new, empty GitHub repository:

```bash
git -C backup/<owner>/repositories/<repo>/repository push <new-remote-url> \
  'refs/heads/*:refs/heads/*' 'refs/tags/*:refs/tags/*'
```

Do not use `git push --mirror`: GitHub rejects pushes to `refs/pull/*`. To look
at the code, `git clone backup/<owner>/repositories/<repo>/repository` gives a
normal working copy. To recover archived history, list it with
`git for-each-ref refs/backup` and push the ones you need as branches.

**Upgrading from 0.3.0 and earlier.** Older versions stored a non-bare clone
(branches only as `refs/remotes/origin/*`, with the access token in the remote
URL) or, with `--bare`, a `git clone --mirror`. Both are converted in place on
the next run, also for repositories whose fetch is skipped. `--bare` is now a
no-op. The migration is designed to lose nothing:

- No git object is copied, rewritten or deleted; the old `.git` directory
  *becomes* the mirror. Only the checked-out working tree (whose content is in
  git) is removed, and only after verifying that every branch was carried over.
- Every remote-tracking branch becomes a real branch at the same commit.
- Every commit or annotated tag that no ref points to any more - tips
  force-pushed away that only the old reflogs remember, branches and re-cut
  tags an earlier run deleted but git had not yet garbage collected - is
  rescued as `refs/backup/<ts>-migration-unreferenced/<sha>`.
- A clone that fails `git fsck` is not converted; it is moved aside and
  replaced by a fresh copy (see "A fresh copy is the fallback" above). The
  `commit-graph` cache file is dropped before the check: older runs could
  leave it listing commits that git had already garbage collected, which
  makes `fsck` fail although no data is missing.
- An old `--bare` mirror gets the same rescue of unreferenced commits and
  tags once, when it is converted.
- Each step is idempotent: an interrupted run (Ctrl-C, container killed)
  resumes the migration on the next run (`repository.mirror-migration/` is
  the in-progress state).
- The token-bearing remote URL is replaced by a clean one.

Recommended procedure: take a filesystem snapshot of the backup directory
(e.g. Btrfs/ZFS snapshot on a NAS), run once, check `status.json` for
`repositories_failed` and `recovered_repositories`, then verify with
`grep -rl ghs_ <backup-dir> --include=config` (expect no output). Do not roll
back to 0.3.0 afterwards without its `--bare` flag: without it, 0.3.0 does not
recognise the mirrors and silently stops backing up git content.

**LFS** (`--lfs`): `git lfs fetch --all` runs after every fetch and covers all
refs including the archive; LFS objects are never pruned.

### Incremental backups

Incremental backups are automatic; there is no flag to enable them and no
separate state file. Every skip decision is derived from the backup data already
on disk, so the backup directory alone explains what was skipped and why.

**Repository git and wiki** — one `git ls-remote` lists every ref on GitHub
(branches, tags, notes, pull request heads). If all of them equal the refs in
the mirror, the (often dominant) `git fetch` is skipped. Unlike the
repository's `pushed_at`, this also notices pull request heads updated from a
fork, wiki edits, and branch deletions. Each repository's metadata is written
to `repo.json` after a fully successful pass, so metadata stays current even
when the git fetch is skipped.

**Issues, pull requests and milestones** — for each item, its stored
`<number>.json` already records `updated_at`. If that is at least as new as the
`updated_at` from the listing, the item is unchanged and its expensive
sub-resources (issue/PR comments, events, commits) are not re-fetched and the
file is not rewritten. An issue/PR `updated_at` reliably advances on comment,
label and state activity, so this does not miss updates. The item **listings**
are fetched in a single GraphQL query per repository (issues, pull requests,
milestones, labels and releases together), which replaces several sequential REST
list calls. Hooks still use REST (not available via GraphQL).

**HTTP performance** — all GitHub API traffic shares a `requests.Session` with
keep-alive, so repeated calls to the same host reuse the TLS connection instead
of paying a full handshake on every request.

**Releases** — release asset binaries are not re-downloaded when a file of the
same name already exists on disk. Release metadata and asset listings come from
the same GraphQL query as other repository metadata (no separate per-release
assets REST call when GraphQL data is available).

Notes:

- We deliberately never use the repository's own `updated_at` to skip
  issues/PRs, because it only reflects repository *metadata* changes, not
  issue/PR/comment activity — relying on it would risk silently missing data.
- Use `--force-full` to ignore all stored timestamps and re-fetch everything
  (git content and every issue/pull/milestone). Deleting an item's JSON has
  the same effect for that item.
- Interrupting a run with Ctrl-C stops cleanly; repositories finished so far
  are unchanged on the next run and are skipped quickly.
- `status.json` reports how much was skipped via
  `repositories_git_skipped_unchanged`, `issues_skipped_unchanged`,
  `pulls_skipped_unchanged` and `milestones_skipped_unchanged`.

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/schlomo/github-backup-app.git
cd github-backup-app

# Set up development environment
./dev-setup.sh

# Or manually
uv sync --dev
```

### Available Commands

First, activate the virtual environment (recommended for less typing):
```bash
source .venv/bin/activate
```

Then you can use the tools directly:
```bash
pytest -q tests/                      # Run tests (local git repos, no network)
flake8 github_backup/ tests/          # Run linting
black github_backup/ tests/           # Format code
python -c "import github_backup; print('Import successful')"  # Test import
github-backup --help                  # Show CLI help
uv build                              # Build package
```

### Releases

CI/CD is defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml). There are three jobs:

| Job | When it runs | What it does |
|-----|--------------|--------------|
| **test-build** | Every push and pull request | Lint (flake8), format check (black), tests (pytest), import/CLI smoke test, `uv build` → uploads `dist/` artifact |
| **docker** | Push to `main`, push of a `v*` tag, **or** a pull request | Builds multi-arch (`amd64` + `arm64`) image, pushes to `ghcr.io/schlomo/github-backup-app` and runs `--help` in it (pull requests from forks: build only) |
| **release** | Push of a `v*` tag only | Downloads the built wheel/sdist and publishes to PyPI |

**Docker image tags** ([docker/metadata-action](https://github.com/docker/metadata-action)):

- **`latest`** — every push to `main` (what the Quick Start uses)
- **`main`** — branch ref tag on `main` pushes
- **`X.Y.Z`**, **`X.Y`**, **`X`** — when you push an annotated semver tag like `v0.2.0`
- **`pr-<number>`** — every push to a pull request from this repository, to try a
  change before merging (e.g. `ghcr.io/schlomo/github-backup-app:pr-12`)

Merging to `main` updates `ghcr.io/schlomo/github-backup-app:latest`. No git tag is required for Docker.

**PyPI and version tags** — the PyPI job only runs when you push a **version tag** (`v0.2.0`, not `0.2.0`):

1. Bump version in [`github_backup/__init__.py`](github_backup/__init__.py)
2. Merge to `main` (updates `:latest` Docker image)
3. Tag and push:

```bash
git tag v0.2.0
git push origin v0.2.0
```

That triggers semver Docker tags and PyPI publish (requires a `PYPI_API_TOKEN` repository secret). There are no GitHub Releases in the repo yet; production Docker images come from `main` branch builds.

## Requirements

- Python 3.14+
- Git 2.41+ (not sure exactly)
- GitHub App with appropriate permissions

## License

MIT License - see [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

This project is based on the excellent work by [Jose Diaz-Gonzalez](https://github.com/josegonzalez) in [python-backup](https://github.com/josegonzalez/python-github-backup). Thank you for creating the foundation that made this derived work possible.

