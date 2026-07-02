# GitHub Backup App

A modern Python application for backing up GitHub repositories and metadata using **GitHub App authentication**. It creates local backups of your git repositories, JSON metadata, and release assets — organized by account, ready to push elsewhere or restore from.

The intended workflow: create one private GitHub App, install it on every org and user account you want to back up, then run nightly. The tool discovers all installations automatically and backs up every accessible repository.

This project is a fork of [python-backup](https://github.com/josegonzalez/python-github-backup) with a different focus: **multi-installation GitHub App backups**, **automatic incremental runs**, and **much faster repeat backups** on large estates.

## What This Tool Does

- **Git repositories** — full clones, with automatic skip when `pushed_at` is unchanged
- **JSON metadata** — issues, pull requests, comments, milestones, labels, hooks, releases
- **Organized storage** — `{output}/{owner}/repositories/{repo}/…` mirrors GitHub's structure
- **GitHub App auth** — one app, many installations; no personal access tokens or SSH keys to rotate

## Key features

| Feature | Description |
|---------|-------------|
| **Multi-installation discovery** | One run backs up every org/user where the app is installed; filter with positional args (`jschule myorg`) |
| **Automatic incremental** | No `-i` flag and no separate state files — skip decisions come from the backup data on disk (`repo.json`, per-item JSON) |
| **Git skip** | Unchanged repos skip `git fetch` when stored `pushed_at` matches the API |
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
| **Git fetch on repeat runs** | Always runs `git fetch` when a clone exists | Skips fetch when `repo.json` `pushed_at` is unchanged |
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

On a quiet estate where most repos haven't changed, the dominant cost shifts from git fetches and metadata listing to wiki probes and hooks (still REST-only).

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
│       │   ├── repository/          # Git clone
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
  "version": "0.2.0",
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

### Incremental backups

Incremental backups are automatic; there is no flag to enable them and no
separate state file. Every skip decision is derived from the backup data already
on disk, so the backup directory alone explains what was skipped and why.

**Repository git** — each repository's metadata is written to `repo.json` in its
backup folder. This is useful backup data in its own right (description, topics,
visibility, default branch, archived state, ...) and its `pushed_at` field
doubles as the incremental signal. On the next run, if a repository's current
`pushed_at` (from the GitHub API) matches the value stored in `repo.json` **and**
a local clone already exists, the (often dominant) `git fetch` is skipped.
`pushed_at` changes on every push (including tags and force-pushes), so this is
always safe. `repo.json` is refreshed on every successful run, so metadata stays
current even when the git fetch is skipped.

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

**Wiki** — always fetched (a no-op when unchanged), because wiki edits are not
reflected in the repository's `pushed_at`.

**Releases** — release asset binaries are not re-downloaded when a file of the
same name already exists on disk. Release metadata and asset listings come from
the same GraphQL query as other repository metadata (no separate per-release
assets REST call when GraphQL data is available).

Notes:

- We deliberately never use the repository's own `updated_at` to skip
  issues/PRs, because it only reflects repository *metadata* changes, not
  issue/PR/comment activity — relying on it would risk silently missing data.
- Use `--force-full` to ignore all stored timestamps and re-fetch everything
  (git content and every issue/pull/milestone). Deleting a repo's `repo.json`
  (or an item's JSON) has the same effect for that item.
- Interrupting a run with Ctrl-C stops cleanly; each repository finished so far
  has its `repo.json` saved, so the next run skips them and resumes quickly.
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
flake8 github_backup/                 # Run linting
black github_backup/                  # Format code
python -c "import github_backup; print('Import successful')"  # Test import
github-backup --help                  # Show CLI help
uv build                              # Build package
```

### Releases

CI/CD is defined in [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml). There are three jobs:

| Job | When it runs | What it does |
|-----|--------------|--------------|
| **test-build** | Every push and pull request | Lint (flake8), format check (black), import/CLI smoke test, `uv build` → uploads `dist/` artifact |
| **docker** | Push to `main` **or** push of a `v*` tag | Builds multi-arch (`amd64` + `arm64`) image and pushes to `ghcr.io/schlomo/github-backup-app` |
| **release** | Push of a `v*` tag only | Downloads the built wheel/sdist and publishes to PyPI |

**Docker image tags** ([docker/metadata-action](https://github.com/docker/metadata-action)):

- **`latest`** — every push to `main` (what the Quick Start uses)
- **`main`** — branch ref tag on `main` pushes
- **`X.Y.Z`**, **`X.Y`**, **`X`** — when you push an annotated semver tag like `v0.2.0`

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

