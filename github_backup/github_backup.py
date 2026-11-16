#!/usr/bin/env python


import argparse
import base64
import calendar
import codecs
import errno
import getpass
import json
import logging
import os
import platform
import re
import select
import shutil
import socket
import ssl
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
from urllib.parse import quote as urlquote
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

# GitHub App authentication imports
try:
    import jwt
except ImportError:
    raise ImportError(
        "PyJWT library is required for GitHub App authentication. "
        "Install it with: pip install PyJWT>=2.0.0 cryptography>=3.0.0"
    )

try:
    import requests
except ImportError:
    raise ImportError(
        "requests library is required. Install it with: pip install requests>=2.34.0"
    )

try:
    from . import __version__

    VERSION = __version__
except ImportError:
    VERSION = "unknown"

FILE_URI_PREFIX = "file://"
STATUS_FILENAME = "status.json"
REPO_METADATA_FILENAME = "repo.json"
# Installation tokens live 60 minutes; refresh once less than this is left.
TOKEN_MIN_REMAINING = timedelta(minutes=30)
PROJECT_URL = "https://github.com/schlomo/github-backup-app"
logger = logging.getLogger(__name__)

_github_http_session = None


class _HttpResponse:
    """Adapter so requests responses match the urllib interface used elsewhere."""

    def __init__(self, response):
        self._response = response
        self._body = None

    def getcode(self):
        return self._response.status_code

    @property
    def headers(self):
        return self._response.headers

    def read(self):
        if self._body is None:
            self._body = self._response.content
        return self._body


class _HttpErrorResponse:
    """Adapter so requests error responses work with ``_request_http_error``."""

    def __init__(self, response):
        self._response = response
        self.code = response.status_code
        self.reason = response.reason
        self.headers = response.headers

    def read(self):
        return self._response.content


def get_github_http_session():
    """Return a shared ``requests.Session`` for GitHub API calls (keep-alive)."""
    global _github_http_session
    if _github_http_session is None:
        _github_http_session = requests.Session()
    return _github_http_session


def close_github_http_session():
    """Close the shared HTTP session (called at process exit)."""
    global _github_http_session
    if _github_http_session is not None:
        _github_http_session.close()
        _github_http_session = None


def format_exception(exc):
    """Return a detailed, log-friendly description of an exception.

    Plain ``str(exc)`` often hides the exception type and, for HTTP failures,
    the response body that GitHub fills with a precise error message. Surfacing
    both makes failures understandable from the logs alone.
    """
    description = f"{type(exc).__name__}: {exc}"

    # urllib's HTTPError behaves like a response object and carries the body
    # GitHub returns (usually JSON with a "message" field explaining the error).
    if isinstance(exc, HTTPError):
        details = [f"HTTP {exc.code} {exc.reason}"]
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        if body:
            details.append(f"response body: {body}")
        description = f"{description} ({'; '.join(details)})"

    # Preserve the chained/original cause when one exists.
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        description = f"{description} [caused by {type(cause).__name__}: {cause}]"

    return description


