# GitHub Backup App

A modern Python application for backing up GitHub repositories and metadata using GitHub App authentication. This tool is designed to create local backups of your GitHub data "just in case" - storing git repositories, JSON metadata files, and release data for safekeeping. The git repos are stored in a directory structure that mirrors the GitHub organization and repository structure, they can be accessed locally and pushed to a remote repository. Everythong else is stored as JSON responses for safekeeping and potentially re-used in the future.

The indended way of using this is to create a private GitHub App and installing that app into all the orgs and accounts you want to backup. The tool will then backup all the repositories from all the installations. This is also the main difference to [python-github-backup](https://github.com/josegonzalez/python-github-backup) on which this tool is based.

## What This Tool Does

This application creates comprehensive backups of GitHub repositories and their associated metadata:

- **Git Repositories**: Full git clones of your repositories
- **JSON Metadata**: Issues, pull requests, comments, milestones, labels, and more
- **Organized Storage**: Data is organized by account/repository structure
- **GitHub App Authentication**: Uses modern GitHub App authentication for secure, automated access

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
  --private-key ./creds/$(ls ./creds/*-private-key.pem | head -1 | xargs basename) \
  --all \
  --output-directory /data
```

## Installation

NOTE: Publication on PyPI is coming soon. Till then you have to install it manually.

### Manual Installation with uv from GitHub

If the package is not yet published on PyPI, you can install it directly from the GitHub repository using [uv](https://github.com/astral-sh/uv):

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
  --all
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
├── organization1/
│   └── repositories/
│       ├── repo1/
│       │   ├── repository/          # Git clone
│       │   ├── issues/              # JSON files
│       │   ├── pulls/               # JSON files
│       │   └── milestones/          # JSON files
│       └── repo2/
└── organization2/
    └── repositories/
```

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
black --check github_backup/          # Check formatting
python -c "import github_backup; print('Import successful')"  # Test import
github-backup --help                  # Show CLI help
uv build                              # Build package
```

## Requirements

- Python 3.12+
- Git 2.41+ (not sure exactly)
- GitHub App with appropriate permissions

## License

MIT License - see [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

This project is based on the excellent work by [Jose Diaz-Gonzalez](https://github.com/josegonzalez) in the original [python-github-backup](https://github.com/josegonzalez/python-github-backup) repository. Thank you for creating the foundation that made this derived work possible.

