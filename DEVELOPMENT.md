# Development Setup Guide

This guide will help you set up a development environment for the `python-github-backup` project.

## Prerequisites

- Python 3.8+ (tested with Python 3.13.3)
- Git
- Virtual environment tool (venv, virtualenv, or conda)

## Quick Setup

### 1. Clone the Repository
```bash
git clone https://github.com/josegonzalez/python-github-backup.git
cd python-github-backup
```

### 2. Create and Activate Virtual Environment

**Using venv (recommended):**
```bash
python3 -m venv venv
source venv/bin/activate  # On Unix/macOS
# or
venv\Scripts\activate     # On Windows
```

**Using fish shell:**
```bash
python3 -m venv venv
source venv/bin/activate.fish
```

### 3. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install runtime dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r release-requirements.txt

# Install the package in development mode
pip install -e .
```

### 4. Verify Installation

```bash
# Test the CLI
github-backup -h

# Test linting
flake8 --ignore=E501 github_backup/

# Test code formatting
black --check github_backup/
```

## Development Tools

### Code Quality Tools

- **flake8**: Linting and style checking
- **black**: Code formatting
- **autopep8**: Automatic PEP 8 formatting

### Testing

Currently, this project has no unit tests. To run linting:

```bash
flake8 --ignore=E501 github_backup/
```

### Code Formatting

To format code with black:
```bash
black github_backup/
```

To check formatting without making changes:
```bash
black --check github_backup/
```

## Project Structure

```
python-github-backup/
├── github_backup/           # Main package
│   ├── __init__.py         # Package initialization
│   └── github_backup.py    # Main application logic
├── bin/                    # Executable scripts
│   └── github-backup       # CLI entry point
├── requirements.txt        # Runtime dependencies
├── release-requirements.txt # Development dependencies
├── setup.py               # Package configuration
└── README.rst             # Project documentation
```

## Key Dependencies

### Runtime Dependencies
- `PyJWT>=2.0.0`: For GitHub App authentication
- `cryptography>=3.0.0`: For cryptographic operations

### Development Dependencies
- `flake8`: Code linting
- `black`: Code formatting
- `autopep8`: PEP 8 formatting
- `twine`: Package distribution
- `gitchangelog`: Changelog generation

## Running the Application

### Basic Usage
```bash
# Show help
github-backup -h

# Backup a user's public repositories
github-backup username --output-directory ./backup

# Backup with authentication
github-backup username --token YOUR_TOKEN --private --output-directory ./backup
```

### Development Testing
```bash
# Run directly from source
python bin/github-backup -h

# Run the main module
python -m github_backup.github_backup -h
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run linting: `flake8 --ignore=E501 github_backup/`
5. Format code: `black github_backup/`
6. Test your changes
7. Submit a pull request

## Environment Variables

For development, you might want to set these environment variables:

```bash
export GITHUB_TOKEN=your_github_token
export GITHUB_USERNAME=your_github_username
```

## Troubleshooting

### Virtual Environment Issues
- Make sure you're using the correct Python version (3.8+)
- If you get permission errors, try: `python3 -m venv venv --user`

### Import Errors
- Ensure the package is installed in development mode: `pip install -e .`
- Check that your virtual environment is activated

### Linting Issues
- The project uses specific flake8 ignore patterns
- Some style issues are expected in the existing codebase
- Use `black` to automatically format code

### GitHub App Authentication Issues

If you encounter "Could not parse the provided public key" errors when using GitHub App authentication:

1. **Check your private key file**: Ensure it's a complete PEM file with all lines
2. **Use the test script**: Run `./test_github_app_auth.py` to verify your setup
3. **Verify file permissions**: Make sure the private key file is readable
4. **Check file format**: The private key should be in PEM format (RSA or PKCS#8)

**Test your GitHub App authentication:**
```bash
# Set your environment variables
export GITHUB_APP_ID=your_app_id
export GITHUB_INSTALLATION_ID=your_installation_id
export GITHUB_PRIVATE_KEY=/path/to/your-app.pem

# Run the test script
./test_github_app_auth.py
```

**Common issues:**
- Private key file truncated or corrupted
- Incorrect App ID or Installation ID
- Missing GitHub App permissions
- File path issues (use absolute paths)

**Note**: This project includes several optimizations for GitHub App authentication:

1. **Private Key Parsing Fix**: Resolved the "Could not parse the provided public key" error by:
   - Reading private key files completely (not just the first line)
   - Supporting both `file://` prefixed paths and direct file paths
   - Adding proper error handling for file reading operations

2. **Simplified Token Management**: Implemented a robust and simple approach:
   - Always call `get_auth()` before each API request
   - Let the caching logic in `get_or_refresh_github_app_token()` handle optimization
   - No complex error handling or retry logic needed
   - 5-minute buffer before token expiry for seamless refresh
   - Automatic token regeneration when needed
   - Proper timezone handling for token expiration comparison

3. **API Request Simplification**: Streamlined authentication flow:
   - Each API call gets fresh authentication (caching handles efficiency)
   - Eliminated complex error handling for token expiration
   - More reliable and easier to maintain
   - Works seamlessly with any token lifetime

4. **Bug Fixes**:
   - Fixed parameter order bug in `_construct_request()` that caused pagination to start at page 100
   - Fixed `b"..."` string issue in `logging_subprocess()` by properly decoding bytes to strings
   - Fixed timezone handling in token expiration comparison

## Next Steps

1. Read the main README.rst for usage examples
2. Explore the `github_backup.py` file to understand the codebase
3. Set up your GitHub authentication for testing
4. Start contributing!

## Support

- Check the [README.rst](README.rst) for detailed usage information
- Review the [CHANGES.rst](CHANGES.rst) for recent updates
- Open an issue on GitHub for bugs or feature requests
