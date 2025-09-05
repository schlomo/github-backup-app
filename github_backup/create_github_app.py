#!/usr/bin/env python3
"""
Simple Flask-based GitHub App Creator.

This script creates a GitHub App using the manifest flow with a clean Flask web interface.
The only required parameter is the output directory for saving credentials.
"""

import argparse
import os
import sys
import time
import threading
import logging
from pathlib import Path
from typing import Dict, Any
import requests
import webbrowser
import getpass
from flask import Flask, request, render_template_string, jsonify

# Constants
DEFAULT_APP_DESCRIPTION = "A GitHub App for backing up repositories and metadata"


def generate_app_name(username: str) -> str:
    """Generate a unique GitHub App name under 34 characters that doesn't start with 'github'."""
    import re

    # Sanitize username to only a-z0-9, convert to lowercase
    clean_username = re.sub(r"[^a-z0-9]", "", username.lower())

    # Try different naming strategies in order of preference
    strategies = [
        # Strategy 1: GitHub backup with abbreviation (preferred)
        lambda u: f"gh-backup-{u}",
        # Strategy 2: Simple backup prefix
        lambda u: f"backup-{u}",
        # Strategy 3: Creative abbreviation
        lambda u: f"ghb-{u}",
    ]

    for strategy in strategies:
        name = strategy(clean_username)
        # Check constraints: under 34 chars and doesn't start with 'github'
        if len(name) <= 34 and not name.lower().startswith("github"):
            return name

    # Fallback: just use username if it's short enough
    if len(clean_username) <= 34:
        return clean_username

    # Last resort: truncate username
    return clean_username[:34]


current_username = getpass.getuser()
default_app_name = generate_app_name(current_username)


# Flask app
app = Flask(__name__)
app.temp_code = None
app.output_dir = None

# Suppress Flask and Werkzeug logging
logging.getLogger("werkzeug").setLevel(logging.ERROR)
logging.getLogger("flask").setLevel(logging.ERROR)
logging.getLogger("werkzeug.serving").setLevel(logging.ERROR)

