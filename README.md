# GitHub Backup App

A modern Python application for backing up GitHub repositories and metadata using GitHub App authentication. This tool is designed to create local backups of your GitHub data "just in case" - storing git repositories, JSON metadata files, and release data for safekeeping. The git repos are stored in a directory structure that mirrors the GitHub organization and repository structure, they can be accessed locally and pushed to a remote repository. Everythong else is stored as JSON responses for safekeeping and potentially re-used in the future.

The indended way of using this is to create a private GitHub App and installing that app into all the orgs and accounts you want to backup. The tool will then backup all the repositories from all the installations. This is also the main difference to [python-github-backup](https://github.com/josegonzalez/python-github-backup) on which this tool is based.

## What This Tool Does

This application creates comprehensive backups of GitHub repositories and their associated metadata:

- **Git Repositories**: Full git clones of your repositories
- **JSON Metadata**: Issues, pull requests, comments, milestones, labels, and more
- **Organized Storage**: Data is organized by account/repository structure
- **GitHub App Authentication**: Uses modern GitHub App authentication for secure, automated access

## Installation

NOTE: Publication on PyPI is coming soon. Till then you have to install it manually.

### Using uv (Recommended)

```bash
# Install uv if you haven't already
brew install uv  # On macOS
# or: curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the application (once published on PyPI)
uv tool install github-backup-app
```

### Using pip

```bash
pip install github-backup-app
```

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

## Quick Start

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

### 2. Run a Backup

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

### 3. Dry Run (See What Would Be Backed Up)

```bash
github-backup \
  --app-id YOUR_APP_ID \
  --private-key /path/to/your-app.pem \
  --dry-run
```

## GitHub App Setup

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

First, activate the virtual environment:
```bash
source .venv/bin/activate
```

Then you can use the tools directly:
```bash
flake8 github_backup/                 # Run linting
black github_backup/                  # Format code
black --check github_backup/          # Check formatting
python -c "import github_backup; print('Import successful')"  # Test import
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

