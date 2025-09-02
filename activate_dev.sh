#!/bin/bash

# Development Environment Activation Script
# This script activates the virtual environment and sets up the development environment

echo "🐍 Activating python-github-backup development environment..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Please run the setup first:"
    echo "   python3 -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    echo "   pip install -r release-requirements.txt"
    echo "   pip install -e ."
    exit 1
fi

# Activate virtual environment
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Check if package is installed
if ! python -c "import github_backup" 2>/dev/null; then
    echo "❌ Package not installed in development mode. Installing..."
    pip install -e .
fi

echo "✅ Development environment ready!"
echo ""
echo "Available commands:"
echo "  github-backup -h                    # Show help"
echo "  flake8 --ignore=E501 github_backup/ # Run linting"
echo "  black --check github_backup/        # Check code formatting"
echo "  black github_backup/                # Format code"
echo ""
echo "To deactivate: deactivate"