# HTML template for the web interface
MAIN_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GH Backup App Creator</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f6f8fa;
        }
        .container {
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #24292e;
            text-align: center;
            margin-bottom: 30px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #24292e;
        }
        input, select, textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #d1d5da;
            border-radius: 6px;
            font-size: 14px;
        }
        input:focus, select:focus, textarea:focus {
            outline: none;
            border-color: #0366d6;
            box-shadow: 0 0 0 3px rgba(3, 102, 214, 0.1);
        }
        .help-text {
            font-size: 12px;
            color: #586069;
            margin-top: 5px;
        }
        .permissions {
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 15px;
            margin: 20px 0;
        }
        .permissions h3 {
            margin-top: 0;
            color: #24292e;
        }
        .permission-item {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #e1e4e8;
        }
        .permission-item:last-child {
            border-bottom: none;
        }
        .permission-name {
            font-weight: 500;
        }
        .permission-level {
            color: #0366d6;
            font-size: 12px;
        }
        .btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            width: 100%;
            margin-top: 20px;
        }
        .btn:hover {
            background: #218838;
        }
        .btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
        }
        .loading {
            text-align: center;
            padding: 20px;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #0366d6;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 GitHub Backup App Creator</h1>

        <div id="form-section">
            <form id="app-form">
                <div class="form-group">
                    <label for="app-name">App Name *</label>
                    <input type="text" id="app-name" name="name" required
                           value="{{ DEFAULT_APP_NAME }}" placeholder="My GitHub Backup App">
                    <div class="help-text">Choose a descriptive name for your GitHub App (prefilled with your username)</div>
                </div>

                <div class="form-group">
                    <label for="app-type">App Type *</label>
                    <select id="app-type" name="app_type" required>
                        <option value="personal">Personal App</option>
                        <option value="organization">Organization App</option>
                    </select>
                    <div class="help-text">Personal apps are owned by you, organization apps are owned by an organization.</div>
                </div>

                <div class="form-group" id="org-group" style="display: none;">
                    <label for="org-name">Organization Name *</label>
                    <input type="text" id="org-name" name="org_name"
                           placeholder="my-organization">
                    <div class="help-text">The GitHub organization name (e.g., "my-org" from github.com/my-org)</div>
                </div>

                <div class="form-group">
                    <label for="app-visibility">App Visibility *</label>
                    <select id="app-visibility" name="app_visibility" required>
                        <option value="private">Private App</option>
                        <option value="public">Public App</option>
                    </select>
                    <div class="help-text">
                        <strong>Private:</strong> Can only backup the single organization or account it belongs to.<br>
                        <strong>Public:</strong> Can backup multiple accounts/orgs, but others can also install it (be careful with org filtering).
                    </div>
                </div>

                <div class="form-group">
                    <label for="description">Description</label>
                    <textarea id="description" name="description" rows="3"
                              placeholder="Enter a description for your GitHub App">{{ DEFAULT_APP_DESCRIPTION }}</textarea>
                </div>

                <div class="permissions">
                    <h3>📋 Required Permissions</h3>
                    <p style="font-size: 12px; color: #586069; margin-bottom: 15px;">
                        This creates a GitHub App with read-only permissions for backup purposes.
                    </p>
                    <div class="permission-item">
                        <span class="permission-name">Contents</span>
                        <span class="permission-level">Read</span>
                    </div>
                    <div class="permission-item">
                        <span class="permission-name">Issues</span>
                        <span class="permission-level">Read</span>
                    </div>
                    <div class="permission-item">
                        <span class="permission-name">Metadata</span>
                        <span class="permission-level">Read</span>
                    </div>
                    <div class="permission-item">
                        <span class="permission-name">Pull requests</span>
                        <span class="permission-level">Read</span>
                    </div>
                    <div class="permission-item">
                        <span class="permission-name">Repository hooks</span>
                        <span class="permission-level">Read</span>
                    </div>
                    <div class="permission-item">
                        <span class="permission-name">Members</span>
                        <span class="permission-level">Read</span>
                    </div>
                </div>

                <button type="submit" class="btn">Create GitHub App</button>
            </form>
        </div>

        <div id="loading-section" style="display: none;">
            <div class="loading">
                <div class="spinner"></div>
                <p>Creating your GitHub App...</p>
            </div>
        </div>


    </div>

    <script>
        // Show/hide organization field based on app type
        document.getElementById('app-type').addEventListener('change', function() {
            const orgGroup = document.getElementById('org-group');
            const orgName = document.getElementById('org-name');
            if (this.value === 'organization') {
                orgGroup.style.display = 'block';
                orgName.required = true;
            } else {
                orgGroup.style.display = 'none';
                orgName.required = false;
            }
        });

        // Update help text based on app visibility
        document.getElementById('app-visibility').addEventListener('change', function() {
            const helpText = this.parentElement.querySelector('.help-text');
            if (this.value === 'public') {
                helpText.innerHTML = `
                    <strong>Public:</strong> Can backup multiple accounts/orgs, but others can also install it.<br>
                    <span style="color: #d73a49;">⚠️ Warning:</span> Be careful with organization filtering to avoid backing up unintended orgs.
                `;
            } else {
                helpText.innerHTML = `
                    <strong>Private:</strong> Can only backup the single organization or account it belongs to.<br>
                    <span style="color: #28a745;">✓ Safe:</span> No risk of others installing your app.
                `;
            }
        });

        // Handle form submission
        document.getElementById('app-form').addEventListener('submit', async function(e) {
            e.preventDefault();

            const formData = new FormData(this);
            const data = Object.fromEntries(formData);

            // Validate organization name if needed
            if (data.app_type === 'organization' && !data.org_name) {
                alert('Organization name is required for organization apps');
                return;
            }

            // Show loading
            document.getElementById('form-section').style.display = 'none';
            document.getElementById('loading-section').style.display = 'block';

            try {
                // Get manifest from server
                const response = await fetch('/create-app', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    const result = await response.json();

                    // Create a form to submit the manifest to GitHub
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = result.create_url;
                    form.target = '_blank';

                    // Add manifest as hidden input
                    const manifestInput = document.createElement('input');
                    manifestInput.type = 'hidden';
                    manifestInput.name = 'manifest';
                    manifestInput.value = JSON.stringify(result.manifest);
                    form.appendChild(manifestInput);

                    // Submit the form
                    document.body.appendChild(form);
                    form.submit();
                    document.body.removeChild(form);

                    // Show redirect message
                    document.getElementById('loading-section').innerHTML = `
                        <div class="loading">
                            <div class="spinner"></div>
                            <p>Redirecting to GitHub...</p>
                            <p>Complete the GitHub App creation process in the new tab.</p>
                        </div>
                    `;
                } else {
                    throw new Error('Failed to create app');
                }
            } catch (error) {
                document.getElementById('loading-section').style.display = 'none';
                document.getElementById('form-section').style.display = 'block';
                alert('Error creating app: ' + error.message);
            }
        });
    </script>
</body>
</html>
"""

SUCCESS_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitHub App Created Successfully</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f6f8fa;
        }
        .container {
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .success-header {
            text-align: center;
            margin-bottom: 30px;
        }
        .success-icon {
            font-size: 48px;
            margin-bottom: 15px;
        }
        .success-title {
            color: #28a745;
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 10px;
        }
        .success-subtitle {
            color: #586069;
            font-size: 16px;
        }
        .app-info {
            background: #f6f8fa;
            border: 1px solid #e1e4e8;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }
        .app-info h3 {
            margin-top: 0;
            color: #24292e;
            font-size: 18px;
        }
        .info-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e1e4e8;
        }
        .info-item:last-child {
            border-bottom: none;
        }
        .info-label {
            font-weight: 500;
            color: #24292e;
        }
        .info-value {
            color: #0366d6;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
        }
        .next-steps {
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 6px;
            padding: 20px;
            margin: 20px 0;
        }
        .next-steps h3 {
            margin-top: 0;
            color: #856404;
            font-size: 18px;
        }
        .next-steps p {
            color: #856404;
            margin-bottom: 15px;
            line-height: 1.5;
        }
        .btn {
            display: inline-block;
            background: #0366d6;
            color: white;
            text-decoration: none;
            padding: 12px 24px;
            border-radius: 6px;
            font-weight: 600;
            margin: 10px 5px;
            transition: background-color 0.2s;
        }
        .btn:hover {
            background: #0256cc;
            color: white;
            text-decoration: none;
        }
        .btn-secondary {
            background: #6c757d;
        }
        .btn-secondary:hover {
            background: #5a6268;
        }
        .credentials-note {
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 6px;
            padding: 15px;
            margin: 20px 0;
            color: #0c5460;
        }
        .credentials-note h4 {
            margin-top: 0;
            color: #0c5460;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-header">
            <div class="success-icon">🎉</div>
            <div class="success-title">GitHub App Created Successfully!</div>
            <div class="success-subtitle">Your backup app "{{ name or 'Your GitHub App' }}" is ready to use</div>
        </div>

        <div class="app-info">
            <h3>📱 App Information</h3>
            <div class="info-item">
                <span class="info-label">App ID:</span>
                <span class="info-value">{{ id or 'Unknown' }}</span>
            </div>
            <div class="info-item">
                <span class="info-label">App Name:</span>
                <span class="info-value">{{ name or 'Your GitHub App' }}</span>
            </div>
            <div class="info-item">
                <span class="info-label">App URL:</span>
                <span class="info-value">
                    <a href="{{ html_url or '#' }}" target="_blank" style="color: #0366d6;">View App Definition</a>
                </span>
            </div>
        </div>

        <div class="next-steps">
            <h3>🚀 Next Steps: Install Your App</h3>
            <p>
                <strong>Your GitHub App has been created, but it's not installed anywhere yet.</strong>
                To start backing up repositories, you need to install the app into the organizations
                or user accounts you want to backup.
            </p>
            <p>
                Click the button below to go to your app's definition page where you can install it
                into organizations and configure which repositories to backup.
            </p>
            <a href="{{ html_url or '#' }}" target="_blank" class="btn">Install App into Organizations</a>
        </div>

        <div class="credentials-note">
            <h4>🔐 Credentials Saved</h4>
            <p>
                Your app credentials (App ID, private key, and client secret) have been automatically
                saved to your local directory. You'll need these to run backup commands.
            </p>
        </div>

        <div style="text-align: center; margin-top: 30px;">
            <p style="color: #586069; font-size: 14px;">
                You can now close this window. Check the terminal for detailed installation instructions.
            </p>
        </div>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    """Serve the main HTML interface."""
    return render_template_string(
        MAIN_PAGE_TEMPLATE,
        DEFAULT_APP_DESCRIPTION=DEFAULT_APP_DESCRIPTION,
        DEFAULT_APP_NAME=default_app_name,
    )


@app.route("/create-app", methods=["POST"])
def create_app():
    """Handle app creation request."""
    try:
        data = request.get_json()

        # Create the manifest
        manifest = {
            "name": data["name"],
            "description": data.get("description", DEFAULT_APP_DESCRIPTION),
            "url": "https://github.com/schlomo/github-backup-app",
            "redirect_url": f"http://localhost:{app.port}/callback",
            "public": data.get("app_visibility") == "public",
            "default_events": [],
            "default_permissions": {
                "contents": "read",
                "issues": "read",
                "metadata": "read",
                "pull_requests": "read",
                "repository_hooks": "read",
                "members": "read",
            },
        }

        # Determine the creation URL based on app type
        if data["app_type"] == "organization":
            if not data.get("org_name"):
                return jsonify({"error": "Organization name is required"}), 400
            create_url = (
                f"https://github.com/organizations/{data['org_name']}/settings/apps/new"
            )
        else:
            create_url = "https://github.com/settings/apps/new"

        # Return the manifest and URL for the browser to submit
        return jsonify(
            {"success": True, "manifest": manifest, "create_url": create_url}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/callback")
def callback():
    """Handle GitHub callback with temporary code."""
    code = request.args.get("code")
    if code:
        app.temp_code = code
        print(f"✅ Received temporary code: {code}")

        # Exchange code for credentials
        try:
            app_data = exchange_code_for_credentials(code)
            files = save_credentials(app_data, app.output_dir)
            print_installation_instructions(app_data, files)

            # Start a background thread to exit after giving the browser time to load
            def delayed_exit():
                time.sleep(3)
                print("✅ GitHub App created successfully! Exiting...")
                os._exit(0)

            exit_thread = threading.Thread(target=delayed_exit)
            exit_thread.daemon = True
            exit_thread.start()

        except Exception as e:
            print(f"❌ Error processing credentials: {e}")
            return f"Error: {e}", 500

        # Return success page with app data
        return render_template_string(SUCCESS_PAGE_TEMPLATE, **app_data)
    else:
        return "Error: No code received", 400


def exchange_code_for_credentials(code: str) -> Dict[str, Any]:
    """Exchange the temporary code for permanent app credentials."""
    print("🔄 Exchanging temporary code for app credentials...")

    url = f"https://api.github.com/app-manifests/{code}/conversions"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "github-backup-app",
    }

    response = requests.post(url, headers=headers)
    response.raise_for_status()

    app_data = response.json()
    print("✅ Successfully exchanged code for app credentials!")
    return app_data


def save_credentials(app_data: Dict[str, Any], output_dir: str) -> Dict[str, str]:
    """Save the app credentials to files."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    app_slug = app_data["slug"]

    # Save App ID
    app_id_file = output_path / f"{app_slug}-app-id.txt"
    with open(app_id_file, "w") as f:
        f.write(str(app_data["id"]))
    os.chmod(app_id_file, 0o600)

    # Save Private Key
    private_key_file = output_path / f"{app_slug}-private-key.pem"
    with open(private_key_file, "w") as f:
        f.write(app_data["pem"])
    os.chmod(private_key_file, 0o600)

    # Save Client Secret
    client_secret_file = output_path / f"{app_slug}-client-secret.txt"
    with open(client_secret_file, "w") as f:
        f.write(app_data["client_secret"])
    os.chmod(client_secret_file, 0o600)

    return {
        "app_id": str(app_id_file),
        "private_key": str(private_key_file),
        "client_secret": str(client_secret_file),
    }


def print_installation_instructions(app_data: Dict[str, Any], files: Dict[str, str]):
    """Print installation instructions."""
    print("\n" + "=" * 60)
    print("🎉 GitHub App Created Successfully!")
    print("=" * 60)
    print(f"App ID: {app_data['id']}")
    print(f"App URL: {app_data['html_url']}")
    print(f"App Slug: {app_data['slug']}")
    print()
    print("📁 Credentials saved to:")
    print(f"  • App ID: {files['app_id']}")
    print(f"  • Private Key: {files['private_key']}")
    print(f"  • Client Secret: {files['client_secret']}")
    print()
    print("🚀 Next Steps:")
    print("1. Install the app on your repositories:")
    print(
        f"   github-backup --app-id {app_data['id']} --private-key {files['private_key']} --output-directory ./backup --all"
    )
    print()
    print("2. Or backup specific users/organizations:")
    print(
        f"   github-backup --app-id {
            app_data['id']} --private-key {
            files['private_key']} --output-directory ./backup --all USERNAME/ORGANIZATION"
    )
    print()
    print("3. For more options, see:")
    print("   github-backup --help")


