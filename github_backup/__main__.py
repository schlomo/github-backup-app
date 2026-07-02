#!/usr/bin/env python

import logging
import os
import sys
from datetime import datetime, timezone

from github_backup.github_backup import (
    backup_repositories,
    check_git_lfs_install,
    close_github_http_session,
    collect_backup_plan,
    filter_repositories,
    format_exception,
    get_github_api_host,
    log_runtime_environment,
    logger,
    mkdir_p,
    parse_args,
    retrieve_repositories,
    validate_args,
    write_status_file,
)

# Set up logging with DEBUG level initially to capture all messages
logging.basicConfig(
    format="%(asctime)s.%(msecs)03d: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.DEBUG,
)


def main():
    args = parse_args()

    # Set logging level based on arguments
    if args.quiet:
        logger.setLevel(logging.WARNING)
        logger.root.setLevel(logging.WARNING)
    elif args.log_level:
        log_level = logging.getLevelName(args.log_level.upper())
        if isinstance(log_level, int):
            logger.setLevel(log_level)
            logger.root.setLevel(log_level)
    else:
        # Default to INFO level
        logger.setLevel(logging.INFO)
        logger.root.setLevel(logging.INFO)

    log_runtime_environment()

    started_at = datetime.now(timezone.utc)
    output_directory = None

    try:
        validate_args(args)

        output_directory = os.path.realpath(args.output_directory)
        if not os.path.isdir(output_directory):
            logger.info("Creating output directory {0}".format(output_directory))
            mkdir_p(output_directory)

        if args.lfs_clone:
            check_git_lfs_install()

        # GitHub App mode is now mandatory
        if args.dry_run:
            # Collect backup plan without actually backing up
            backup_plan = collect_backup_plan(args)

            print("\n" + "=" * 80)
            print("BACKUP PLAN (DRY RUN)")
            print("=" * 80)

            total_repos = 0
            for installation in backup_plan:
                counts = installation["counts"]
                total_repos += counts["total"]

                print(
                    f"\n📁 {installation['account_type']}: {installation['account_login']}"
                )
                print(f"   Installation ID: {installation['installation_id']}")
                print(f"   Repositories: {counts['repositories']}")

                # List the actual repositories
                repos_list = installation["repositories"]
                if repos_list:
                    print("   📋 Repositories to backup:")
                    for repo in repos_list:
                        repo_name = repo.get("name", "unknown")
                        repo_private = "🔒" if repo.get("private") else "🌐"
                        repo_lang = repo.get("language", "No language")
                        print(f"      {repo_private} {repo_name} ({repo_lang})")
                else:
                    print("   📋 No repositories to backup")

            print(f"\n📊 SUMMARY:")
            print(f"   Total installations: {len(backup_plan)}")
            print(f"   Total repositories: {total_repos}")

            print(f"\n📂 Directory structure:")
            print(f"   {output_directory}/{{owner}}/repositories/{{repo_name}}")

            print("\n" + "=" * 80)
            return

        # Regular backup mode
        repositories = retrieve_repositories(args, None)

        # Starred repositories are now handled per installation during auto-discovery

        # Gists are now handled per installation during auto-discovery

        # Starred gists are now handled per installation during auto-discovery

        repositories = filter_repositories(args, repositories)
        stats = backup_repositories(args, output_directory, repositories)

        if stats.get("interrupted"):
            write_status_file(output_directory, "interrupted", started_at, stats=stats)
            logger.warning("Backup interrupted by user; partial progress saved.")
            sys.exit(130)

        # A run is "partial" when some repositories failed but the run itself
        # completed; this distinction is useful for monitoring/alerting.
        status = "partial" if stats.get("repositories_failed") else "success"
        write_status_file(output_directory, status, started_at, stats=stats)

        if status == "partial":
            logger.warning(
                "Backup finished with errors: "
                f"{stats['repositories_failed']} repository(ies) failed. "
                "See the status file and logs above for details."
            )
            sys.exit(2)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user (Ctrl-C). Aborting.")
        _write_failure_status(
            output_directory,
            started_at,
            KeyboardInterrupt("Interrupted by user"),
            status="interrupted",
        )
        sys.exit(130)
    except TypeError as e:
        if "not supported between instances of 'NoneType' and 'str'" in str(e):
            logger.error(
                f"TypeError: {str(e)}\n"
                f"This error typically occurs when GitHub API returns None values for timestamp fields "
                f"(like 'updated_at' or 'pushed_at') that the backup tool tries to compare with strings.\n"
                f"This can happen with certain repository types or when GitHub API has incomplete data.\n"
                f"Please check the logs above for more specific information about which repository or item caused this issue.",
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
        else:
            logger.error(
                f"TypeError: {str(e)}",
                exc_info=logger.isEnabledFor(logging.DEBUG),
            )
        _write_failure_status(output_directory, started_at, e)
        sys.exit(1)
    except Exception as e:
        logger.error(format_exception(e), exc_info=logger.isEnabledFor(logging.DEBUG))
        _write_failure_status(output_directory, started_at, e)
        sys.exit(1)
    finally:
        close_github_http_session()


def _write_failure_status(output_directory, started_at, exc, status="failed"):
    """Record a failed/interrupted run in the status file (best effort).

    Only possible once the output directory exists; failures before that point
    (e.g. invalid arguments) cannot produce a status file.
    """
    if not output_directory or not os.path.isdir(output_directory):
        return
    write_status_file(
        output_directory,
        status,
        started_at,
        error={"type": type(exc).__name__, "message": format_exception(exc)},
    )


if __name__ == "__main__":
    main()