def _package_version(name):
    """Best-effort lookup of an installed package version."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(name)
        except PackageNotFoundError:
            return "not-installed"
    except Exception:
        return "unknown"


def log_runtime_environment():
    """Log Python and key dependency versions.

    Dependency drift between environments (e.g. the pinned local install vs. a
    freshly built container) is a common and hard-to-spot cause of failures, so
    we record it up front to make such problems obvious from the logs.
    """
    jwt_version = getattr(jwt, "__version__", None) or _package_version("PyJWT")
    logger.debug(
        "Runtime: github-backup %s | Python %s | %s | "
        "PyJWT %s | cryptography %s | requests %s | flask %s",
        VERSION,
        platform.python_version(),
        platform.platform(),
        jwt_version,
        _package_version("cryptography"),
        _package_version("requests"),
        _package_version("flask"),
    )


def _read_previous_last_success(path):
    """Return the ``last_success_at`` value from an existing status file.

    Falls back to the previous run's ``finished_at`` if it was itself a success
    (for status files written before this field existed). Returns ``None`` when
    no prior success can be determined.
    """
    try:
        with codecs.open(path, "r", encoding="utf-8") as f:
            previous = json.load(f)
    except OSError, ValueError:
        return None
    if previous.get("last_success_at"):
        return previous["last_success_at"]
    if previous.get("status") == "success":
        return previous.get("finished_at") or previous.get("timestamp")
    return None


def write_status_file(output_directory, status, started_at, stats=None, error=None):
    """Write a machine-readable status file to the root of the backup directory.

    The file is intended for monitoring: it always contains at least ``status``
    and ``finished_at`` fields, plus summary statistics about the run. It is
    written atomically so monitoring never observes a half-written file.

    Returns the path written, or ``None`` if it could not be written.
    """
    finished_at = datetime.now(timezone.utc)
    path = os.path.join(output_directory, STATUS_FILENAME)

    # Carry forward the timestamp of the last fully successful run. This lets a
    # monitor alert on "the last good backup is too old" even when more recent
    # runs keep failing - the exact situation that previously went unnoticed
    # for months.
    if status == "success":
        last_success_at = finished_at.isoformat()
    else:
        last_success_at = _read_previous_last_success(path)

    status_data = {
        "status": status,
        "started_at": started_at.isoformat() if started_at else None,
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (
            round((finished_at - started_at).total_seconds(), 3) if started_at else None
        ),
        "last_success_at": last_success_at,
        "tool": "github-backup-app",
        "url": PROJECT_URL,
        "version": VERSION,
        "python_version": platform.python_version(),
    }
    if stats:
        status_data["summary"] = stats
    if error is not None:
        status_data["error"] = error

    tmp_path = path + ".tmp"
    try:
        with codecs.open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(status_data, f, ensure_ascii=False, sort_keys=True, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
        logger.info(f"Wrote backup status file: {path} (status={status})")
        return path
    except Exception as e:
        logger.error(f"Failed to write status file {path}: {format_exception(e)}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return None


def read_json_field(path, field, default=None):
    """Return a single top-level field from a JSON file on disk.

    Returns ``default`` if the file is missing, unreadable, not a JSON object,
    or lacks the field. Used to drive incremental skips directly from the backup
    data (e.g. a repository's last-seen ``pushed_at`` stored in ``repo.json``)
    rather than from a separate state file.
    """
    try:
        with codecs.open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except OSError, ValueError:
        return default
    if isinstance(data, dict):
        return data.get(field, default)
    return default


def is_item_unchanged(item_file, api_updated_at, force_full=False):
    """Return True if the on-disk JSON for an item already covers its latest
    update, so its (expensive) sub-resources do not need to be re-fetched.

    Compares the ``updated_at`` stored in ``item_file`` against the value from
    the listing response. GitHub emits ISO-8601 UTC (``...Z``) timestamps, which
    are lexicographically ordered, so a stored value greater than or equal to
    the listed value means nothing changed since the last backup.

    Returns False (i.e. "fetch it") when forcing a full backup, when the listing
    has no ``updated_at``, or when the item has no readable stored copy.
    """
    if force_full or not api_updated_at:
        return False
    stored = read_json_field(item_file, "updated_at")
    return stored is not None and stored >= api_updated_at


def get_github_graphql_url(args):
    if args.github_host:
        return f"https://{args.github_host}/api/graphql"
    return "https://api.github.com/graphql"


def _graphql_timestamp(value):
    if not value:
        return None
    return value.replace("+00:00", "Z")


def _graphql_user(node):
    author = node.get("author") or {}
    login = author.get("login")
    if not login:
        return None
    return {"login": login}


def _graphql_issue_to_rest(node):
    labels = [
        {"name": label["name"], "color": label.get("color")}
        for label in (node.get("labels") or {}).get("nodes", [])
    ]
    milestone = node.get("milestone")
    milestone_data = None
    if milestone:
        milestone_data = {
            "number": milestone.get("number"),
            "title": milestone.get("title"),
        }
    return {
        "number": node["number"],
        "title": node.get("title"),
        "body": node.get("body"),
        "state": (node.get("state") or "").lower(),
        "created_at": _graphql_timestamp(node.get("createdAt")),
        "updated_at": _graphql_timestamp(node.get("updatedAt")),
        "closed_at": _graphql_timestamp(node.get("closedAt")),
        "url": node.get("url"),
        "user": _graphql_user(node),
        "labels": labels,
        "milestone": milestone_data,
        "comments": (node.get("comments") or {}).get("totalCount", 0),
    }


def _graphql_pull_to_rest(node, include_details=False):
    data = {
        "number": node["number"],
        "title": node.get("title"),
        "body": node.get("body"),
        "state": (node.get("state") or "").lower(),
        "created_at": _graphql_timestamp(node.get("createdAt")),
        "updated_at": _graphql_timestamp(node.get("updatedAt")),
        "closed_at": _graphql_timestamp(node.get("closedAt")),
        "merged_at": _graphql_timestamp(node.get("mergedAt")),
        "url": node.get("url"),
        "user": _graphql_user(node),
    }
    if include_details:
        data.update(
            {
                "additions": node.get("additions"),
                "deletions": node.get("deletions"),
                "changed_files": node.get("changedFiles"),
                "merged": node.get("merged"),
                "mergeable": node.get("mergeable"),
                "rebaseable": node.get("rebaseable"),
                "merge_commit_sha": (node.get("mergeCommit") or {}).get("oid"),
                "commits": (node.get("commits") or {}).get("totalCount", 0),
            }
        )
    return data


def _graphql_milestone_to_rest(node):
    return {
        "number": node["number"],
        "title": node.get("title"),
        "description": node.get("description"),
        "state": (node.get("state") or "").lower(),
        "created_at": _graphql_timestamp(node.get("createdAt")),
        "updated_at": _graphql_timestamp(node.get("updatedAt")),
        "closed_at": _graphql_timestamp(node.get("closedAt")),
        "due_on": node.get("dueOn"),
        "open_issues": node.get("openIssueCount", 0),
        "closed_issues": node.get("closedIssueCount", 0),
    }


def _graphql_label_to_rest(node):
    return {
        "name": node.get("name"),
        "color": node.get("color"),
        "description": node.get("description"),
    }


def _graphql_release_to_rest(node):
    assets = []
    for asset in (node.get("releaseAssets") or {}).get("nodes", []):
        assets.append(
            {
                "name": asset.get("name"),
                "size": asset.get("size"),
                "updated_at": _graphql_timestamp(asset.get("updatedAt")),
                "url": asset.get("url"),
            }
        )
    return {
        "tag_name": node.get("tagName"),
        "name": node.get("name"),
        "body": node.get("description"),
        "created_at": _graphql_timestamp(node.get("createdAt")),
        "published_at": _graphql_timestamp(node.get("publishedAt")),
        "updated_at": _graphql_timestamp(
            node.get("updatedAt") or node.get("publishedAt")
        ),
        "prerelease": node.get("isPrerelease", False),
        "draft": node.get("isDraft", False),
        "assets": assets,
        "assets_url": node.get("url"),
    }


def _build_repo_metadata_graphql_query(fetch):
    parts = []
    if fetch.get("issues"):
        parts.append("""
            issues(
              first: $issuesFirst
              after: $issuesAfter
              states: [OPEN, CLOSED]
              orderBy: {field: UPDATED_AT, direction: DESC}
            ) {
              pageInfo { hasNextPage endCursor }
              nodes {
                number title body state createdAt updatedAt closedAt url
                author { login }
                comments { totalCount }
                labels(first: 100) { nodes { name color } }
                milestone { number title }
              }
            }
            """)
    if fetch.get("pulls"):
        detail_fields = ""
        if fetch.get("pull_details"):
            detail_fields = """
                additions deletions changedFiles merged mergeable rebaseable
                mergeCommit { oid }
                commits { totalCount }
            """
        parts.append(f"""
            pullRequests(
              first: $pullsFirst
              after: $pullsAfter
              states: [OPEN, CLOSED, MERGED]
              orderBy: {{field: UPDATED_AT, direction: DESC}}
            ) {{
              pageInfo {{ hasNextPage endCursor }}
              nodes {{
                number title body state createdAt updatedAt closedAt mergedAt url
                author {{ login }}
                {detail_fields}
              }}
            }}
            """)
    if fetch.get("milestones"):
        parts.append("""
            milestones(
              first: $milestonesFirst
              after: $milestonesAfter
              states: [OPEN, CLOSED]
              orderBy: {field: DUE_DATE, direction: ASC}
            ) {
              pageInfo { hasNextPage endCursor }
              nodes {
                number title description state createdAt updatedAt closedAt dueOn
                openIssueCount closedIssueCount
              }
            }
            """)
    if fetch.get("labels"):
        parts.append("""
            labels(first: $labelsFirst, after: $labelsAfter, orderBy: {field: NAME, direction: ASC}) {
              pageInfo { hasNextPage endCursor }
              nodes { name color description }
            }
            """)
    if fetch.get("releases"):
        parts.append("""
            releases(first: $releasesFirst, after: $releasesAfter, orderBy: {field: CREATED_AT, direction: DESC}) {
              pageInfo { hasNextPage endCursor }
              nodes {
                tagName name description createdAt publishedAt updatedAt
                isDraft isPrerelease url
                releaseAssets(first: 100) {
                  nodes { name size updatedAt url }
                }
              }
            }
            """)

    variable_defs = ["$owner: String!", "$name: String!"]
    if fetch.get("issues"):
        variable_defs.extend(["$issuesFirst: Int!", "$issuesAfter: String"])
    if fetch.get("pulls"):
        variable_defs.extend(["$pullsFirst: Int!", "$pullsAfter: String"])
    if fetch.get("milestones"):
        variable_defs.extend(["$milestonesFirst: Int!", "$milestonesAfter: String"])
    if fetch.get("labels"):
        variable_defs.extend(["$labelsFirst: Int!", "$labelsAfter: String"])
    if fetch.get("releases"):
        variable_defs.extend(["$releasesFirst: Int!", "$releasesAfter: String"])

    return (
        f"query RepoMetadata({', '.join(variable_defs)}) {{\n"
        f"  repository(owner: $owner, name: $name) {{\n"
        f"    {' '.join(parts)}\n"
        f"  }}\n"
        f"}}"
    )


def execute_graphql(args, query, variables, installation_id):
    """Run a GraphQL query against the GitHub API using the shared session."""
    auth = get_auth(args, installation_id, encode=False)
    headers = {
        "Authorization": f"Bearer {auth}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"github-backup/{VERSION}",
    }
    url = get_github_graphql_url(args)
    logger.debug(f"GraphQL request to {url}")
    session = get_github_http_session()
    response = session.post(
        url, headers=headers, json={"query": query, "variables": variables}, timeout=120
    )
    if response.status_code >= 400:
        raise Exception(f"GraphQL HTTP {response.status_code}: {response.text.strip()}")
    payload = response.json()
    if payload.get("errors"):
        messages = "; ".join(
            error.get("message", str(error)) for error in payload["errors"]
        )
        raise Exception(f"GraphQL error: {messages}")
    return payload


def fetch_repository_metadata_graphql(args, repository, fetch):
    """Fetch repository metadata in as few GraphQL round trips as possible.

    ``fetch`` is a dict of booleans: issues, pulls, pull_details, milestones,
    labels, releases. Returns REST-shaped lists for each requested resource.
    Hooks are not available via GraphQL and must still be fetched over REST.
    """
    if not any(fetch.values()):
        return {}

    owner = repository["owner"]["login"]
    name = repository["name"]
    installation_id = repository.get("_installation_id")
    query = _build_repo_metadata_graphql_query(fetch)

    results = {
        "issues": [],
        "pulls": [],
        "milestones": [],
        "labels": [],
        "releases": [],
    }
    cursors = {
        "issues": None,
        "pulls": None,
        "milestones": None,
        "labels": None,
        "releases": None,
    }
    done = {key: not fetch.get(key) for key in cursors}

    while not all(done.values()):
        variables = {"owner": owner, "name": name}
        if fetch.get("issues"):
            variables["issuesFirst"] = 100
            variables["issuesAfter"] = cursors["issues"]
        if fetch.get("pulls"):
            variables["pullsFirst"] = 100
            variables["pullsAfter"] = cursors["pulls"]
        if fetch.get("milestones"):
            variables["milestonesFirst"] = 100
            variables["milestonesAfter"] = cursors["milestones"]
        if fetch.get("labels"):
            variables["labelsFirst"] = 100
            variables["labelsAfter"] = cursors["labels"]
        if fetch.get("releases"):
            variables["releasesFirst"] = 100
            variables["releasesAfter"] = cursors["releases"]

        payload = execute_graphql(args, query, variables, installation_id)
        repo_data = (payload.get("data") or {}).get("repository")
        if repo_data is None:
            raise Exception(f"GraphQL could not access repository {owner}/{name}")

        if fetch.get("issues"):
            connection = repo_data["issues"]
            results["issues"].extend(
                _graphql_issue_to_rest(node) for node in connection.get("nodes", [])
            )
            if connection["pageInfo"]["hasNextPage"]:
                cursors["issues"] = connection["pageInfo"]["endCursor"]
            else:
                done["issues"] = True

        if fetch.get("pulls"):
            connection = repo_data["pullRequests"]
            results["pulls"].extend(
                _graphql_pull_to_rest(node, fetch.get("pull_details"))
                for node in connection.get("nodes", [])
            )
            if connection["pageInfo"]["hasNextPage"]:
                cursors["pulls"] = connection["pageInfo"]["endCursor"]
            else:
                done["pulls"] = True

        if fetch.get("milestones"):
            connection = repo_data["milestones"]
            results["milestones"].extend(
                _graphql_milestone_to_rest(node) for node in connection.get("nodes", [])
            )
            if connection["pageInfo"]["hasNextPage"]:
                cursors["milestones"] = connection["pageInfo"]["endCursor"]
            else:
                done["milestones"] = True

        if fetch.get("labels"):
            connection = repo_data["labels"]
            results["labels"].extend(
                _graphql_label_to_rest(node) for node in connection.get("nodes", [])
            )
            if connection["pageInfo"]["hasNextPage"]:
                cursors["labels"] = connection["pageInfo"]["endCursor"]
            else:
                done["labels"] = True

        if fetch.get("releases"):
            connection = repo_data["releases"]
            results["releases"].extend(
                _graphql_release_to_rest(node) for node in connection.get("nodes", [])
            )
            if connection["pageInfo"]["hasNextPage"]:
                cursors["releases"] = connection["pageInfo"]["endCursor"]
            else:
                done["releases"] = True

    logger.debug(
        "GraphQL metadata for %s/%s: %d issues, %d pulls, %d milestones, "
        "%d labels, %d releases",
        owner,
        name,
        len(results["issues"]),
        len(results["pulls"]),
        len(results["milestones"]),
        len(results["labels"]),
        len(results["releases"]),
    )
    return results


def write_repo_metadata(repo_cwd, repository):
    """Persist the repository metadata object as ``repo.json`` (atomic).

    It is useful backup data in its own right (description, topics,
    visibility, default branch, archived state, ...) and marks the repository
    as completely backed up by the last run.

    Internal bookkeeping keys (prefixed with ``_``, added during discovery) are
    stripped so the file contains only GitHub's own data.

    Returns the path written, or ``None`` if it could not be written.
    """
    clean = {k: v for k, v in repository.items() if not k.startswith("_")}
    path = os.path.join(repo_cwd, REPO_METADATA_FILENAME)
    tmp_path = path + ".tmp"
    try:
        mkdir_p(repo_cwd)
        with codecs.open(tmp_path, "w", encoding="utf-8") as f:
            json_dump(clean, f)
        os.replace(tmp_path, path)
        return path
    except Exception as e:
        logger.error(f"Failed to write repo metadata {path}: {format_exception(e)}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return None


# Global variables for GitHub App token management
_github_app_tokens = (
    {}
)  # Cache tokens per installation: {installation_id: (token, expires_at)}
_github_app_credentials = None
_token_refresh_failures = (
    {}
)  # Track consecutive token refresh failures per installation
_token_refresh_failure_times = {}  # Track when failures occurred for backoff

https_ctx = ssl.create_default_context()
if not https_ctx.get_ca_certs():
    import warnings

    warnings.warn(
        "\n\nYOUR DEFAULT CA CERTS ARE EMPTY.\n"
        + "PLEASE POPULATE ANY OF:"
        + "".join(
            ["\n - " + x for x in ssl.get_default_verify_paths() if type(x) is str]
        )
        + "\n",
        stacklevel=2,
    )
    import certifi

    https_ctx = ssl.create_default_context(cafile=certifi.where())


def logging_subprocess(
    popenargs, stdout_log_level=logging.DEBUG, stderr_log_level=logging.ERROR, **kwargs
):
    """
    Variant of subprocess.call that accepts a logger instead of stdout/stderr,
    and logs stdout messages via logger.debug and stderr messages via
    logger.error.
    """
    child = subprocess.Popen(
        popenargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
    if sys.platform == "win32":
        logger.info(
            "Windows operating system detected - no subprocess logging will be returned"
        )

    log_level = {child.stdout: stdout_log_level, child.stderr: stderr_log_level}

    def check_io():
        if sys.platform == "win32":
            return
        ready_to_read = select.select([child.stdout, child.stderr], [], [], 1000)[0]
        for io in ready_to_read:
            line = io.readline()
            if not logger:
                continue
            if not (io == child.stderr and not line):
                # Decode bytes to string for proper logging
                line_str = line.decode("utf-8", errors="replace").rstrip("\n")
                # Only log non-empty lines to avoid cluttering the output
                if line_str.strip():
                    logger.log(log_level[io], line_str)

    # keep checking stdout/stderr until the child exits
    while child.poll() is None:
        check_io()

    check_io()  # check again to catch anything after the process exits

    rc = child.wait()

    if rc != 0:
        print("{} returned {}:".format(popenargs[0], rc), file=sys.stderr)
        print("\t", " ".join(popenargs), file=sys.stderr)

    return rc


def mkdir_p(*args):
    for path in args:
        try:
            os.makedirs(path)
        except OSError as exc:  # Python >2.5
            if exc.errno == errno.EEXIST and os.path.isdir(path):
                pass
            else:
                raise


def mask_password(url, secret="*****"):
    parsed = urlparse(url)

    if not parsed.password:
        return url
    elif parsed.password == "x-oauth-basic":
        return url.replace(parsed.username, secret)

    return url.replace(parsed.password, secret)


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Backup GitHub repositories and metadata using GitHub App authentication"
    )
    parser.add_argument(
        "users",
        metavar="USER",
        nargs="*",
        help="GitHub username(s) or organization(s) to backup (optional - if not provided, will backup all discovered installations)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        dest="quiet",
        help="supress log messages less severe than warning, e.g. info",
    )

    parser.add_argument(
        "--app-id",
        dest="app_id",
        help="GitHub App ID for app authentication",
    )

    parser.add_argument(
        "--private-key",
        dest="private_key",
        help="GitHub App private key (PEM format) or path to private key file (file://...)",
    )
    parser.add_argument(
        "-o",
        "--output-directory",
        default=".",
        dest="output_directory",
        help="directory at which to backup the repositories",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        default="info",
        dest="log_level",
        help="log level to use (default: info, possible levels: debug, info, warning, error, critical)",
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        dest="force_full",
        help=(
            "ignore stored backup data and re-fetch everything: re-fetch every "
            "repository's git content and every issue/pull/milestone even when "
            "unchanged since the last backup"
        ),
    )

    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_everything",
        help="include everything in backup (not including [*])",
    )
    parser.add_argument(
        "--issues",
        action="store_true",
        dest="include_issues",
        help="include issues in backup",
    )
    parser.add_argument(
        "--issue-comments",
        action="store_true",
        dest="include_issue_comments",
        help="include issue comments in backup",
    )
    parser.add_argument(
        "--issue-events",
        action="store_true",
        dest="include_issue_events",
        help="include issue events in backup",
    )
    parser.add_argument(
        "--pulls",
        action="store_true",
        dest="include_pulls",
        help="include pull requests in backup",
    )
    parser.add_argument(
        "--pull-comments",
        action="store_true",
        dest="include_pull_comments",
        help="include pull request review comments in backup",
    )
    parser.add_argument(
        "--pull-commits",
        action="store_true",
        dest="include_pull_commits",
        help="include pull request commits in backup",
    )
    parser.add_argument(
        "--pull-details",
        action="store_true",
        dest="include_pull_details",
        help="include more pull request details in backup [*]",
    )
    parser.add_argument(
        "--labels",
        action="store_true",
        dest="include_labels",
        help="include labels in backup",
    )
    parser.add_argument(
        "--hooks",
        action="store_true",
        dest="include_hooks",
        help="include hooks in backup (works only when authenticated)",
    )  # noqa
    parser.add_argument(
        "--milestones",
        action="store_true",
        dest="include_milestones",
        help="include milestones in backup",
    )
    parser.add_argument(
        "--repositories",
        action="store_true",
        dest="include_repository",
        default=True,
        help="include repository clone in backup (default: True)",
    )
    parser.add_argument(
        "--bare",
        action="store_true",
        dest="bare_clone",
        help="deprecated, no effect: repositories are always stored as bare mirrors",
    )
    parser.add_argument(
        "--no-prune",
        action="store_true",
        dest="no_prune",
        help=(
            "deprecated, no effect: refs deleted on GitHub are always moved "
            "to refs/backup/<timestamp>/"
        ),
    )
    parser.add_argument(
        "--lfs",
        action="store_true",
        dest="lfs_clone",
        help="clone LFS repositories (requires Git LFS to be installed, https://git-lfs.github.com) [*]",
    )
    parser.add_argument(
        "--wikis",
        action="store_true",
        dest="include_wiki",
        help="include wiki clone in backup",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        dest="skip_existing",
        help="skip project if a backup directory exists",
    )
    parser.add_argument(
        "-L",
        "--languages",
        dest="languages",
        help="only allow these languages",
        nargs="*",
    )
    parser.add_argument(
        "-N",
        "--name-regex",
        dest="name_regex",
        help="python regex to match names against",
    )
    parser.add_argument(
        "-H", "--github-host", dest="github_host", help="GitHub Enterprise hostname"
    )

    parser.add_argument(
        "-R",
        "--repository",
        dest="repository",
        help="name of repository to limit backup to",
    )

    parser.add_argument(
        "-v", "--version", action="version", version="%(prog)s " + VERSION
    )

    parser.add_argument(
        "--releases",
        action="store_true",
        dest="include_releases",
        help="include release information, not including assets or binaries",
    )
    parser.add_argument(
        "--latest-releases",
        type=int,
        default=0,
        dest="number_of_latest_releases",
        help="include certain number of the latest releases; only applies if including releases",
    )
    parser.add_argument(
        "--skip-prerelease",
        action="store_true",
        dest="skip_prerelease",
        help="skip prerelease and draft versions; only applies if including releases",
    )
    parser.add_argument(
        "--assets",
        action="store_true",
        dest="include_assets",
        help="include assets alongside release information; only applies if including releases",
    )
    parser.add_argument(
        "--throttle-limit",
        dest="throttle_limit",
        type=int,
        default=0,
        help="start throttling of GitHub API requests after this amount of API requests remain",
    )
    parser.add_argument(
        "--throttle-pause",
        dest="throttle_pause",
        type=float,
        default=30.0,
        help="wait this amount of seconds when API request throttling is active (default: 30.0, requires --throttle-limit to be set)",
    )
    parser.add_argument(
        "--exclude", dest="exclude", help="names of repositories to exclude", nargs="*"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="show what would be backed up without actually performing the backup",
    )

    return parser.parse_args(args)


def validate_args(args):
    """Validate argument combinations and dependencies."""
    if args.quiet:
        logger.setLevel(logging.WARNING)

    # GitHub App authentication is now mandatory
    if not (args.app_id and args.private_key):
        raise Exception(
            "GitHub App authentication is required. Please provide --app-id and --private-key.\n"
            "Create a GitHub App at https://github.com/settings/apps/new and install it on your account/organization."
        )


def get_auth(args, installation_id, encode=True, for_git_cli=False):
    """Get authentication for GitHub App for a specific installation."""
    global _github_app_credentials

    if not installation_id:
        raise Exception("Installation ID is required for authentication.")

    logger.debug(f"get_auth called with installation_id={installation_id}")

    # Store credentials globally for token refresh (only if not already set)
    if not _github_app_credentials:
        _github_app_credentials = (
            args.app_id,
            installation_id,  # Use the first installation_id for credentials
            args.private_key,
        )

    # Get fresh token for this specific installation
    github_host = get_github_api_host(args)
    token = get_or_refresh_github_app_token(installation_id, github_host)
    if not token:
        raise Exception("Failed to generate GitHub App installation token")

    # Log token details for debugging
    logger.debug(f"Using token ...{token[-4:]} (length: {len(token)})")
    if not token.startswith("ghs_"):
        raise Exception(f"Token doesn't start with 'ghs_': {token[:20]}...")

    # Log successful token usage
    logger.debug(
        f"Successfully obtained valid token for installation {installation_id}"
    )

    if not for_git_cli:
        auth = token
    else:
        auth = "x-access-token:" + token

    # For GitHub App tokens, we don't need to encode
    if not encode or not for_git_cli:
        return auth
    return base64.b64encode(auth.encode("ascii"))


def generate_github_app_token(
    app_id, installation_id, private_key, github_host="api.github.com"
):
    """Generate an installation access token for GitHub App authentication."""
    try:
        # Load private key
        if private_key.startswith(FILE_URI_PREFIX):
            private_key = read_file_contents(private_key)
        elif os.path.exists(private_key):
            # If it's a file path, convert to file:// format
            file_uri = f"{FILE_URI_PREFIX}{private_key}"
            private_key = read_file_contents(file_uri)

        # Create JWT payload
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued at (1 minute ago to account for clock skew)
            "exp": now + 600,  # Expires in 10 minutes (max allowed)
            "iss": str(
                app_id
            ),  # Issuer (GitHub App ID); must be a string for PyJWT >= 2.11.0
        }
        # Generate JWT
        jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

        # Request installation access token
        url = f"https://{github_host}/app/installations/{installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"github-backup/{VERSION}",
        }

        request = Request(url, headers=headers, method="POST")
        request.data = b""  # Empty POST body

        response = urlopen(request, context=https_ctx)
        data = json.loads(response.read().decode("utf-8"))

        token = data["token"]
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))

        logger.info(
            f"Generated GitHub App installation token for installation {installation_id} (expires at {expires_at})"
        )
        logger.debug(f"Token starts with: {token[:10]}...")

        # Validate the token
        logger.debug(f"Validating generated token for installation {installation_id}")
        if not validate_github_app_token(token, github_host):
            raise Exception("Generated token failed validation")

        logger.info(f"Token validation successful for installation {installation_id}")
        return token, expires_at

    except Exception as e:
        raise Exception(f"Failed to generate GitHub App token: {str(e)}")


def _is_token_refresh_circuit_open(installation_id):
    """Check if the circuit breaker is open for token refresh failures."""
    global _token_refresh_failures, _token_refresh_failure_times

    failures = _token_refresh_failures.get(installation_id, 0)
    if failures < 3:  # Allow up to 3 consecutive failures
        return False

    # Check if enough time has passed since last failure (exponential backoff)
    last_failure_time = _token_refresh_failure_times.get(installation_id)
    if not last_failure_time:
        return False

    # Exponential backoff: 2^failures minutes, max 30 minutes
    backoff_minutes = min(2**failures, 30)
    backoff_duration = timedelta(minutes=backoff_minutes)

    if datetime.utcnow() - last_failure_time < backoff_duration:
        logger.warning(
            f"Circuit breaker open for installation {installation_id}. "
            f"Failed {failures} times, waiting {backoff_minutes} minutes before retry."
        )
        return True

    return False


def _record_token_refresh_success(installation_id):
    """Record a successful token refresh, resetting failure counters."""
    global _token_refresh_failures, _token_refresh_failure_times
    _token_refresh_failures[installation_id] = 0
    _token_refresh_failure_times.pop(installation_id, None)


def _record_token_refresh_failure(installation_id):
    """Record a token refresh failure, incrementing failure counters."""
    global _token_refresh_failures, _token_refresh_failure_times
    _token_refresh_failures[installation_id] = (
        _token_refresh_failures.get(installation_id, 0) + 1
    )
    _token_refresh_failure_times[installation_id] = datetime.utcnow()


def get_or_refresh_github_app_token(installation_id, github_host="api.github.com"):
    """Get current GitHub App token or refresh it if expired/missing for a specific installation."""
    global _github_app_tokens, _github_app_credentials

    if not _github_app_credentials:
        return None

    app_id, _, private_key = _github_app_credentials

    # Check circuit breaker first
    if _is_token_refresh_circuit_open(installation_id):
        raise Exception(
            f"Token refresh circuit breaker is open for installation {installation_id}. "
            "Too many consecutive failures. Please check your GitHub App credentials and network connectivity."
        )

    # Check if we have a cached token for this installation
    cached_token, cached_expires = _github_app_tokens.get(installation_id, (None, None))

    # Simple approach: Check if token exists and is not expired (with 5-minute buffer)
    # Convert both times to UTC for comparison (GitHub API returns UTC times)
    now_utc = datetime.utcnow()
    expires_utc = cached_expires.replace(tzinfo=None) if cached_expires else None

    # Generate new token if:
    # 1. No token exists for this installation
    # 2. Token is expired or will expire within TOKEN_MIN_REMAINING (long
    #    git/LFS transfers authenticate once per request with the token
    #    they were started with, so leave them plenty of time)
    if (
        cached_token is None
        or expires_utc is None
        or now_utc >= (expires_utc - TOKEN_MIN_REMAINING)
    ):
        logger.info(
            f"Generating new GitHub App token for installation {installation_id}..."
        )
        logger.debug(
            f"Token generation conditions: token_exists={cached_token is not None}, expires_utc={expires_utc}, now_utc={now_utc}"
        )

        try:
            new_token, new_expires = generate_github_app_token(
                app_id, installation_id, private_key, github_host
            )
            # Cache the token for this installation
            _github_app_tokens[installation_id] = (new_token, new_expires)
            _record_token_refresh_success(installation_id)
            return new_token
        except Exception as e:
            _record_token_refresh_failure(installation_id)
            logger.error(
                f"Failed to generate token for installation {installation_id}: {str(e)}"
            )
            raise
    else:
        logger.debug(
            f"Using cached token for installation {installation_id}, expires at: {cached_expires}"
        )
        return cached_token


def validate_github_app_token(token, github_host="api.github.com"):
    """Validate a GitHub App installation token by making a test API call."""
    try:
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"github-backup/{VERSION}",
        }

        # Test with rate limit endpoint
        request = Request(f"https://{github_host}/rate_limit", headers=headers)
        response = urlopen(request, context=https_ctx)

        if response.getcode() == 200:
            data = json.loads(response.read().decode("utf-8"))
            logger.debug(
                f"Token validation successful. Rate limit: {data.get('rate', {}).get('remaining', 'unknown')} remaining"
            )
            return True
        else:
            logger.error(
                f"Token validation failed with status code: {response.getcode()}"
            )
            return False

    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        return False


def discover_github_app_installations(
    app_id, private_key, github_host="api.github.com"
):
    """Discover all installations of a GitHub App."""
    try:
        # Load private key
        if private_key.startswith(FILE_URI_PREFIX):
            private_key = read_file_contents(private_key)
        elif os.path.exists(private_key):
            file_uri = f"{FILE_URI_PREFIX}{private_key}"
            private_key = read_file_contents(file_uri)

        # Create JWT payload
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued at (1 minute ago to account for clock skew)
            "exp": now + 600,  # Expires in 10 minutes (max allowed)
            "iss": str(
                app_id
            ),  # Issuer (GitHub App ID); must be a string for PyJWT >= 2.11.0
        }

        # Generate JWT
        jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

        # Request installations list
        url = f"https://{github_host}/app/installations"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"github-backup/{VERSION}",
        }

        request = Request(url, headers=headers)
        response = urlopen(request, context=https_ctx)
        installations = json.loads(response.read().decode("utf-8"))

        logger.info(f"Discovered {len(installations)} GitHub App installations")
        for installation in installations:
            account = installation.get("account", {})
            account_type = account.get("type", "unknown")
            account_login = account.get("login", "unknown")
            installation_id = installation.get("id", "unknown")
            logger.info(
                f"  - {account_type}: {account_login} (installation ID: {installation_id})"
            )

        return installations

    except Exception as e:
        raise Exception(
            f"Failed to discover GitHub App installations: {format_exception(e)}"
        ) from e


def get_github_api_host(args):
    if args.github_host:
        host = args.github_host + "/api/v3"
    else:
        host = "api.github.com"

    return host


def get_github_host(args):
    if args.github_host:
        host = args.github_host
    else:
        host = "github.com"

    return host


def read_file_contents(file_uri):
    return open(file_uri[len(FILE_URI_PREFIX) :], "rt").read()


def get_github_repo_url(args, repository):
    """HTTPS clone URL of a repository, without credentials.

    Authentication is supplied per git invocation by get_git_auth_env, so this
    URL is what ends up in the backup's git config.
    """
    return "https://{0}/{1}/{2}.git".format(
        get_github_host(args), repository["owner"]["login"], repository["name"]
    )


def get_github_wiki_url(args, repository):
    return "https://{0}/{1}/{2}.wiki.git".format(
        get_github_host(args), repository["owner"]["login"], repository["name"]
    )


def retrieve_data_gen(
    args, template, installation_id, query_args=None, single_request=False
):
    query_args = get_query_args(query_args)
    per_page = 100
    page = 0

    while True:
        if single_request:
            request_page, request_per_page = None, None
        else:
            page = page + 1
            request_page, request_per_page = page, per_page

        # Always get fresh auth before each API call - this handles token refresh automatically
        auth = get_auth(args, installation_id, encode=False)
        logger.debug(
            f"Using installation token for installation {installation_id} for API request to {template}"
        )

        request = _construct_request(
            request_per_page,
            request_page,
            query_args,
            template,
            auth,
            as_app=True,
            fine=False,
        )  # noqa
        r, errors = _get_response(request, auth, template, args)

        status_code = int(r.getcode())
        # Check if we got correct data
        try:
            response = json.loads(r.read().decode("utf-8"))

        except IncompleteRead:
            logger.warning("Incomplete read error detected")
            read_error = True
        except json.decoder.JSONDecodeError:
            logger.warning("JSON decode error detected")
            read_error = True
        except TimeoutError:
            logger.warning("Tiemout error detected")
            read_error = True
        else:
            read_error = False

        # be gentle with API request limit and throttle requests if remaining requests getting low
        limit_remaining = int(r.headers.get("x-ratelimit-remaining", 0))
        if args.throttle_limit and limit_remaining <= args.throttle_limit:
            logger.info(
                "API request limit hit: {} requests left, pausing further requests for {}s".format(
                    limit_remaining, args.throttle_pause
                )
            )

            # Clear cached tokens during throttling to prevent expiration during pause
            if _github_app_credentials is not None:
                logger.info(
                    "Throttling active, clearing cached tokens to prevent expiration during pause"
                )
                global _github_app_tokens
                _github_app_tokens.clear()

            time.sleep(args.throttle_pause)

        retries = 0
        while retries < 3 and (status_code == 502 or read_error):
            logger.warning("API request failed. Retrying in 5 seconds")
            retries += 1
            time.sleep(5)

            # Get fresh auth for retry - this will automatically handle token refresh if needed
            auth = get_auth(args, installation_id, encode=False)

            request = _construct_request(
                per_page,
                page,
                query_args,
                template,
                auth,
                as_app=True,
                fine=False,
            )  # noqa
            r, errors = _get_response(request, auth, template)

            status_code = int(r.getcode())
            try:
                response = json.loads(r.read().decode("utf-8"))
                read_error = False
            except IncompleteRead:
                logger.warning("Incomplete read error detected")
                read_error = True
            except json.decoder.JSONDecodeError:
                logger.warning("JSON decode error detected")
                read_error = True
            except TimeoutError:
                logger.warning("Tiemout error detected")
                read_error = True

        if status_code != 200:
            # Try to get more detailed error information from GitHub API response
            error_details = ""
            required_permissions = ""
            try:
                if hasattr(r, "read"):
                    response_body = r.read().decode("utf-8")
                    if response_body:
                        error_data = json.loads(response_body)
                        if "message" in error_data:
                            error_details = f" - {error_data['message']}"
                        if "documentation_url" in error_data:
                            error_details += (
                                f" (See: {error_data['documentation_url']})"
                            )

                        # Check for required permissions header
                        if hasattr(r, "headers"):
                            required_perms = r.headers.get(
                                "X-Accepted-GitHub-Permissions", ""
                            )
                            if required_perms:
                                required_permissions = (
                                    f" Required permissions: {required_perms}"
                                )
            except json.JSONDecodeError, UnicodeDecodeError, AttributeError:
                # If we can't parse the error response, just use the basic info
                pass

            template = "API request returned HTTP {0}: {1}{2}{3}"
            errors.append(
                template.format(
                    status_code, r.reason, error_details, required_permissions
                )
            )
            raise Exception(", ".join(errors))

        if read_error:
            template = "API request problem reading response for {0}"
            errors.append(template.format(request))
            raise Exception(", ".join(errors))

        if len(errors) == 0:
            if type(response) is list:
                # Yield all items from the response
                for resp in response:
                    yield resp
                if len(response) < per_page:
                    break
            elif type(response) is dict:
                # Handle special case for /installation/repositories endpoint
                if "repositories" in response and "total_count" in response:
                    repos_list = response["repositories"]
                    total_count = response["total_count"]
                    repository_selection = response.get(
                        "repository_selection", "unknown"
                    )

                    for resp in repos_list:
                        yield resp

                    # For installation/repositories, stop if we got fewer repos than requested
                    if len(repos_list) < per_page:
                        break
                elif single_request:
                    yield response

        if len(errors) > 0:
            raise Exception(", ".join(errors))

        if single_request:
            break


def retrieve_data(
    args, template, installation_id, query_args=None, single_request=False
):
    return list(
        retrieve_data_gen(args, template, installation_id, query_args, single_request)
    )


def get_query_args(query_args=None):
    if not query_args:
        query_args = {}
    return query_args


def _get_response(request, auth, template, args=None):
    retry_timeout = 3
    errors = []
    retry_count = 0
    max_retries = 10  # Maximum number of retries to prevent infinite loops
    session = get_github_http_session()

    # We'll make requests in a loop so we can
    # delay and retry in the case of rate-limiting
    while retry_count < max_retries:
        should_continue = False
        try:
            method = request.get_method() if hasattr(request, "get_method") else "GET"
            headers = dict(request.header_items())
            data = getattr(request, "data", None)
            response = session.request(
                method,
                request.full_url,
                headers=headers,
                data=data,
                timeout=120,
            )
            if response.status_code >= 400:
                http_error = _HttpErrorResponse(response)
                errors, should_continue = _request_http_error(
                    http_error, auth, errors, args
                )
                r = http_error
            else:
                r = _HttpResponse(response)
        except requests.RequestException as e:
            reason = getattr(e, "args", [str(e)])[0]
            logger.warning(reason)
            should_continue, retry_timeout = _request_url_error(template, retry_timeout)
            if not should_continue:
                raise
            r = None
        except socket.error as e:
            logger.warning(e.strerror)
            should_continue, retry_timeout = _request_url_error(template, retry_timeout)
            if not should_continue:
                raise
            r = None

        if should_continue:
            retry_count += 1
            if retry_count >= max_retries:
                logger.error(
                    f"Maximum retry limit ({max_retries}) reached for {template}. Stopping to prevent infinite loop."
                )
                break
            continue

        break

    if retry_count >= max_retries:
        raise Exception(
            f"Request failed after {max_retries} retries for {template}. This may indicate a persistent issue with authentication or network connectivity."
        )

    return r, errors


def _construct_request(
    per_page, page, query_args, template, auth, as_app=True, fine=False
):
    all_query_args = {}
    if per_page:
        all_query_args["per_page"] = per_page
    if page:
        all_query_args["page"] = page
    if query_args:
        all_query_args.update(query_args)

    request_url = template
    if all_query_args:
        querystring = urlencode(all_query_args)
        request_url = template + "?" + querystring
    else:
        querystring = ""

    request = Request(request_url)
    if auth is not None:
        # GitHub App authentication always uses token format
        request.add_header("Authorization", "token " + auth)

    log_url = template
    if querystring:
        log_url += "?" + querystring
    logger.debug("Requesting {}".format(log_url))
    return request


def _request_http_error(exc, auth, errors, args=None):
    # HTTPError behaves like a Response so we can
    # check the status code and headers to see exactly
    # what failed.

    should_continue = False
    headers = exc.headers
    limit_remaining = int(headers.get("x-ratelimit-remaining", 0))

    # Handle GitHub App token expiry (401 Unauthorized)
    if exc.code == 401 and _github_app_credentials is not None:
        logger.warning(
            "GitHub App token expired (401 Unauthorized). Refreshing token..."
        )
        try:
            # Force refresh the token - we need to clear all cached tokens
            # since we don't know which specific installation token expired
            global _github_app_tokens, _token_refresh_failures, _token_refresh_failure_times
            _github_app_tokens.clear()  # Clear all cached tokens

            # Also clear failure tracking since we're forcing a refresh
            _token_refresh_failures.clear()
            _token_refresh_failure_times.clear()

            # Clear cached tokens - the next request will generate fresh tokens as needed
            # This is simpler and more reliable than trying to pre-generate tokens here
            logger.info(
                "Cleared cached tokens, will generate fresh token on next request"
            )
            should_continue = True
        except Exception as e:
            logger.error(f"Error refreshing GitHub App token: {str(e)}")
            # Don't continue if there's an error in the refresh process
            should_continue = False
    elif exc.code == 403 and limit_remaining < 1:
        # Rate limit exceeded - wait for reset time
        # The X-RateLimit-Reset header includes a
        # timestamp telling us when the limit will reset
        # so we can calculate how long to wait rather
        # than inefficiently polling:
        gm_now = calendar.timegm(time.gmtime())
        reset = int(headers.get("x-ratelimit-reset", 0)) or gm_now
        # We'll never sleep for less than 10 seconds:
        delta = max(10, reset - gm_now)

        limit = headers.get("x-ratelimit-limit")
        logger.warning(
            "Exceeded rate limit of {} requests; waiting {} seconds to reset".format(
                limit, delta
            )
        )  # noqa

        if auth is None:
            logger.info("Hint: Authenticate to raise your GitHub rate limit")

        # Always clear cached tokens when hitting rate limits to prevent using expired tokens after the wait
        # GitHub App tokens expire after 1 hour, so any significant wait could cause expiration
        if _github_app_credentials is not None:
            logger.info(
                "Rate limit hit, clearing cached tokens to prevent expiration during wait"
            )
            _github_app_tokens.clear()

        time.sleep(delta)
        should_continue = True
    return errors, should_continue


def _request_url_error(template, retry_timeout):
    # In case of a connection timing out, we can retry a few time
    # But we won't crash and not back-up the rest now
    logger.info("'{}' timed out".format(template))
    retry_timeout -= 1

    if retry_timeout >= 0:
        return True, retry_timeout

    raise Exception("'{}' timed out to much, skipping!".format(template))


class S3HTTPRedirectHandler(HTTPRedirectHandler):
    """
    A subclassed redirect handler for downloading Github assets from S3.

    urllib will add the Authorization header to the redirected request to S3, which will result in a 400,
    so we should remove said header on redirect.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        request = super(S3HTTPRedirectHandler, self).redirect_request(
            req, fp, code, msg, headers, newurl
        )
        del request.headers["Authorization"]
        return request


def download_file(url, path, auth, as_app=True, fine=False):
    # Skip downloading release assets if they already exist on disk so we don't redownload on every sync
    if os.path.exists(path):
        return

    request = _construct_request(
        per_page=100,
        page=1,
        query_args={},
        template=url,
        auth=auth,
        as_app=True,
        fine=fine,
    )
    request.add_header("Accept", "application/octet-stream")
    opener = build_opener(S3HTTPRedirectHandler)

    try:
        response = opener.open(request)

        chunk_size = 16 * 1024
        with open(path, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
    except HTTPError as exc:
        # Gracefully handle 404 responses (and others) when downloading from S3
        logger.warning(
            "Skipping download of asset {0} due to HTTPError: {1}".format(
                url, exc.reason
            )
        )
    except URLError as e:
        # Gracefully handle other URL errors
        logger.warning(
            "Skipping download of asset {0} due to URLError: {1}".format(url, e.reason)
        )
    except socket.error as e:
        # Gracefully handle socket errors
        # TODO: Implement retry logic
        logger.warning(
            "Skipping download of asset {0} due to socker error: {1}".format(
                url, e.strerror
            )
        )


def check_git_lfs_install():
    exit_code = subprocess.call(["git", "lfs", "version"])
    if exit_code != 0:
        raise Exception(
            "The argument --lfs requires you to have Git LFS installed.\nYou can get it from https://git-lfs.github.com."
        )


def retrieve_repositories(args, authenticated_user):
    """Retrieve repositories from all accessible GitHub App installations."""
    logger.info("Retrieving repositories from all accessible installations")
    return retrieve_all_accessible_repositories(args)


def collect_backup_plan(args):
    """Collect all information about what would be backed up without actually backing up."""
    logger.info("Collecting backup plan...")

    # Discover all installations
    installations = discover_github_app_installations(
        args.app_id, args.private_key, get_github_api_host(args)
    )

    if not installations:
        logger.warning("No GitHub App installations found")
        return []

    backup_plan = []
    total_installations = len(installations)

    for i, installation in enumerate(installations, 1):
        installation_id = installation.get("id")
        account = installation.get("account", {})
        account_type = account.get("type", "unknown")
        account_login = account.get("login", "unknown")

        # Filter installations if specific users are specified
        if args.users and account_login not in args.users:
            logger.info(
                f"Skipping installation {i}/{total_installations}: {account_type} '{account_login}' (not in filter list)"
            )
            continue

        logger.info(
            f"Processing installation {i}/{total_installations}: {account_type} '{account_login}'"
        )

        try:
            # Generate token for this installation
            token, expires_at = generate_github_app_token(
                args.app_id,
                installation_id,
                args.private_key,
                get_github_api_host(args),
            )

            # Get repositories for this installation
            installation_repos = retrieve_repositories_from_installation(
                args, installation_id, token
            )

            # Apply repository-level filters
            filtered_repos = apply_repository_filters(args, installation_repos)

            # Count repositories (all are regular repositories now)
            regular_repos = filtered_repos

            # Add installation context to each repository
            repos_with_context = []
            for repo in filtered_repos:
                repo_with_context = repo.copy()
                repo_with_context["_installation_id"] = installation_id
                repo_with_context["_account_type"] = account_type
                repo_with_context["_account_login"] = account_login
                repos_with_context.append(repo_with_context)

            installation_info = {
                "installation_id": installation_id,
                "account_type": account_type,
                "account_login": account_login,
                "repositories": repos_with_context,
                "counts": {
                    "repositories": len(regular_repos),
                    "total": len(filtered_repos),
                },
            }

            backup_plan.append(installation_info)
            logger.info(
                f"Found {len(filtered_repos)} repositories in {account_type} '{account_login}' (filtered from {len(installation_repos)} total)"
            )

        except Exception as e:
            logger.error(
                f"Failed to retrieve repositories from {account_type} '{account_login}': {str(e)}"
            )
            continue

    return backup_plan


def retrieve_all_accessible_repositories(args):
    """Retrieve all repositories accessible to the GitHub App across all installations."""
    backup_plan = collect_backup_plan(args)

    # Flatten all repositories from all installations
    all_repos = []
    for installation in backup_plan:
        all_repos.extend(installation["repositories"])

    logger.info(f"Total repositories found across all installations: {len(all_repos)}")

    # Log directory structure info
    logger.info(
        "Backups will be organized by account/org: {output_directory}/{owner}/repositories/{repo_name}"
    )

    return all_repos


def retrieve_repositories_from_installation(args, installation_id, token=None):
    """Retrieve repositories from a specific GitHub App installation."""
    if token is None:
        # Use the global token system
        repos = []
        template = "https://{0}/installation/repositories".format(
            get_github_api_host(args)
        )

        # Use the generator to process repositories one by one
        for repo in retrieve_data_gen(
            args, template, installation_id, single_request=False
        ):
            repos.append(repo)

        return repos
    else:
        # Use provided token directly
        template = "https://{0}/installation/repositories".format(
            get_github_api_host(args)
        )

        # Make direct API call with the provided token
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"github-backup/{VERSION}",
        }

        repos = []
        page = 1
        per_page = 100

        while True:
            url = f"{template}?per_page={per_page}&page={page}"
            request = Request(url, headers=headers)

            try:
                response = urlopen(request, context=https_ctx)
                data = json.loads(response.read().decode("utf-8"))

                if isinstance(data, dict) and "repositories" in data:
                    # Installation repositories response format
                    repos_list = data["repositories"]
                    if not repos_list:
                        break
                    repos.extend(repos_list)
                    if len(repos_list) < per_page:
                        break
                elif isinstance(data, list):
                    # Direct list response
                    if not data:
                        break
                    repos.extend(data)
                    if len(data) < per_page:
                        break
                else:
                    break

                page += 1

            except Exception as e:
                logger.error(
                    f"Failed to retrieve repositories from page {page}: {str(e)}"
                )
                break

        return repos


def apply_repository_filters(args, repositories):
    """Apply all repository filters (name regex, languages, exclude) to repositories."""
    filtered_repos = repositories

    # Apply repository name filter
    if args.repository:
        filtered_repos = [
            r
            for r in filtered_repos
            if r.get("name") == args.repository or r.get("full_name") == args.repository
        ]

    # Apply name regex filter
    if args.name_regex:
        name_regex = re.compile(args.name_regex)
        filtered_repos = [
            r for r in filtered_repos if "name" not in r or name_regex.match(r["name"])
        ]

    # Apply language filter
    if args.languages:
        languages = [x.lower() for x in args.languages]
        filtered_repos = [
            r
            for r in filtered_repos
            if r.get("language") and r.get("language").lower() in languages
        ]

    # Apply exclude filter
    if args.exclude:
        filtered_repos = [
            r
            for r in filtered_repos
            if "name" not in r or r["name"] not in args.exclude
        ]

    return filtered_repos


def filter_repositories(args, unfiltered_repositories):
    """Legacy function - filtering now happens during discovery."""
    # This function is kept for compatibility but filtering is now done in collect_backup_plan
    return unfiltered_repositories


def backup_repositories(args, output_directory, repositories):
    logger.info("Backing up repositories")
    logger.info(f"Number of repositories to backup: {len(repositories)}")
    repos_template = "https://{0}/repos".format(get_github_api_host(args))

    # Git: fetch_repository compares GitHub's refs (one ls-remote) with the
    # mirror and skips the (often dominant) fetch when nothing changed.
    # NOTE: we deliberately do NOT use the repository's `updated_at` to skip
    # issues/PRs/etc. - that field only reflects repository *metadata* changes,
    # not issue/PR/comment activity, so trusting it would silently miss data.
    total = len(repositories)
    succeeded = 0
    git_skipped = 0
    issues_skipped = 0
    pulls_skipped = 0
    milestones_skipped = 0
    git_refs_archived = 0
    recovered_repositories = []
    lfs_warnings = []
    failed_repositories = []
    accounts = set()
    interrupted = False

    for i, repository in enumerate(repositories, 1):
        repo_full_name = repository.get("full_name", "unknown")
        logger.info(f"Processing repository {i}/{total}: {repo_full_name}")

        # Isolate each repository so a single failure does not abort the
        # whole run; record the failure so it surfaces in logs and the
        # status file instead of silently taking down everything else.
        try:
            owner = repository.get("owner", {}).get("login", "unknown")
            accounts.add(owner)

            # For repositories, organize by owner as top level
            repo_cwd = os.path.join(
                output_directory, owner, "repositories", repository["name"]
            )

            repo_dir = os.path.join(repo_cwd, "repository")
            repo_url = get_github_repo_url(args, repository)
            # A git failure must fail the repository, but should not prevent
            # backing up its issues, PRs and releases in the same run.
            git_errors = []

            if args.include_repository or args.include_everything:
                repo_name = repository.get("name")
                try:
                    mkdir_p(repo_cwd)
                    result = fetch_repository(
                        repo_name,
                        repo_url,
                        repo_dir,
                        lambda: get_git_auth_env(args, repository),
                        skip_existing=args.skip_existing,
                        lfs_clone=args.lfs_clone,
                        force=args.force_full,
                    )
                    if result.lfs_error:
                        lfs_warnings.append(
                            {"repository": repo_full_name, "error": result.lfs_error}
                        )
                    git_refs_archived += result.archived
                    git_skipped += result.skipped
                    if result.recovered:
                        recovered_repositories.append(
                            {"repository": repo_full_name, **result.recovered}
                        )
                except Exception as e:
                    logger.error(f"Git backup of {repo_full_name} failed: {e}")
                    git_errors.append(e)

            download_wiki = args.include_wiki or args.include_everything
            if repository["has_wiki"] and download_wiki:
                try:
                    result = fetch_repository(
                        f"{repository['name']} wiki",
                        get_github_wiki_url(args, repository),
                        os.path.join(repo_cwd, "wiki"),
                        lambda: get_git_auth_env(args, repository),
                        skip_existing=args.skip_existing,
                        optional=True,
                        force=args.force_full,
                    )
                    git_refs_archived += result.archived
                    if result.recovered:
                        recovered_repositories.append(
                            {"repository": f"{repo_full_name} wiki", **result.recovered}
                        )
                except Exception as e:
                    logger.error(f"Wiki backup of {repo_full_name} failed: {e}")
                    git_errors.append(e)

            fetch_issues = args.include_issues or args.include_everything
            fetch_pulls = args.include_pulls or args.include_everything
            fetch_milestones = args.include_milestones or args.include_everything
            fetch_labels = args.include_labels or args.include_everything
            fetch_releases = args.include_releases or args.include_everything
            metadata_bundle = None
            if (
                fetch_issues
                or fetch_pulls
                or fetch_milestones
                or fetch_labels
                or fetch_releases
            ):
                logger.info("Fetching repository metadata via GraphQL")
                metadata_bundle = fetch_repository_metadata_graphql(
                    args,
                    repository,
                    {
                        "issues": fetch_issues,
                        "pulls": fetch_pulls,
                        "pull_details": args.include_pull_details,
                        "milestones": fetch_milestones,
                        "labels": fetch_labels,
                        "releases": fetch_releases,
                    },
                )

            if fetch_issues:
                issues_skipped += backup_issues(
                    args,
                    repo_cwd,
                    repository,
                    repos_template,
                    prefetched_issues=metadata_bundle.get("issues"),
                )["skipped"]

            if fetch_pulls:
                pulls_skipped += backup_pulls(
                    args,
                    repo_cwd,
                    repository,
                    repos_template,
                    prefetched_pulls=metadata_bundle.get("pulls"),
                )["skipped"]

            if fetch_milestones:
                milestones_skipped += backup_milestones(
                    args,
                    repo_cwd,
                    repository,
                    repos_template,
                    prefetched_milestones=metadata_bundle.get("milestones"),
                )["skipped"]

            if fetch_labels:
                backup_labels(
                    args,
                    repo_cwd,
                    repository,
                    repos_template,
                    prefetched_labels=metadata_bundle.get("labels"),
                )

            if args.include_hooks or args.include_everything:
                backup_hooks(args, repo_cwd, repository, repos_template)

            if fetch_releases:
                backup_releases(
                    args,
                    repo_cwd,
                    repository,
                    repos_template,
                    include_assets=args.include_assets or args.include_everything,
                    prefetched_releases=metadata_bundle.get("releases"),
                )

            # Persist repository metadata as backup data, only after a fully
            # successful pass, so repo.json marks a complete backup. Because
            # this also runs when the git fetch was skipped, metadata
            # (description, topics, ...) stays current every run.
            if git_errors:
                raise git_errors[0]
            write_repo_metadata(repo_cwd, repository)

            succeeded += 1
        except KeyboardInterrupt:
            logger.warning(
                "Interrupted by user (Ctrl-C) while processing "
                f"'{repo_full_name}'; stopping after {i - 1}/{total} "
                "repositories. Per-repository progress has been saved."
            )
            interrupted = True
            break
        except Exception as e:
            detail = format_exception(e)
            logger.error(
                f"Failed to back up repository '{repo_full_name}': {detail}",
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
            failed_repositories.append({"repository": repo_full_name, "error": detail})

    stats = {
        "installations": len(accounts),
        "accounts": sorted(accounts),
        "repositories_total": total,
        "repositories_succeeded": succeeded,
        "repositories_failed": len(failed_repositories),
        "repositories_git_skipped_unchanged": git_skipped,
        "issues_skipped_unchanged": issues_skipped,
        "pulls_skipped_unchanged": pulls_skipped,
        "milestones_skipped_unchanged": milestones_skipped,
        "git_refs_archived": git_refs_archived,
        "recovered_repositories": recovered_repositories,
        "lfs_warnings": lfs_warnings,
        "failed_repositories": failed_repositories,
        "interrupted": interrupted,
    }
    logger.info(
        f"Backup complete: {succeeded}/{total} repositories succeeded, "
        f"{len(failed_repositories)} failed, {git_skipped} git fetches skipped, "
        f"{issues_skipped} issues + {pulls_skipped} pulls skipped (unchanged)"
    )
    return stats


def backup_issues(args, repo_cwd, repository, repos_template, prefetched_issues=None):
    has_issues_dir = os.path.isdir("{0}/issues/.git".format(repo_cwd))
    if args.skip_existing and has_issues_dir:
        return {"total": 0, "skipped": 0}

    logger.info("Retrieving issues")
    issue_cwd = os.path.join(repo_cwd, "issues")
    mkdir_p(repo_cwd, issue_cwd)

    issues = {}
    issues_skipped_message = ""
    _issue_template = "{0}/{1}/issues".format(repos_template, repository["full_name"])

    if prefetched_issues is not None:
        for issue in prefetched_issues:
            issues[issue["number"]] = issue
    else:
        should_include_pulls = args.include_pulls or args.include_everything
        issues_skipped_pulls = 0
        issue_states = ["open", "closed"]
        for issue_state in issue_states:
            query_args = {"filter": "all", "state": issue_state}

            installation_id = repository.get("_installation_id")
            _issues = retrieve_data(
                args,
                _issue_template,
                installation_id,
                query_args=query_args,
            )
            for issue in _issues:
                if "pull_request" in issue and should_include_pulls:
                    issues_skipped_pulls += 1
                    continue

                issues[issue["number"]] = issue
        if issues_skipped_pulls:
            issues_skipped_message = " (skipped {0} pull requests)".format(
                issues_skipped_pulls
            )

    logger.info(
        f"Saving {len(list(issues.keys()))} issues to disk{issues_skipped_message}"
    )
    comments_template = _issue_template + "/{0}/comments"
    events_template = _issue_template + "/{0}/events"
    skipped = 0
    for number, issue in list(issues.items()):
        issue_file = "{0}/{1}.json".format(issue_cwd, number)
        # Skip the expensive per-issue comment/event fetches and the rewrite
        # when the stored copy already reflects this issue's latest update. An
        # issue's `updated_at` reliably advances on comment/label/state activity.
        if is_item_unchanged(issue_file, issue.get("updated_at"), args.force_full):
            logger.debug(f"Skipping unchanged issue #{number}")
            skipped += 1
            continue

        if args.include_issue_comments or args.include_everything:
            template = comments_template.format(number)
            installation_id = repository.get("_installation_id")
            issues[number]["comment_data"] = retrieve_data(
                args, template, installation_id
            )
        if args.include_issue_events or args.include_everything:
            template = events_template.format(number)
            installation_id = repository.get("_installation_id")
            issues[number]["event_data"] = retrieve_data(
                args, template, installation_id
            )

        with codecs.open(issue_file + ".temp", "w", encoding="utf-8") as f:
            json_dump(issue, f)
            os.rename(
                issue_file + ".temp", issue_file
            )  # Unlike json_dump, this is atomic

    if skipped:
        logger.info(f"Skipped {skipped} unchanged issues")
    return {"total": len(issues), "skipped": skipped}


def backup_pulls(args, repo_cwd, repository, repos_template, prefetched_pulls=None):
    has_pulls_dir = os.path.isdir("{0}/pulls/.git".format(repo_cwd))
    if args.skip_existing and has_pulls_dir:
        return {"total": 0, "skipped": 0}

    logger.info("Retrieving pull requests")
    pulls_cwd = os.path.join(repo_cwd, "pulls")
    mkdir_p(repo_cwd, pulls_cwd)

    pulls = {}
    _pulls_template = "{0}/{1}/pulls".format(repos_template, repository["full_name"])
    _issue_template = "{0}/{1}/issues".format(repos_template, repository["full_name"])

    if prefetched_pulls is not None:
        for pull in prefetched_pulls:
            pulls[pull["number"]] = pull
    else:
        query_args = {
            "filter": "all",
            "state": "all",
            "sort": "updated",
            "direction": "desc",
        }

        if not args.include_pull_details:
            pull_states = ["open", "closed"]
            for pull_state in pull_states:
                query_args["state"] = pull_state
                installation_id = repository.get("_installation_id")
                _pulls = retrieve_data_gen(
                    args,
                    _pulls_template,
                    installation_id,
                    query_args=query_args,
                )
                for pull in _pulls:
                    pulls[pull["number"]] = pull
        else:
            installation_id = repository.get("_installation_id")
            _pulls = retrieve_data_gen(
                args,
                _pulls_template,
                installation_id,
                query_args=query_args,
            )
            for pull in _pulls:
                installation_id = repository.get("_installation_id")
                pulls[pull["number"]] = retrieve_data(
                    args,
                    _pulls_template + "/{}".format(pull["number"]),
                    installation_id,
                    single_request=True,
                )[0]

    logger.info(f"Saving {len(list(pulls.keys()))} pull requests to disk")
    # Comments from pulls API are only _review_ comments
    # regular comments need to be fetched via issue API.
    # For backwards compatibility with versions <= 0.41.0
    # keep name "comment_data" for review comments
    comments_regular_template = _issue_template + "/{0}/comments"
    comments_template = _pulls_template + "/{0}/comments"
    commits_template = _pulls_template + "/{0}/commits"
    skipped = 0
    for number, pull in list(pulls.items()):
        pull_file = "{0}/{1}.json".format(pulls_cwd, number)
        # Skip the expensive per-PR comment/commit fetches and the rewrite when
        # the stored copy already reflects this PR's latest update.
        if is_item_unchanged(pull_file, pull.get("updated_at"), args.force_full):
            logger.debug(f"Skipping unchanged pull request #{number}")
            skipped += 1
            continue
        if args.include_pull_comments or args.include_everything:
            template = comments_regular_template.format(number)
            installation_id = repository.get("_installation_id")
            pulls[number]["comment_regular_data"] = retrieve_data(
                args, template, installation_id
            )
            template = comments_template.format(number)
            pulls[number]["comment_data"] = retrieve_data(
                args, template, installation_id
            )
        if args.include_pull_commits or args.include_everything:
            template = commits_template.format(number)
            installation_id = repository.get("_installation_id")
            pulls[number]["commit_data"] = retrieve_data(
                args, template, installation_id
            )

        with codecs.open(pull_file + ".temp", "w", encoding="utf-8") as f:
            json_dump(pull, f)
            os.rename(
                pull_file + ".temp", pull_file
            )  # Unlike json_dump, this is atomic

    if skipped:
        logger.info(f"Skipped {skipped} unchanged pull requests")
    return {"total": len(pulls), "skipped": skipped}


def backup_milestones(
    args, repo_cwd, repository, repos_template, prefetched_milestones=None
):
    milestone_cwd = os.path.join(repo_cwd, "milestones")
    if args.skip_existing and os.path.isdir(milestone_cwd):
        return {"total": 0, "skipped": 0}

    logger.info("Retrieving milestones")
    mkdir_p(repo_cwd, milestone_cwd)

    if prefetched_milestones is not None:
        _milestones = prefetched_milestones
    else:
        template = "{0}/{1}/milestones".format(repos_template, repository["full_name"])
        query_args = {"state": "all"}
        installation_id = repository.get("_installation_id")
        _milestones = retrieve_data(
            args, template, installation_id, query_args=query_args
        )

    milestones = {}
    for milestone in _milestones:
        milestones[milestone["number"]] = milestone

    logger.info(f"Saving {len(list(milestones.keys()))} milestones to disk")
    skipped = 0
    for number, milestone in list(milestones.items()):
        milestone_file = "{0}/{1}.json".format(milestone_cwd, number)
        # Milestones have no sub-resources; skip the rewrite when unchanged.
        if is_item_unchanged(
            milestone_file, milestone.get("updated_at"), args.force_full
        ):
            skipped += 1
            continue
        with codecs.open(milestone_file, "w", encoding="utf-8") as f:
            json_dump(milestone, f)

    return {"total": len(milestones), "skipped": skipped}


def backup_labels(args, repo_cwd, repository, repos_template, prefetched_labels=None):
    label_cwd = os.path.join(repo_cwd, "labels")
    output_file = "{0}/labels.json".format(label_cwd)
    template = "{0}/{1}/labels".format(repos_template, repository["full_name"])
    installation_id = repository.get("_installation_id")
    _backup_data(
        args,
        "labels",
        template,
        output_file,
        label_cwd,
        installation_id,
        prefetched=prefetched_labels,
    )


def backup_hooks(args, repo_cwd, repository, repos_template):
    installation_id = repository.get("_installation_id")
    if not installation_id:
        logger.info("Skipping hooks since no installation context available")
        return
    hook_cwd = os.path.join(repo_cwd, "hooks")
    output_file = "{0}/hooks.json".format(hook_cwd)
    template = "{0}/{1}/hooks".format(repos_template, repository["full_name"])

    # Log installation context for debugging
    account_type = repository.get("_account_type", "unknown")
    account_login = repository.get("_account_login", "unknown")
    repo_name = repository.get("full_name", "unknown")
    repo_private = repository.get("private", False)

    try:
        _backup_data(
            args,
            "hooks",
            template,
            output_file,
            hook_cwd,
            installation_id,
        )
    except Exception as e:
        if "404" in str(e):
            logger.info("Unable to read hooks, skipping")
        elif "403" in str(e):
            # Handle 403 Forbidden - this can happen for various reasons:
            # 1. Repository-specific permission restrictions
            # 2. Organization-level webhook access policies
            # 3. Repository is archived or has restricted access
            # 4. Different GitHub App installation permissions between user and org
            logger.warning(
                f"Access denied to hooks for repository '{repo_name}' (HTTP 403). "
                f"Installation: {installation_id} ({account_type}: {account_login}). "
                f"This may be due to repository-specific restrictions, organization policies, "
                f"or different GitHub App installation permissions. Skipping hooks backup for this repository."
            )
        else:
            raise e


def backup_releases(
    args,
    repo_cwd,
    repository,
    repos_template,
    include_assets=False,
    prefetched_releases=None,
):
    repository_fullname = repository["full_name"]

    # give release files somewhere to live & log intent
    release_cwd = os.path.join(repo_cwd, "releases")
    logger.info("Retrieving releases")
    mkdir_p(repo_cwd, release_cwd)

    if prefetched_releases is not None:
        releases = prefetched_releases
    else:
        release_template = "{0}/{1}/releases".format(
            repos_template, repository_fullname
        )
        installation_id = repository.get("_installation_id")
        releases = retrieve_data(args, release_template, installation_id, query_args={})

    if args.skip_prerelease:
        releases = [r for r in releases if not r["prerelease"] and not r["draft"]]

    if args.number_of_latest_releases and args.number_of_latest_releases < len(
        releases
    ):
        releases.sort(
            key=lambda item: datetime.strptime(
                item["created_at"], "%Y-%m-%dT%H:%M:%SZ"
            ),
            reverse=True,
        )
        releases = releases[: args.number_of_latest_releases]
        logger.info(f"Saving the latest {len(releases)} releases to disk")
    else:
        logger.info(f"Saving {len(releases)} releases to disk")

    # for each release, store it
    for release in releases:
        release_name = release["tag_name"]
        release_name_safe = release_name.replace("/", "__")
        output_filepath = os.path.join(
            release_cwd, "{0}.json".format(release_name_safe)
        )
        with codecs.open(output_filepath, "w+", encoding="utf-8") as f:
            json_dump(release, f)

        if include_assets:
            installation_id = repository.get("_installation_id")
            assets = release.get("assets")
            if assets is None:
                assets = retrieve_data(args, release["assets_url"], installation_id)
            if len(assets) > 0:
                # give release asset files somewhere to live & download them (not including source archives)
                release_assets_cwd = os.path.join(release_cwd, release_name_safe)
                mkdir_p(release_assets_cwd)
                for asset in assets:
                    download_file(
                        asset["url"],
                        os.path.join(release_assets_cwd, asset["name"]),
                        get_auth(args, installation_id, encode=False),
                        as_app=True,
                        fine=False,
                    )


# --- Git repository mirroring -------------------------------------------------
#
# Every repository (and wiki) is stored as a bare mirror so that a restore is a
# plain push of real branches and tags. Refs are never silently destroyed: a
# branch/tag/PR head that GitHub deleted or rewrote is preserved under
# ARCHIVE_REF_PREFIX, then the mirror matches GitHub exactly.
#
# Crash safety: before every fetch the current refs are written to a journal
# file inside the mirror. Whatever the fetch changes (`--prune` deletes refs
# even before objects are transferred) is compared against that journal and
# archived, after a successful fetch, after a failed one, and - if the process
# was killed - at the start of the next run. Automatic gc is disabled while
# the journal exists, so the objects of journaled refs are still present.
#
# Credentials never touch the disk or the process list: the installation token
# is handed to git through GIT_CONFIG_* environment variables (see
# get_git_auth_env), so the stored remote URL is a plain https:// URL.

# Explicit refspecs (instead of the `+refs/*:refs/*` of `git clone --mirror`) so
# that `--prune` can never delete the archive refs, and so that GitHub's
# synthetic `refs/pull/*/merge` commits (recomputed on every base-branch push)
# are not backed up.
ARCHIVE_REF_PREFIX = "refs/backup"
GIT_FETCH_REFSPECS = (
    "+refs/*:refs/*",
    # GitHub's synthetic merge commits, recomputed on every base-branch push.
    "^refs/pull/*/merge",
    # Keeps --prune away from the archive (refs GitHub does not have).
    f"^{ARCHIVE_REF_PREFIX}/*",
)


def _is_mirrored_ref(ref):
    """Every ref GitHub advertises is backed up, except the synthetic
    refs/pull/<n>/merge and anything under the archive prefix."""
    if not ref.startswith("refs/") or ref.startswith(ARCHIVE_REF_PREFIX + "/"):
        return False
    return not (ref.startswith("refs/pull/") and ref.endswith("/merge"))


MIGRATION_SUFFIX = ".mirror-migration"
NEW_MIRROR_SUFFIX = ".new-mirror"
REF_JOURNAL = "backup-refs-journal"
GIT_NO_AUTO_GC = ("-c", "gc.auto=0", "-c", "maintenance.auto=false")
# GIT_CONFIG_COUNT (how credentials reach git, see get_git_auth_env) needs git
# 2.31. Older git silently ignores it, so git would run unauthenticated.
MIN_GIT_VERSION = (2, 31)


class GitCommandError(Exception):
    pass


class BrokenBackupError(Exception):
    """The local backup of a repository is unusable (failed integrity check,
    unfinishable migration, not a git repository). fetch_repository moves it
    aside, never deleting it, and clones a fresh copy."""


def check_git_version():
    """Fail fast unless a git that supports everything we rely on is present."""
    try:
        output = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        raise Exception(f"git is required but could not be run: {e}") from e
    match = re.search(r"(\d+)\.(\d+)", output)
    if not match or tuple(map(int, match.groups())) < MIN_GIT_VERSION:
        raise Exception(
            f"git >= {'.'.join(map(str, MIN_GIT_VERSION))} is required, "
            f"found: {output.strip() or 'unknown'}"
        )
    return output.strip()


def _git(git_args, cwd=None, env=None, check=True, git_dir=None):
    """Run git, log its stderr at debug level and raise on failure.

    The command line never contains credentials (see get_git_auth_env), so the
    command and its output are safe to log and to put into status.json.
    surrogateescape keeps non-UTF-8 ref names byte-exact when they are passed
    back to git.

    git_dir is passed explicitly instead of being discovered from the working
    directory: that works with `safe.bareRepository=explicit`, never picks up
    a repository in a parent directory, and makes file ownership of the
    backup irrelevant (git's "dubious ownership" check does not apply).
    Hooks are always disabled: a backup never needs them, and nobody who can
    write to the backup disk can make the backup run code through them.
    """
    command = ["git", "-c", f"core.hooksPath={os.devnull}"]
    if git_dir is not None:
        command.append(f"--git-dir={git_dir}")
        cwd = cwd or git_dir
    result = subprocess.run(
        [*command, *git_args],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="surrogateescape",
    )
    for line in result.stderr.splitlines():
        if line.strip():
            logger.debug(f"git: {line}")
    if check and result.returncode != 0:
        raise GitCommandError(
            f"git {' '.join(git_args)} failed with exit code "
            f"{result.returncode}: {result.stderr.strip()}"
        )
    return result


def get_git_auth_env(args, repository):
    """Environment that authenticates git (and git-lfs) for one repository.

    The installation token is passed as an HTTP Authorization header via
    GIT_CONFIG_COUNT/KEY/VALUE (git >= 2.31), scoped to the GitHub host. It is
    therefore never written to .git/config, never visible in `ps`, and dies
    with the process. Call this right before each git operation so the token
    is fresh (see TOKEN_MIN_REMAINING).
    """
    installation_id = repository.get("_installation_id")
    if not installation_id:
        raise Exception(
            f"Repository {repository.get('full_name', 'unknown')} missing installation context"
        )
    token = get_auth(args, installation_id, encode=False, for_git_cli=False)
    basic = base64.b64encode(f"x-access-token:{token}".encode("ascii")).decode()
    key = f"http.https://{get_github_host(args)}/.extraHeader"

    env = os.environ.copy()
    count = int(env.get("GIT_CONFIG_COUNT", "0") or 0)
    for config_key, value in (
        # The empty value first resets any extraHeader inherited from system
        # or global config (git only; git-lfs ignores the reset).
        (key, ""),
        (key, f"Authorization: Basic {basic}"),
        # The header must never follow a redirect to another host; GitHub
        # needs none, the API gives current repository names.
        ("http.followRedirects", "false"),
        # Abort transfers stalled below 1 KB/s for 10 minutes.
        ("http.lowSpeedLimit", "1000"),
        ("http.lowSpeedTime", "600"),
    ):
        env[f"GIT_CONFIG_KEY_{count}"] = config_key
        env[f"GIT_CONFIG_VALUE_{count}"] = value
        count += 1
    env["GIT_CONFIG_COUNT"] = str(count)
    # Never block on an interactive credential prompt in a cron/Docker run.
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _is_git_dir(path):
    if not os.path.isdir(path):
        return False
    result = _git(["rev-parse", "--absolute-git-dir"], git_dir=path, check=False)
    if result.returncode != 0:
        if "not a git repository" in result.stderr:
            return False
        # E.g. a repository format written by a newer git: not ours to judge
        # as broken, so fail loudly instead.
        raise GitCommandError(
            f"Cannot use {path}: git rev-parse failed with exit code "
            f"{result.returncode}: {result.stderr.strip()}"
        )
    return os.path.realpath(result.stdout.strip()) == os.path.realpath(path)


def _list_refs(git_dir, *patterns):
    """Map refname -> (object id, object type)."""
    output = _git(
        [
            "for-each-ref",
            "--format=%(objectname) %(objecttype) %(refname)",
            *patterns,
        ],
        git_dir=git_dir,
    ).stdout
    refs = {}
    for line in output.splitlines():
        sha, kind, name = line.split(" ", 2)
        refs[name] = (sha, kind)
    return refs


def _list_mirrored_refs(git_dir):
    return {
        name: value
        for name, value in _list_refs(git_dir).items()
        if _is_mirrored_ref(name)
    }


def _is_ancestor(git_dir, old, new):
    result = _git(
        ["merge-base", "--is-ancestor", old, new], git_dir=git_dir, check=False
    )
    return result.returncode == 0


def _archive_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _archive_ref(git_dir, label, ref, sha, reason):
    """Create ARCHIVE_REF_PREFIX/<label>/<ref> pointing at sha.

    Never overwrites: if the name is taken (two runs in the same second, a
    directory/file conflict between ref names) a suffix is added to the label.
    """
    for attempt in range(100):
        suffix = f"-{attempt}" if attempt else ""
        name = f"{ARCHIVE_REF_PREFIX}/{label}{suffix}/{ref}"
        # An empty old value makes update-ref fail if the ref already exists.
        if _git(["update-ref", name, sha, ""], git_dir=git_dir, check=False).returncode:
            existing = _git(
                ["rev-parse", "--verify", "--quiet", name], git_dir=git_dir, check=False
            ).stdout.strip()
            if existing == sha:
                return name
            continue
        logger.info(f"Archived {reason} as {name} ({sha[:12]})")
        return name
    raise GitCommandError(f"Could not create an archive ref for {ref} ({sha})")


def _must_archive(git_dir, ref, old, new):
    """Whether replacing old by new (each (sha, type) or None) loses data."""
    if new == old:
        return False
    if new is None or ref.startswith("refs/tags/"):
        # Deleted, or any change to a tag (message, signature, target).
        return True
    return not (
        old[1] == "commit"
        and new[1] == "commit"
        and _is_ancestor(git_dir, old[0], new[0])
    )


def _write_journal(git_dir, refs):
    path = os.path.join(git_dir, REF_JOURNAL)
    with open(
        path + ".tmp", "w", encoding="utf-8", errors="surrogateescape"
    ) as journal:
        for name, (sha, kind) in sorted(refs.items()):
            journal.write(f"{sha} {kind} {name}\n")
        journal.flush()
        os.fsync(journal.fileno())
    os.replace(path + ".tmp", path)


def _settle_journal(git_dir, name):
    """Archive every ref that changed since the journaled snapshot in a way
    that loses data, then drop the journal. Returns the number archived."""
    path = os.path.join(git_dir, REF_JOURNAL)
    if not os.path.exists(path):
        return 0
    before = {}
    with open(path, encoding="utf-8", errors="surrogateescape") as journal:
        for line in journal.read().splitlines():
            sha, kind, ref = line.split(" ", 2)
            before[ref] = (sha, kind)
    after = _list_mirrored_refs(git_dir)
    label = _archive_timestamp()
    archived = 0
    for ref, old in before.items():
        new = after.get(ref)
        if new == old:
            continue
        change = "deleted" if new is None else "rewritten"
        if _git(["cat-file", "-e", old[0]], git_dir=git_dir, check=False).returncode:
            # Never let an unrecoverable entry block all future backups.
            logger.error(
                f"Cannot archive {change} {ref} of {name}: object {old[0]} is no "
                "longer in the mirror (garbage collected outside this tool?)"
            )
            continue
        if _must_archive(git_dir, ref, old, new):
            _archive_ref(git_dir, label, ref, old[0], f"{change} {ref} of {name}")
            archived += 1
    os.remove(path)
    return archived


# commit-graph is a pure cache. Old versions let `git gc` delete unreferenced
# commits without rewriting it, so it can list commits that no longer exist,
# which makes fsck fail although no data is missing.
GIT_FSCK_OPTIONS = ("-c", "core.commitGraph=false")


def _drop_commit_graph(git_dir):
    """Remove the (regenerable) commit-graph cache of a repository."""
    info = os.path.join(git_dir, "objects", "info")
    graph = os.path.join(info, "commit-graph")
    if os.path.exists(graph):
        os.remove(graph)
    if os.path.isdir(os.path.join(info, "commit-graphs")):
        shutil.rmtree(os.path.join(info, "commit-graphs"))


# A backup is only moved aside on positive evidence of missing or corrupt
# data. Anything else (permissions, an unknown repository format from a newer
# git, a killed process) fails the repository and leaves the backup alone.
FSCK_CORRUPTION_MARKERS = (
    "missing ",
    "broken link",
    "corrupt",
    "bad object",
    "too short",
    "unable to read",
    "invalid sha1 pointer",
    "hash mismatch",
    "error in packfile",
)
FSCK_ENVIRONMENT_MARKERS = (
    "permission denied",
    "repository extension",
    "repository format",
    "not a git repository",
    "out of memory",
    "cannot allocate",
)


def _fsck(git_dir, what):
    """Check repository integrity; return fsck's stdout (incl. "dangling ..."
    lines, judged without reflogs). Raises BrokenBackupError only on positive
    evidence of missing or corrupt data, GitCommandError on other failures."""
    _drop_commit_graph(git_dir)
    fsck = _git(
        [
            *GIT_FSCK_OPTIONS,
            "fsck",
            "--connectivity-only",
            "--no-reflogs",
            "--dangling",
            "--no-progress",
        ],
        git_dir=git_dir,
        check=False,
    )
    if fsck.returncode == 0:
        return fsck.stdout
    # Dangling objects are expected; report only the real problems.
    problems = [
        line.strip()
        for line in fsck.stderr.splitlines()
        + [x for x in fsck.stdout.splitlines() if not x.startswith("dangling ")]
        if line.strip()
    ]
    detail = "; ".join(problems)[:1000]
    text = detail.lower()
    if (
        fsck.returncode > 0
        and not any(marker in text for marker in FSCK_ENVIRONMENT_MARKERS)
        and any(marker in text for marker in FSCK_CORRUPTION_MARKERS)
    ):
        raise BrokenBackupError(
            f"git fsck of {what} found missing or corrupt data, it was left "
            f"untouched: {detail}"
        )
    raise GitCommandError(
        f"git fsck of {what} failed (exit code {fsck.returncode}), it was left "
        f"untouched: {detail}"
    )


def _rescue_unreferenced(git_dir, label, what):
    """Archive commits and tags no ref points to any more (only reflogs or
    nothing), after checking repository integrity (see _fsck)."""
    unreferenced = []
    for line in _fsck(git_dir, what).splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0] == "dangling" and parts[1] in ("commit", "tag"):
            unreferenced.append((parts[1], parts[2]))
    return lambda target: [
        _archive_ref(target, label, sha, sha, f"unreferenced {kind} of {what}")
        for kind, sha in unreferenced
    ]


def _migrate_working_clone_to_mirror(local_dir):
    """Convert a legacy non-bare clone (`repository/.git` + checkout) in place.

    No objects are copied: the .git directory becomes the bare mirror. The
    remote-tracking branches become real branches. Every commit or tag that is
    not referenced by a ref (force-pushed-away tips that only the reflogs
    remember, branches an earlier --prune deleted) is archived. Each step is
    idempotent, so an interrupted migration resumes on the next run.
    """
    tmp_dir = local_dir + MIGRATION_SUFFIX
    dot_git = os.path.join(local_dir, ".git")
    if os.path.isdir(dot_git) and os.path.exists(tmp_dir):
        raise BrokenBackupError(
            f"Cannot migrate {local_dir}: both {dot_git} and {tmp_dir} exist; "
            "left untouched, please resolve manually"
        )
    old_git_dir = dot_git if os.path.isdir(dot_git) else tmp_dir
    stamp = _archive_timestamp()

    # A pointer, not data, and removed with the remote below anyway. After a
    # default-branch rename upstream it dangles, which fsck reports.
    _git(
        ["symbolic-ref", "--delete", "refs/remotes/origin/HEAD"],
        git_dir=old_git_dir,
        check=False,
    )
    # Checks integrity before anything else is modified.
    archive_unreferenced = _rescue_unreferenced(
        old_git_dir, f"{stamp}-migration-unreferenced", local_dir
    )

    if old_git_dir == dot_git:
        logger.info(f"Migrating {local_dir} to a bare mirror")
        os.rename(dot_git, tmp_dir)

    _git(["config", "core.bare", "true"], git_dir=tmp_dir)
    _git(["config", "--unset", "core.worktree"], git_dir=tmp_dir, check=False)
    index = os.path.join(tmp_dir, "index")
    if os.path.exists(index):
        os.remove(index)

    archive_unreferenced(tmp_dir)

    remote_prefix = "refs/remotes/origin/"
    remote_refs = {
        name[len(remote_prefix) :]: sha
        for name, (sha, _) in _list_refs(tmp_dir, "refs/remotes/origin").items()
        if name != remote_prefix + "HEAD"
    }

    if remote_refs:
        # Local branches only ever held the initial checkout; keep any that
        # are not contained in the upstream branch of the same name.
        for name, (sha, _) in _list_refs(tmp_dir, "refs/heads").items():
            branch = name[len("refs/heads/") :]
            upstream = remote_refs.get(branch)
            if upstream is None or (
                upstream != sha and not _is_ancestor(tmp_dir, sha, upstream)
            ):
                _archive_ref(
                    tmp_dir,
                    f"{stamp}-migration",
                    name,
                    sha,
                    f"stale local branch {branch}",
                )
                if upstream is None:
                    _git(["update-ref", "-d", name], git_dir=tmp_dir)

        for branch, sha in remote_refs.items():
            _git(["update-ref", f"refs/heads/{branch}", sha], git_dir=tmp_dir)

    # Verify before anything is removed: every upstream branch must now be a
    # real branch at the same commit.
    heads = _list_refs(tmp_dir, "refs/heads")
    missing = [
        branch
        for branch, sha in remote_refs.items()
        if heads.get(f"refs/heads/{branch}", (None,))[0] != sha
    ]
    if missing or not _is_git_dir(tmp_dir):
        raise BrokenBackupError(
            f"Migration of {local_dir} could not be verified (missing branches: "
            f"{missing}); nothing was deleted, state kept in {tmp_dir}"
        )

    # Drops refs/remotes/origin/* and the old remote config (incl. any
    # token-bearing URL); _configure_mirror re-adds a clean one.
    _git(["remote", "remove", "origin"], git_dir=tmp_dir, check=False)

    if os.path.exists(local_dir):
        if os.path.exists(os.path.join(local_dir, ".git")):
            raise BrokenBackupError(f"Refusing to delete {local_dir}: it contains .git")
        # Only the checked-out working tree is left; its content is in git.
        shutil.rmtree(local_dir)
    os.rename(tmp_dir, local_dir)
    logger.info(f"Migrated {local_dir} to a bare mirror")


def _configure_mirror(git_dir, remote_url):
    config = _git(
        ["config", "--get-regexp", r"^remote\.origin\."], git_dir=git_dir, check=False
    )
    current = {}
    for line in config.stdout.splitlines():
        key, _, value = line.partition(" ")
        current.setdefault(key, []).append(value)
    if current.get("remote.origin.url") != [remote_url]:
        # Also replaces legacy URLs that embedded an access token.
        _git(
            ["config", "--replace-all", "remote.origin.url", remote_url],
            git_dir=git_dir,
        )
    if "remote.origin.mirror" in current:
        # A `git clone --mirror` from the old --bare mode: rescue commits an
        # earlier --prune left unreferenced, then drop the mirror settings.
        logger.info(f"Converting old --bare mirror {git_dir}")
        _rescue_unreferenced(
            git_dir, f"{_archive_timestamp()}-migration-unreferenced", git_dir
        )(git_dir)
        _git(["config", "--unset-all", "remote.origin.mirror"], git_dir=git_dir)
        # Its refspec also fetched GitHub's synthetic merge refs.
        for name in _list_refs(git_dir, "refs/pull"):
            if name.endswith("/merge"):
                _git(["update-ref", "-d", name], git_dir=git_dir)
    if current.get("remote.origin.fetch") != list(GIT_FETCH_REFSPECS):
        _git(
            ["config", "--unset-all", "remote.origin.fetch"],
            git_dir=git_dir,
            check=False,
        )
        for refspec in GIT_FETCH_REFSPECS:
            _git(["config", "--add", "remote.origin.fetch", refspec], git_dir=git_dir)


class RunLockedError(Exception):
    pass


def acquire_run_lock(output_directory):
    """Hold an exclusive lock on the backup directory for this process'
    lifetime, so overlapping runs (e.g. cron) never work on the same mirrors
    or journals. Returns the open lock file; keep a reference to it."""
    import fcntl

    handle = open(os.path.join(output_directory, ".github-backup.lock"), "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise RunLockedError(
            f"Another github-backup run is using {output_directory}; not starting"
        )
    return handle


def _has_backup(local_dir):
    return os.path.exists(local_dir) or os.path.exists(local_dir + MIGRATION_SUFFIX)


def ensure_mirror_repository(local_dir, remote_url):
    """Bring an existing backup at local_dir into the current mirror layout
    without network access: migrates legacy clones and scrubs token-bearing
    remote URLs. Creates nothing.

    Returns True if local_dir is a mirror afterwards.
    """
    if os.path.isdir(os.path.join(local_dir, ".git")) or os.path.isdir(
        local_dir + MIGRATION_SUFFIX
    ):
        _migrate_working_clone_to_mirror(local_dir)
    if not _is_git_dir(local_dir):
        return False
    _configure_mirror(local_dir, remote_url)
    return True


def _remote_missing(stderr):
    stderr = stderr.lower()
    return "not found" in stderr or "does not appear to be a git repository" in stderr


def _parse_ls_remote(output):
    """Return (default branch ref or None, {mirrored refname: object id},
    [refs on GitHub this backup does not cover])."""
    default_ref = None
    remote = {}
    not_covered = []
    for line in output.splitlines():
        if line.startswith("ref: ") and line.endswith("\tHEAD"):
            default_ref = line[len("ref: ") : -len("\tHEAD")]
            continue
        sha, _, ref = line.partition("\t")
        if ref == "HEAD" or ref.endswith("^{}"):
            continue
        if ref.startswith("refs/pull/") and ref.endswith("/merge"):
            continue  # GitHub's synthetic merge commits, deliberately skipped
        if not _is_mirrored_ref(ref):
            not_covered.append(ref)  # would collide with our archive
            continue
        remote[ref] = sha
    return default_ref, remote, not_covered


FetchResult = namedtuple(
    "FetchResult", "archived skipped recovered lfs_error", defaults=(None, None)
)
LFS_INCOMPLETE = "backup-lfs-incomplete"


def _env(git_env):
    """git_env may be a callable, so long runs get a fresh token per step."""
    return git_env() if callable(git_env) else git_env


BROKEN_SUFFIX = ".broken-"


def _quarantine(local_dir):
    """Move an unusable backup (and any half-done migration) aside. Never
    deletes anything; returns the new location."""
    dest = f"{local_dir}{BROKEN_SUFFIX}{_archive_timestamp()}"
    base, n = dest, 0
    while os.path.exists(dest) or os.path.exists(dest + MIGRATION_SUFFIX):
        n += 1
        dest = f"{base}-{n}"
    if os.path.exists(local_dir):
        os.rename(local_dir, dest)
    if os.path.exists(local_dir + MIGRATION_SUFFIX):
        os.rename(local_dir + MIGRATION_SUFFIX, dest + MIGRATION_SUFFIX)
    return dest


def fetch_repository(name, remote_url, local_dir, git_env, **kwargs):
    """Create or update the bare mirror of one repository (see
    _fetch_repository). If the local backup turns out to be unusable, it is
    moved aside - never deleted - and a fresh copy is cloned; the returned
    FetchResult then carries `recovered`.

    Remote problems (network, authentication, GitHub) are never treated as
    a broken backup: they are detected before the local backup is touched.
    """
    try:
        return _fetch_repository(name, remote_url, local_dir, git_env, **kwargs)
    except BrokenBackupError as e:
        moved_to = _quarantine(local_dir)
        logger.warning(
            f"Backup of {name} in {local_dir} is unusable ({e}). Moved it to "
            f"{moved_to} (kept for inspection, delete when no longer needed) "
            "and cloning a fresh copy."
        )
        try:
            result = _fetch_repository(name, remote_url, local_dir, git_env, **kwargs)
        except Exception as clone_error:
            raise GitCommandError(
                f"Backup of {name} was unusable ({e}) and was moved to {moved_to}; "
                f"cloning a fresh copy failed: {clone_error}"
            ) from clone_error
        return result._replace(recovered={"moved_to": moved_to, "reason": str(e)})


def _fetch_repository(
    name,
    remote_url,
    local_dir,
    git_env,
    skip_existing=False,
    lfs_clone=False,
    optional=False,
    force=False,
):
    """Create or update the bare mirror of one repository.

    Change detection: one `git ls-remote` lists every ref on GitHub; if they
    all equal the mirror's refs, the (expensive) fetch is skipped. Unlike the
    repository's `pushed_at`, this also sees pull request heads updated from
    forks. force=True always fetches.

    Returns FetchResult(archived=<refs archived because GitHub deleted or
    rewrote them>, skipped=<fetch was not needed>). With optional=True
    (wikis), a remote that does not exist is skipped as long as we hold no
    backup of it; every other git failure raises, so the caller does not
    record the repository as backed up.
    """
    if skip_existing and _has_backup(local_dir):
        ensure_mirror_repository(local_dir, remote_url)
        return FetchResult(0, True)

    listing = _git(
        ["ls-remote", "--symref", remote_url], env=_env(git_env), check=False
    )
    if listing.returncode != 0:
        if optional and not _has_backup(local_dir) and _remote_missing(listing.stderr):
            logger.debug(f"Skipping {name} (remote does not exist)")
            return FetchResult(0, True)
        raise GitCommandError(
            f"git ls-remote {remote_url} failed with exit code "
            f"{listing.returncode}: {listing.stderr.strip()}"
        )
    default_ref, remote_refs, not_covered = _parse_ls_remote(listing.stdout)
    if not_covered:
        logger.warning(
            f"{name} has {len(not_covered)} ref(s) under {ARCHIVE_REF_PREFIX}/ on "
            "GitHub, which this backup uses for its own archive; they are not "
            f"backed up, e.g. {', '.join(not_covered[:5])}"
        )

    try:
        return _update_mirror(
            name,
            remote_url,
            local_dir,
            git_env,
            default_ref,
            remote_refs,
            lfs_clone,
            force,
        )
    except GitCommandError as e:
        # GitHub answered ls-remote moments ago, so a git failure on an
        # existing backup that also fails its integrity check is local.
        git_dir = (
            local_dir if _is_git_dir(local_dir) else os.path.join(local_dir, ".git")
        )
        if os.path.isdir(git_dir):
            try:
                _fsck(git_dir, local_dir)
            except BrokenBackupError as broken:
                raise BrokenBackupError(f"{broken} (after: {e})") from e
            except GitCommandError:
                pass  # no evidence of damage: report the original failure
        raise


def _update_mirror(
    name, remote_url, local_dir, git_env, default_ref, remote_refs, lfs_clone, force
):
    existed = ensure_mirror_repository(local_dir, remote_url)
    if existed:
        target = local_dir
    else:
        if os.path.exists(local_dir) and os.listdir(local_dir):
            raise BrokenBackupError(f"{local_dir} exists but is not a git repository")
        # Build a new mirror next to its final place and move it there only
        # once the first fetch succeeded, so a failed or killed first fetch
        # never leaves an empty "backup" behind.
        target = local_dir + NEW_MIRROR_SUFFIX
        if os.path.exists(target):
            shutil.rmtree(target)
        _git(["init", "--quiet", "--bare", target])
        _configure_mirror(target, remote_url)

    # Finish archiving for a run that was killed during or after its fetch.
    archived = _settle_journal(target, name)

    local_refs = {ref: sha for ref, (sha, _) in _list_mirrored_refs(target).items()}
    skipped = existed and not force and local_refs == remote_refs
    if skipped:
        logger.info(f"{name} unchanged on GitHub; skipping git fetch")
    else:
        logger.info(
            f"{'Updating' if existed else 'Cloning'} {name} mirror from "
            f"{remote_url} in {local_dir}"
        )
        _write_journal(target, _list_mirrored_refs(target))
        fetch_error = None
        try:
            _git(
                [*GIT_NO_AUTO_GC, "fetch", "--quiet", "--force", "--prune", "origin"],
                git_dir=target,
                env=_env(git_env),
            )
        except GitCommandError as e:
            fetch_error = e
        # Also after a failed fetch: --prune deletes refs before transferring
        # objects. (If the process is killed, the next run settles.)
        try:
            archived += _settle_journal(target, name)
        except Exception as settle_error:
            if fetch_error is None:
                raise
            logger.error(f"Archiving refs of {name} failed: {settle_error}")
        if fetch_error is not None:
            raise fetch_error
        # Pack loose objects now and then. Safe: everything worth keeping is
        # reachable from a ref, including the archive.
        _git(["-c", "gc.autoDetach=false", "gc", "--auto", "--quiet"], git_dir=target)

    # Point HEAD at the remote default branch so a clone of the mirror checks
    # out the right branch (the default branch can change without a push).
    if default_ref and default_ref in remote_refs:
        current = _git(["symbolic-ref", "-q", "HEAD"], git_dir=target, check=False)
        if current.stdout.strip() != default_ref:
            _git(["symbolic-ref", "HEAD", default_ref], git_dir=target)

    if not existed:
        if os.path.exists(local_dir):
            os.rmdir(local_dir)  # checked to be empty above
        os.rename(target, local_dir)

    lfs_error = None
    marker = os.path.join(local_dir, LFS_INCOMPLETE)
    if lfs_clone and (not skipped or os.path.exists(marker)):
        # Also when the git fetch was skipped but an earlier LFS download
        # failed (it only fetches what is missing). No --prune: pruning LFS
        # objects of old commits defeats a backup. --all covers every ref,
        # including the archive refs. LFS objects GitHub no longer has would
        # fail the repository on every run, so failures are reported as a
        # warning; the git backup itself is complete.
        lfs = _git(
            ["lfs", "fetch", "--all", "origin"],
            git_dir=local_dir,
            env=_env(git_env),
            check=False,
        )
        if lfs.returncode:
            lfs_error = lfs.stderr.strip()[-1000:] or f"exit code {lfs.returncode}"
            with open(marker, "w") as f:
                f.write(lfs_error + "\n")
            logger.warning(f"LFS download of {name} incomplete: {lfs_error}")
        elif os.path.exists(marker):
            os.remove(marker)

    return FetchResult(archived, skipped, lfs_error=lfs_error)


def backup_account(args, output_directory):
    account_cwd = os.path.join(output_directory, "account")


def _backup_data(
    args,
    name,
    template,
    output_file,
    output_directory,
    installation_id,
    prefetched=None,
):
    skip_existing = args.skip_existing
    if not skip_existing or not os.path.exists(output_file):
        if prefetched is not None:
            logger.info(f"Writing {len(prefetched)} {name} to disk")
            mkdir_p(output_directory)
            with codecs.open(output_file, "w", encoding="utf-8") as f:
                json_dump(prefetched, f)
            return

        logger.info(f"Retrieving {name}")
        mkdir_p(output_directory)
        data = retrieve_data(args, template, installation_id)

        logger.info(f"Writing {len(data)} {name} to disk")
        with codecs.open(output_file, "w", encoding="utf-8") as f:
            json_dump(data, f)


def json_dump(data, output_file):
    json.dump(
        data,
        output_file,
        ensure_ascii=False,
        sort_keys=True,
        indent=4,
        separators=(",", ": "),
    )