def main():
    parser = argparse.ArgumentParser(
        description="GitHub App Creator for github-backup-app (prefills app name with your username)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create app and save credentials to current directory
  github-backup-create-app .

  # Create app and save credentials to specific directory
  github-backup-create-app ~/github-app-credentials

Note: The app name will be prefilled as "{default_app_name}" guessing your username
from your OS username. You can change this in the web interface if desired.
        """.format(
            default_app_name=default_app_name
        ),
    )

    parser.add_argument(
        "output_dir",
        help="Directory to save the app credentials (App ID, private key, client secret)",
    )
    parser.add_argument(
        "--port", type=int, default=3000, help="Port for the web server (default: 3000)"
    )

    args = parser.parse_args()

    # Validate output directory
    try:
        output_path = Path(args.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"❌ Error creating output directory: {e}")
        sys.exit(1)

    app.output_dir = args.output_dir
    app.port = args.port

    try:
        print("🚀 Starting GitHub App Creator...")
        print(f"📁 Credentials will be saved to: {args.output_dir}")
        print(f"🌐 Opening browser to: http://localhost:{args.port}")

        # Open browser
        webbrowser.open(f"http://localhost:{args.port}")

        print("\n📋 Instructions:")
        print("1. Fill out the app configuration in your browser")
        print("2. Click 'Create GitHub App' when ready")
        print("3. Complete the GitHub App creation process")
        print("4. You'll be redirected back automatically")
        print("\n⏳ Waiting for GitHub App creation...")

        # Start Flask app (suppress only Flask/Werkzeug logging)
        import werkzeug.serving

        werkzeug.serving.WSGIRequestHandler.log_request = lambda *args, **kwargs: None
        werkzeug.serving.WSGIRequestHandler.log_message = (
            lambda self, format, *args: None
        )

        # Use Werkzeug directly to avoid Flask startup messages
        from werkzeug.serving import make_server

        server = make_server("localhost", args.port, app, threaded=True)
        server.serve_forever()

    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
