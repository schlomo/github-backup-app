#!/bin/bash

# Modern Development Setup Script for github-backup
# Uses uv for fast dependency management

set -e

echo "🚀 Setting up github-backup development environment with uv..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   brew install uv"
    echo "   or visit: https://github.com/astral-sh/uv"
    exit 1
fi

echo "✅ uv is available"

# Install dependencies
echo "📦 Installing dependencies..."
uv sync --dev

# Verify installation
echo "🔍 Verifying installation..."
uv run python -c "import github_backup; print('✅ Package import successful')"

echo ""
echo "🎉 Development environment ready!"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source .venv/bin/activate"
echo ""
echo "2. Then you can use these commands directly:"
echo "   flake8 github_backup/                # Run linting"
echo "   black github_backup/                 # Format code"
echo "   black --check github_backup/         # Check formatting"
echo "   python -c \"import github_backup; print('Import successful')\"  # Test import"
echo "   github-backup --help                 # Show CLI help"
echo "   uv build                             # Build package"
echo ""
echo "To deactivate the virtual environment: deactivate"
