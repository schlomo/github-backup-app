# Development Setup Guide

This guide will help you set up a development environment for the `github-backup-app` project using modern Python tooling.

## Prerequisites

- Python 3.12+ (tested with Python 3.13.3)
- Git
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)

## Quick Setup

### 1. Clone the Repository
```bash
git clone https://github.com/schlomo/github-backup-app.git
cd github-backup-app
```

### 2. Install uv (if not already installed)
```bash
# On macOS with Homebrew (recommended)
brew install uv

# Or using the official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Set up Development Environment

**Option A: Using the setup script (recommended):**
```bash
./dev-setup.sh
```

**Option B: Manual setup:**
```bash
# Install all dependencies (runtime + dev)
uv sync --dev

# Activate the virtual environment
source .venv/bin/activate

# Verify installation
python -c "import github_backup; print('Import successful')"
```

**Option C: Using uv directly:**
```bash
uv sync --dev
```

### 4. Verify Installation

First, activate the virtual environment:
```bash
source .venv/bin/activate
```

Then test the installation:
```bash
# Test the CLI
github-backup --help

# Test linting
flake8 github_backup/

# Test code formatting
black --check github_backup/

# Test import
python -c "import github_backup; print('Import successful')"
```

## Development Tools

### Code Quality Tools

- **flake8**: Linting and style checking
- **black**: Code formatting
- **autopep8**: Automatic PEP 8 formatting

### Testing

Currently, this project has no unit tests. To run linting:

```bash
# Activate the virtual environment first
source .venv/bin/activate

# Then run linting
flake8 github_backup/
```

### Code Formatting

To format code with black:
```bash
# Activate the virtual environment first
source .venv/bin/activate

# Then format code
black github_backup/
```

To check formatting without making changes:
```bash
black --check github_backup/
```

## Project Structure

```
github-backup-app/
├── github_backup/                   # Main package
│   ├── __init__.py                  # Package initialization
│   ├── github_backup.py             # Main application logic
│   └── create_github_app.py         # Script to automate creation of a GitHub App
├── bin/                             # Executable scripts
│   ├── github-backup                # Backup tool CLI entry point
│   └── github-backup-create-app     # GitHub App creation CLI entry poing
├── .github/
│   └── workflows/                   # GitHub Actions CI/CD
│       ├── ci.yml                   # Continuous Integration
│       ├── docker.yml               # Docker build and push
│       └── release.yml              # Release automation
├── pyproject.toml                   # Modern Python packaging configuration
├── uv.lock                          # Dependency lock file
├── dev-setup.sh                     # Development setup script
├── .flake8                          # Flake8 configuration
└── README.md                        # Project documentation
```

## Running the Application

### Basic Usage

First, activate the virtual environment:
```bash
source .venv/bin/activate
```

Then use the application:
```bash
# Show help
github-backup --help

# Backup a user's public repositories (requires GitHub App authentication)
github-backup username --app-id YOUR_APP_ID --private-key YOUR_PRIVATE_KEY --output-directory ./backup
```

### Development Testing
```bash
# Activate the virtual environment first
source .venv/bin/activate

# Run directly from source
python bin/github-backup --help

# Run the main module
python -m github_backup.github_backup --help

# Use the installed command
github-backup --help
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Set up development environment: `./dev-setup.sh`
4. Activate the virtual environment: `source .venv/bin/activate`
5. Make your changes
6. Run linting: `flake8 github_backup/`
7. Format code: `black github_backup/`
8. Test your changes: `python -c "import github_backup; print('Import successful')"`
9. Submit a pull request

The CI/CD pipeline will automatically run tests, linting, and formatting checks on your pull request.
