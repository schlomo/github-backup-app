=============
github-backup
=============

|PyPI| |Python Versions|

The package can be used to backup an *entire* `Github <https://github.com/>`_ organization, repository or user account, including starred repos, issues and wikis in the most appropriate format (clones for wikis, json files for issues).

Requirements
============

- GIT 1.9+
- Python

Installation
============

Using PIP via PyPI::

    pip install github-backup

Using PIP via Github (more likely the latest version)::

    pip install git+https://github.com/josegonzalez/python-github-backup.git#egg=github-backup
    
*Install note for python newcomers:*

Python scripts are unlikely to be included in your ``$PATH`` by default, this means it cannot be run directly in terminal with ``$ github-backup ...``, you can either add python's install path to your environments ``$PATH`` or call the script directly e.g. using ``$ ~/.local/bin/github-backup``.*

Basic Help
==========

Show the CLI help output::

    github-backup -h

CLI Help output::

    github-backup [-h] [-u USERNAME] [-p PASSWORD] [-t TOKEN_CLASSIC]
                  [-f TOKEN_FINE] [--as-app] [-o OUTPUT_DIRECTORY]
                  [-l LOG_LEVEL] [-i] [--starred] [--all-starred]
                  [--watched] [--followers] [--following] [--all] [--issues]
                  [--issue-comments] [--issue-events] [--pulls]
                  [--pull-comments] [--pull-commits] [--pull-details]
                  [--labels] [--hooks] [--milestones] [--repositories]
                  [--bare] [--lfs] [--wikis] [--gists] [--starred-gists]
                  [--skip-archived] [--skip-existing] [-L [LANGUAGES ...]]
                  [-N NAME_REGEX] [-H GITHUB_HOST] [-O] [-R REPOSITORY]
                  [-P] [-F] [--prefer-ssh] [-v]
                  [--keychain-name OSX_KEYCHAIN_ITEM_NAME]
                  [--keychain-account OSX_KEYCHAIN_ITEM_ACCOUNT]
                  [--releases] [--latest-releases NUMBER_OF_LATEST_RELEASES]
                  [--skip-prerelease] [--assets]
                  [--exclude [REPOSITORY [REPOSITORY ...]]
                  [--throttle-limit THROTTLE_LIMIT] [--throttle-pause THROTTLE_PAUSE]
                  USER

    Backup a github account

    positional arguments:
      USER                  github username

    optional arguments:
      -h, --help            show this help message and exit
      -u USERNAME, --username USERNAME
                            username for basic auth
      -p PASSWORD, --password PASSWORD
                            password for basic auth. If a username is given but
                            not a password, the password will be prompted for.
      -f TOKEN_FINE, --token-fine TOKEN_FINE
                            fine-grained personal access token or path to token
                            (file://...)
      -t TOKEN_CLASSIC, --token TOKEN_CLASSIC
                            personal access, OAuth, or JSON Web token, or path to
                            token (file://...)
      --as-app              authenticate as github app instead of as a user.
      -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                            directory at which to backup the repositories
      -l LOG_LEVEL, --log-level LOG_LEVEL
                            log level to use (default: info, possible levels:
                            debug, info, warning, error, critical)
      -i, --incremental     incremental backup
      --incremental-by-files incremental backup using modified time of files
      --starred             include JSON output of starred repositories in backup
      --all-starred         include starred repositories in backup [*]
      --watched             include JSON output of watched repositories in backup
      --followers           include JSON output of followers in backup
      --following           include JSON output of following users in backup
      --all                 include everything in backup (not including [*])
      --issues              include issues in backup
      --issue-comments      include issue comments in backup
      --issue-events        include issue events in backup
      --pulls               include pull requests in backup
      --pull-comments       include pull request review comments in backup
      --pull-commits        include pull request commits in backup
      --pull-details        include more pull request details in backup [*]
      --labels              include labels in backup
      --hooks               include hooks in backup (works only when
                            authenticated)
      --milestones          include milestones in backup
      --repositories        include repository clone in backup
      --bare                clone bare repositories
      --lfs                 clone LFS repositories (requires Git LFS to be
                            installed, https://git-lfs.github.com) [*]
      --wikis               include wiki clone in backup
      --gists               include gists in backup [*]
      --starred-gists       include starred gists in backup [*]
      --skip-existing       skip project if a backup directory exists
      -L [LANGUAGES [LANGUAGES ...]], --languages [LANGUAGES [LANGUAGES ...]]
                            only allow these languages
      -N NAME_REGEX, --name-regex NAME_REGEX
                            python regex to match names against
      -H GITHUB_HOST, --github-host GITHUB_HOST
                            GitHub Enterprise hostname
      -O, --organization    whether or not this is an organization user
      -R REPOSITORY, --repository REPOSITORY
                            name of repository to limit backup to
      -P, --private         include private repositories [*]
      -F, --fork            include forked repositories [*]
      --prefer-ssh          Clone repositories using SSH instead of HTTPS
      -v, --version         show program's version number and exit
      --keychain-name OSX_KEYCHAIN_ITEM_NAME
                            OSX ONLY: name field of password item in OSX keychain
                            that holds the personal access or OAuth token
      --keychain-account OSX_KEYCHAIN_ITEM_ACCOUNT
                            OSX ONLY: account field of password item in OSX
                            keychain that holds the personal access or OAuth token
      --releases            include release information, not including assets or
                            binaries
      --latest-releases NUMBER_OF_LATEST_RELEASES
                            include certain number of the latest releases;
                            only applies if including releases
      --skip-prerelease     skip prerelease and draft versions; only applies if including releases
      --assets              include assets alongside release information; only
                            applies if including releases
      --exclude [REPOSITORY [REPOSITORY ...]]
                            names of repositories to exclude from backup.
      --throttle-limit THROTTLE_LIMIT
                            start throttling of GitHub API requests after this
                            amount of API requests remain
      --throttle-pause THROTTLE_PAUSE
                            wait this amount of seconds when API request
                            throttling is active (default: 30.0, requires
                            --throttle-limit to be set)


Usage Details
=============

Authentication
--------------

**Password-based authentication** will fail if you have two-factor authentication enabled, and will `be deprecated <https://github.blog/2023-03-09-raising-the-bar-for-software-security-github-2fa-begins-march-13/>`_ by 2023 EOY.

``--username`` is used for basic password authentication and separate from the positional argument ``USER``, which specifies the user account you wish to back up.

**Classic tokens** are `slightly less secure <https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#personal-access-tokens-classic>`_ as they provide very coarse-grained permissions.

If you need authentication for long-running backups (e.g. for a cron job) it is recommended to use **fine-grained personal access token** ``-f TOKEN_FINE``.


Fine Tokens
~~~~~~~~~~~

You can "generate new token", choosing the repository scope by selecting specific repos or all repos. On Github this is under *Settings -> Developer Settings -> Personal access tokens -> Fine-grained Tokens*

Customise the permissions for your use case, but for a personal account full backup you'll need to enable the following permissions:

**User permissions**: Read access to followers, starring, and watching.

**Repository permissions**: Read access to contents, issues, metadata, pull requests, and webhooks.



GitHub App Authentication
~~~~~~~~~~~~~~~~~~~~~~~~~~

For backing up entire organizations, **GitHub App authentication** (``--as-app``) is the recommended approach as it provides:

* **Higher rate limits**: 5000 requests/hour per installation vs standard personal token limits
* **Broader access**: Organization-wide repository access when installed with "All repositories"  
* **Enterprise-friendly**: Proper app-based authentication for organizational backup scenarios
* **Automated token management**: No need to manually handle token expiry during long backups

Creating a GitHub App for Organization Backup
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Create the GitHub App**:
   
   * Go to your organization's settings: ``https://github.com/organizations/YOUR_ORG/settings/apps``
   * Click "New GitHub App"
   * Fill in basic information:
     - App name: e.g., "Organization Backup Tool" 
     - Homepage URL: Can be your organization's website
     - Webhook URL: Not required, can leave blank or use a placeholder

2. **Configure Permissions**:

   **Repository permissions** (select "Read" access for):
   
   * Contents
   * Issues  
   * Metadata
   * Pull requests
   * Webhooks
   * Repository projects (if backing up projects)

   **Organization permissions** (select "Read" access for):
   
   * Members
   * Metadata

   **Account permissions** (select "Read" access for):
   
   * Starring
   * Watching

3. **Installation Settings**:
   
   * Set "Where can this GitHub App be installed?" to "Only on this account" for security
   * Under "Repository access", choose "All repositories" to backup the entire organization

4. **Generate Private Key**:
   
   * After creating the app, scroll down to "Private keys" section
   * Click "Generate a private key" 
   * Download the ``.pem`` file and store it securely

5. **Install the App**:
   
   * Go to the "Install App" tab in your GitHub App settings
   * Click "Install" next to your organization
   * Choose "All repositories" for comprehensive backup access

6. **Get Required Information**:
   
   * **App ID**: Found in your GitHub App settings under "General" tab (the number at the top)
   * **Installation ID**: After installing, the URL will show the installation ID: ``/organizations/YOUR_ORG/settings/installations/INSTALLATION_ID``
   * **Private Key**: The ``.pem`` file you downloaded

Using GitHub App Authentication
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

With the GitHub App created and installed, you can use it directly with github-backup::

    github-backup YOUR_ORG \
        --app-id 123456 \
        --installation-id 789012 \
        --private-key /path/to/your-app.pem \
        --organization \
        --repositories \
        --output-directory /tmp/backup

Or using environment variables for security::

    export GITHUB_APP_ID=123456
    export GITHUB_INSTALLATION_ID=789012  
    export GITHUB_PRIVATE_KEY=/path/to/your-app.pem
    
    github-backup YOUR_ORG \
        --app-id $GITHUB_APP_ID \
        --installation-id $GITHUB_INSTALLATION_ID \
        --private-key $GITHUB_PRIVATE_KEY \
        --organization \
        --repositories \
        --all

**Key Benefits**:

* **Automatic token management**: The tool automatically generates and refreshes installation access tokens as needed
* **No manual token handling**: No need for external scripts or cron job token generation
* **Handles long backups**: Token expiry is automatically handled during multi-hour organization backups
* **Docker-friendly**: Simple to use in containerized environments with mounted private key files

**For automated/cron backups**, simply set up the same command in your cron job::

    # Daily backup at 2 AM
    0 2 * * * github-backup YOUR_ORG --app-id $GITHUB_APP_ID --installation-id $GITHUB_INSTALLATION_ID --private-key $GITHUB_PRIVATE_KEY --organization --repositories --output-directory /backup/github

Github Backup Examples
======================

Backup all repositories, including private ones using a classic token::

    export ACCESS_TOKEN=SOME-GITHUB-TOKEN
    github-backup WhiteHouse --token $ACCESS_TOKEN --organization --output-directory /tmp/white-house --repositories --private

Use a fine-grained access token to backup a single organization repository with everything else (wiki, pull requests, comments, issues etc)::

    export FINE_ACCESS_TOKEN=SOME-GITHUB-TOKEN
    ORGANIZATION=docker
    REPO=cli
    # e.g. git@github.com:docker/cli.git
    github-backup $ORGANIZATION -P -f $FINE_ACCESS_TOKEN -o . --all -O -R $REPO

Quietly and incrementally backup useful Github user data (public and private repos with SSH) including; all issues, pulls, all public starred repos and gists (omitting "hooks", "releases" and therefore "assets" to prevent blocking). *Great for a cron job.* ::

    export FINE_ACCESS_TOKEN=SOME-GITHUB-TOKEN
    GH_USER=YOUR-GITHUB-USER

    github-backup -f $FINE_ACCESS_TOKEN --prefer-ssh -o ~/github-backup/ -l error -P -i --all-starred --starred --watched --followers --following --issues --issue-comments --issue-events --pulls --pull-comments --pull-commits --labels --milestones --repositories --wikis --releases --assets --pull-details --gists --starred-gists $GH_USER
    
Debug an error/block or incomplete backup into a temporary directory. Omit "incremental" to fill a previous incomplete backup. ::

    export FINE_ACCESS_TOKEN=SOME-GITHUB-TOKEN
    GH_USER=YOUR-GITHUB-USER

    github-backup -f $FINE_ACCESS_TOKEN -o /tmp/github-backup/ -l debug -P --all-starred --starred --watched --followers --following --issues --issue-comments --issue-events --pulls --pull-comments --pull-commits --labels --milestones --repositories --wikis --releases --assets --pull-details --gists --starred-gists $GH_USER



GitHub App Organization Backup Examples
========================================

Backup entire organization using GitHub App (recommended for organizations)::

    github-backup mycompany \
        --app-id 123456 \
        --installation-id 789012 \
        --private-key /path/to/app-private-key.pem \
        --organization \
        --repositories \
        --issues \
        --pulls \
        --wikis \
        --output-directory /backup/github-org

Incremental organization backup with GitHub App for automated/cron scenarios::

    github-backup mycompany \
        --app-id 123456 \
        --installation-id 789012 \
        --private-key /path/to/app-private-key.pem \
        --organization \
        --repositories \
        --incremental \
        --output-directory /backup/github-org

Backup specific organization repository with comprehensive data using GitHub App::

    github-backup mycompany \
        --app-id 123456 \
        --installation-id 789012 \
        --private-key /path/to/app-private-key.pem \
        --organization \
        --repository main-project \
        --repositories \
        --issues \
        --pulls \
        --wikis \
        --issue-comments \
        --pull-comments \
        --output-directory /backup/github-repo

Organization backup excluding certain repositories::

    github-backup mycompany \
        --app-id 123456 \
        --installation-id 789012 \
        --private-key /path/to/app-private-key.pem \
        --organization \
        --repositories \
        --exclude repo-to-skip another-repo-to-skip \
        --output-directory /backup/github-org
Development
===========

This project is considered feature complete for the primary maintainer @josegonzalez. If you would like a bugfix or enhancement, pull requests are welcome. Feel free to contact the maintainer for consulting estimates if you'd like to sponsor the work instead.

Contibuters
-----------

A huge thanks to all the contibuters!

.. image:: https://contrib.rocks/image?repo=josegonzalez/python-github-backup
   :target: https://github.com/josegonzalez/python-github-backup/graphs/contributors
   :alt: contributors

Testing
-------

This project currently contains no unit tests.  To run linting::

    pip install flake8
    flake8 --ignore=E501


.. |PyPI| image:: https://img.shields.io/pypi/v/github-backup.svg
   :target: https://pypi.python.org/pypi/github-backup/
.. |Python Versions| image:: https://img.shields.io/pypi/pyversions/github-backup.svg
   :target: https://github.com/josegonzalez/python-github-backup
