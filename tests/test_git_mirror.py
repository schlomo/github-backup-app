"""Tests for the git mirror layer: layout, archiving, auth, migration.

All tests run against local repositories (file:// URLs); no network access.
"""

import base64
import http.server
import json
import os
import subprocess
import threading

import pytest

import github_backup.github_backup as gb

FAKE_TOKEN = "ghs_FAKETOKEN0123456789"
TOKEN_URL = f"https://x-access-token:{FAKE_TOKEN}@github.com/o/r.git"


def git(*args, cwd=None):
    return subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=t",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def refs(repo):
    out = git("for-each-ref", "--format=%(refname) %(objectname)", cwd=repo)
    return {name: sha for name, sha in (line.split(" ") for line in out.splitlines())}


def archived(repo):
    return {s for n, s in refs(repo).items() if n.startswith("refs/backup/")}


def commit(repo, message):
    git("commit", "-q", "--allow-empty", "-m", message, cwd=repo)
    return git("rev-parse", "HEAD", cwd=repo)


def files_containing(root, needle):
    hits = []
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            with open(path, "rb") as f:
                if needle.encode() in f.read():
                    hits.append(path)
    return hits


@pytest.fixture
def upstream(tmp_path):
    """A stand-in for a GitHub repository, including PR refs."""
    src = tmp_path / "upstream"
    git("init", "-q", str(src))
    base = commit(src, "init")
    git("branch", "feature", cwd=src)
    git("branch", "hotfix", cwd=src)
    git("tag", "v1", cwd=src)
    git("tag", "-a", "-m", "annotated", "v2", cwd=src)
    git("update-ref", "refs/pull/1/head", base, cwd=src)
    git("update-ref", "refs/pull/1/merge", base, cwd=src)
    return src


@pytest.fixture
def env():
    return dict(os.environ)


def fetch(upstream, mirror, env, **kwargs):
    """Returns the number of archived refs."""
    return gb.fetch_repository(
        "r", f"file://{upstream}", str(mirror), env, **kwargs
    ).archived


# --- Mirror layout ------------------------------------------------------------


def test_initial_mirror_captures_branches_tags_and_pr_heads(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    assert fetch(upstream, mirror, env) == 0

    assert git("rev-parse", "--is-bare-repository", cwd=mirror) == "true"
    up = refs(upstream)
    got = refs(mirror)
    for name in (
        "refs/heads/main",
        "refs/heads/feature",
        "refs/heads/hotfix",
        "refs/tags/v1",
        "refs/tags/v2",
        "refs/pull/1/head",
    ):
        assert got[name] == up[name]
    assert "refs/pull/1/merge" not in got
    assert git("symbolic-ref", "HEAD", cwd=mirror) == "refs/heads/main"


def test_head_follows_non_default_initial_branch(tmp_path, env):
    src = tmp_path / "upstream"
    git("init", "-q", "-b", "trunk", str(src))
    commit(src, "init")
    mirror = tmp_path / "mirror"
    fetch(src, mirror, env)
    assert git("symbolic-ref", "HEAD", cwd=mirror) == "refs/heads/trunk"


def test_remote_url_is_stored_without_credentials(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    assert git("config", "remote.origin.url", cwd=mirror) == f"file://{upstream}"


# --- Archiving instead of destroying -----------------------------------------


def test_deleted_branch_is_archived(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    hotfix = refs(mirror)["refs/heads/hotfix"]

    git("branch", "-D", "hotfix", cwd=upstream)
    assert fetch(upstream, mirror, env) == 1

    got = refs(mirror)
    assert "refs/heads/hotfix" not in got
    archived = {n: s for n, s in got.items() if n.startswith("refs/backup/")}
    assert list(archived.values()) == [hotfix]
    assert list(archived)[0].endswith("/refs/heads/hotfix")


def test_force_push_is_archived_fast_forward_is_not(upstream, tmp_path, env):
    git("checkout", "-q", "feature", cwd=upstream)
    lost = commit(upstream, "will be force-pushed away")
    git("checkout", "-q", "main", cwd=upstream)
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)

    commit(upstream, "fast-forward on main")
    git("branch", "-f", "feature", "main~1", cwd=upstream)  # force-push
    git("update-ref", "refs/pull/1/head", "main~1", cwd=upstream)
    assert fetch(upstream, mirror, env) == 1

    got = refs(mirror)
    archived = {n: s for n, s in got.items() if n.startswith("refs/backup/")}
    assert list(archived.values()) == [lost]
    assert got["refs/heads/main"] == refs(upstream)["refs/heads/main"]
    assert got["refs/heads/feature"] == refs(upstream)["refs/heads/feature"]


def test_force_moved_pr_head_and_tag_are_archived(upstream, tmp_path, env):
    git("checkout", "-q", "-b", "pr", cwd=upstream)
    pr_tip = commit(upstream, "pr work")
    git("update-ref", "refs/pull/1/head", pr_tip, cwd=upstream)
    git("tag", "-f", "v1", pr_tip, cwd=upstream)
    git("checkout", "-q", "main", cwd=upstream)
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)

    git("branch", "-D", "pr", cwd=upstream)
    git("update-ref", "refs/pull/1/head", "main", cwd=upstream)
    git("tag", "-f", "v1", "main", cwd=upstream)
    assert fetch(upstream, mirror, env) == 3

    archived = {
        n.split("/", 3)[3]: s
        for n, s in refs(mirror).items()
        if n.startswith("refs/backup/")
    }
    assert archived == {
        "refs/heads/pr": pr_tip,
        "refs/pull/1/head": pr_tip,
        "refs/tags/v1": pr_tip,
    }


def test_archive_refs_survive_later_runs_and_gc(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("branch", "-D", "hotfix", cwd=upstream)
    fetch(upstream, mirror, env)
    commit(upstream, "more")
    fetch(upstream, mirror, env)
    git("gc", "-q", "--prune=now", cwd=mirror)

    archived = [n for n in refs(mirror) if n.startswith("refs/backup/")]
    assert len(archived) == 1
    git("cat-file", "-e", archived[0] + "^{commit}", cwd=mirror)


def test_unchanged_remote_skips_fetch(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    url = f"file://{upstream}"
    assert gb.fetch_repository("r", url, str(mirror), env).skipped
    assert not gb.fetch_repository("r", url, str(mirror), env, force=True).skipped


def test_pr_head_change_alone_triggers_fetch(upstream, tmp_path, env):
    """A fork pushing to its PR does not touch the repository's branches
    (nor its pushed_at); only refs/pull/<n>/head moves."""
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("checkout", "-q", "--detach", cwd=upstream)
    fork_commit = commit(upstream, "pushed to the fork")
    git("checkout", "-q", "main", cwd=upstream)
    git("update-ref", "refs/pull/1/head", fork_commit, cwd=upstream)

    result = gb.fetch_repository("r", f"file://{upstream}", str(mirror), env)

    assert not result.skipped
    assert refs(mirror)["refs/pull/1/head"] == fork_commit


def test_default_branch_change_without_push_updates_head(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("symbolic-ref", "HEAD", "refs/heads/feature", cwd=upstream)
    assert gb.fetch_repository("r", f"file://{upstream}", str(mirror), env).skipped
    assert git("symbolic-ref", "HEAD", cwd=mirror) == "refs/heads/feature"


def test_pending_journal_is_settled_even_when_fetch_is_skipped(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    gb._write_journal(str(mirror), gb._list_mirrored_refs(str(mirror)))
    hotfix = refs(mirror)["refs/heads/hotfix"]
    git("update-ref", "-d", "refs/heads/hotfix", cwd=mirror)  # killed mid-prune
    git("branch", "-D", "hotfix", cwd=upstream)

    result = gb.fetch_repository("r", f"file://{upstream}", str(mirror), env)

    assert result.skipped and result.archived == 1
    assert hotfix in archived(mirror)
    assert not (mirror / gb.REF_JOURNAL).exists()


def test_no_prune_flag_is_accepted_and_ignored(tmp_path):
    args = gb.parse_args(
        ["--app-id", "1", "--private-key", "k", "--no-prune", "--bare"]
    )
    assert args.no_prune and args.bare_clone


def test_restore_roundtrip(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("branch", "-D", "hotfix", cwd=upstream)
    fetch(upstream, mirror, env)

    restored = tmp_path / "restored"
    git("init", "-q", "--bare", str(restored))
    git(
        "push",
        "-q",
        str(restored),
        "refs/heads/*:refs/heads/*",
        "refs/tags/*:refs/tags/*",
        cwd=mirror,
    )
    want = {
        n: s
        for n, s in refs(upstream).items()
        if n.startswith(("refs/heads/", "refs/tags/"))
    }
    assert refs(restored) == want


# --- Failure handling ---------------------------------------------------------


def test_missing_optional_remote_is_skipped(tmp_path, env):
    target = tmp_path / "wiki"
    assert gb.fetch_repository(
        "w", f"file://{tmp_path}/nope", str(target), env, optional=True
    ) == (0, True, None)
    assert not target.exists()


def test_missing_required_remote_raises(tmp_path, env):
    with pytest.raises(gb.GitCommandError):
        gb.fetch_repository("r", f"file://{tmp_path}/nope", str(tmp_path / "x"), env)


def test_optional_remote_failing_after_backup_exists_raises(upstream, tmp_path, env):
    wiki = tmp_path / "wiki"
    fetch(upstream, wiki, env, optional=True)
    with pytest.raises(gb.GitCommandError):
        gb.fetch_repository(
            "w", f"file://{tmp_path}/gone", str(wiki), env, optional=True
        )


def test_failing_fetch_raises_instead_of_being_ignored(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    # Make every ref update in the mirror fail, as a full disk would.
    hook = mirror / "hooks" / "reference-transaction"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    commit(upstream, "new")
    with pytest.raises(gb.GitCommandError, match="fetch"):
        fetch(upstream, mirror, env)


# --- Authentication -----------------------------------------------------------


@pytest.fixture
def fake_auth(monkeypatch):
    monkeypatch.setattr(gb, "get_auth", lambda *a, **k: FAKE_TOKEN)


def test_auth_env_carries_token_as_scoped_header(fake_auth, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "user.name")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "keep")
    args = gb.argparse.Namespace(github_host=None)
    env = gb.get_git_auth_env(args, {"_installation_id": 1})

    basic = base64.b64encode(f"x-access-token:{FAKE_TOKEN}".encode()).decode()
    key = "http.https://github.com/.extraHeader"
    assert env["GIT_CONFIG_COUNT"] == "3"
    assert env["GIT_CONFIG_KEY_0"] == "user.name"
    assert (env["GIT_CONFIG_KEY_1"], env["GIT_CONFIG_VALUE_1"]) == (key, "")
    assert env["GIT_CONFIG_KEY_2"] == key
    assert env["GIT_CONFIG_VALUE_2"] == f"Authorization: Basic {basic}"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_git_sends_exactly_one_auth_header(fake_auth, tmp_path, monkeypatch):
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get_all("Authorization"))
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{server.server_port}"
    # A conflicting header in the global config (as on some CI hosts) must
    # not lead to a second Authorization header.
    global_config = tmp_path / "gitconfig"
    global_config.write_text(
        f'[http "http://{host}/"]\n\textraHeader = Authorization: Basic stale\n'
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    try:
        args = gb.argparse.Namespace(github_host=host)
        env = gb.get_git_auth_env(args, {"_installation_id": 1})
        # The production header is scoped to https://; the test server is
        # plain http, so re-scope both entries (reset and header).
        for i in range(int(env["GIT_CONFIG_COUNT"])):
            if env[f"GIT_CONFIG_KEY_{i}"].endswith(".extraHeader"):
                env[f"GIT_CONFIG_KEY_{i}"] = f"http.http://{host}/.extraHeader"
        with pytest.raises(gb.GitCommandError) as err:
            gb.fetch_repository("r", f"http://{host}/o/r.git", str(tmp_path / "m"), env)
    finally:
        server.shutdown()

    basic = base64.b64encode(f"x-access-token:{FAKE_TOKEN}".encode()).decode()
    assert seen and all(headers == [f"Basic {basic}"] for headers in seen)
    assert FAKE_TOKEN not in str(err.value)


def test_full_backup_leaves_no_token_on_disk_or_in_status(
    fake_auth, upstream, tmp_path, monkeypatch
):
    """Uses the real get_git_auth_env; file:// ignores the header, but every
    file written by migration, fetch and the loop is checked for the token."""
    repo_cwd = tmp_path / "out" / "o" / "repositories" / "r"
    legacy = repo_cwd / "repository"
    git("clone", "-q", f"file://{upstream}", str(legacy))
    git("config", "remote.origin.url", TOKEN_URL, cwd=legacy)
    monkeypatch.setattr(gb, "get_github_repo_url", lambda a, r: f"file://{upstream}")
    commit(upstream, "new")

    stats = gb.backup_repositories(
        _loop_args(tmp_path), str(tmp_path / "out"), [_repository("new")]
    )

    assert stats["repositories_succeeded"] == 1
    assert files_containing(tmp_path / "out", FAKE_TOKEN) == []
    assert FAKE_TOKEN not in json.dumps(stats)


def test_dubious_ownership_is_reported_clearly(upstream, tmp_path, env):
    if os.geteuid() != 0:
        pytest.skip("needs root to chown")
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    for root, dirs, files in os.walk(mirror):
        for entry in [root, *(os.path.join(root, f) for f in files)]:
            os.chown(entry, 12345, 12345)
    with pytest.raises(gb.GitCommandError, match="owned by a different user"):
        fetch(upstream, mirror, env)


def test_lightweight_tag_moved_forward_is_archived(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    old = refs(mirror)["refs/tags/v1"]
    commit(upstream, "newer")
    git("tag", "-f", "v1", cwd=upstream)
    assert fetch(upstream, mirror, env) == 1
    assert old in archived(mirror)


def test_wiki_failing_for_other_reasons_is_not_skipped(tmp_path, env):
    with pytest.raises(gb.GitCommandError):
        gb.fetch_repository(
            "w",
            "http://127.0.0.1:9/o/r.wiki.git",
            str(tmp_path / "w"),
            dict(env, NO_PROXY="127.0.0.1", no_proxy="127.0.0.1"),
            optional=True,
        )


def test_clone_urls_have_no_credentials_and_handle_dotted_names():
    args = gb.argparse.Namespace(github_host=None)
    repo = {"owner": {"login": "o"}, "name": "o.github.io"}
    assert gb.get_github_repo_url(args, repo) == "https://github.com/o/o.github.io.git"
    assert (
        gb.get_github_wiki_url(args, repo)
        == "https://github.com/o/o.github.io.wiki.git"
    )


# --- Migration of existing backups -------------------------------------------


@pytest.fixture
def legacy_clone(upstream, tmp_path):
    """A backup as written by <= 0.3.0 default mode, with history to rescue."""
    legacy = tmp_path / "backup" / "repository"
    legacy.parent.mkdir()
    git("clone", "-q", f"file://{upstream}", str(legacy))

    def old_update():
        git("fetch", "-q", "--all", "--force", "--tags", "--prune", cwd=legacy)

    # A force-push the old version saw: the old tip lives only in the reflog.
    reflog_only = commit(upstream, "force-pushed away later")
    old_update()
    git("reset", "-q", "--hard", "HEAD~1", cwd=upstream)
    commit(upstream, "rewritten")
    old_update()

    # A branch the old version pruned: its reflog is gone, only the objects
    # remain (dangling).
    git("checkout", "-q", "-b", "doomed", cwd=upstream)
    dangling = commit(upstream, "on a branch that gets deleted")
    git("checkout", "-q", "main", cwd=upstream)
    old_update()
    git("branch", "-D", "doomed", cwd=upstream)
    old_update()

    git("config", "remote.origin.url", TOKEN_URL, cwd=legacy)
    return legacy, reflog_only, dangling


def test_migration_of_legacy_clone_is_lossless(upstream, legacy_clone):
    legacy, reflog_only, dangling = legacy_clone
    before = refs(legacy)

    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")

    assert git("rev-parse", "--is-bare-repository", cwd=legacy) == "true"
    assert not (legacy / ".git").exists()
    got = refs(legacy)
    # Every upstream branch became a real branch at the same commit.
    for name, sha in before.items():
        if name.startswith("refs/remotes/origin/") and not name.endswith("/HEAD"):
            assert got["refs/heads/" + name.rsplit("/", 1)[1]] == sha
    for name, sha in before.items():
        if name.startswith("refs/tags/"):
            assert got[name] == sha
    assert not any(n.startswith("refs/remotes/") for n in got)
    archived = {s for n, s in got.items() if n.startswith("refs/backup/")}
    assert reflog_only in archived
    assert dangling in archived
    assert files_containing(legacy, FAKE_TOKEN) == []
    git("fsck", "--connectivity-only", "--no-dangling", cwd=legacy)


def test_migrated_mirror_then_fetches_normally(upstream, legacy_clone, env):
    legacy, _, _ = legacy_clone
    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
    commit(upstream, "after migration")
    assert fetch(upstream, legacy, env) == 0
    assert refs(legacy)["refs/heads/main"] == refs(upstream)["refs/heads/main"]
    assert "refs/pull/1/head" in refs(legacy)


def test_migration_resumes_after_interruption_at_any_step(upstream, legacy_clone):
    legacy, _, _ = legacy_clone
    tmp = str(legacy) + gb.MIGRATION_SUFFIX
    want_main = refs(legacy)["refs/remotes/origin/main"]

    # Interrupted right after moving .git aside ...
    os.rename(legacy / ".git", tmp)
    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
    assert refs(legacy)["refs/heads/main"] == want_main
    assert not os.path.exists(tmp)

    # ... and after the working tree was already deleted.
    os.rename(legacy, tmp)
    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
    assert refs(legacy)["refs/heads/main"] == want_main


def test_migration_refuses_ambiguous_state(upstream, legacy_clone):
    legacy, _, _ = legacy_clone
    os.mkdir(str(legacy) + gb.MIGRATION_SUFFIX)
    with pytest.raises(Exception, match="left untouched"):
        gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
    assert (legacy / ".git").is_dir()


def test_migration_leaves_corrupt_clone_untouched(upstream, legacy_clone):
    legacy, _, _ = legacy_clone
    git("gc", "-q", cwd=legacy)  # pack everything ...
    main = refs(legacy)["refs/remotes/origin/main"]
    for pack in (legacy / ".git" / "objects" / "pack").glob("*.pack"):
        os.chmod(pack, 0o644)
        pack.write_bytes(b"")  # ... and destroy the pack
    with pytest.raises(Exception, match="left untouched") as err:
        gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
    # The real problem is reported, not the expected dangling commits.
    assert "dangling" not in str(err.value)
    assert "error" in str(err.value) or "fatal" in str(err.value)
    assert (legacy / ".git").is_dir()
    assert refs(legacy)["refs/remotes/origin/main"] == main


def test_migration_of_old_bare_mirror(upstream, tmp_path, env):
    old = tmp_path / "old"
    git("clone", "-q", "--mirror", f"file://{upstream}", str(old))
    git("config", "remote.origin.url", TOKEN_URL, cwd=old)
    assert "refs/pull/1/merge" in refs(old)

    assert fetch(upstream, old, env) == 0

    assert "refs/pull/1/merge" not in refs(old)
    assert git("config", "--get-all", "remote.origin.fetch", cwd=old).split(
        "\n"
    ) == list(gb.GIT_FETCH_REFSPECS)
    assert files_containing(old, FAKE_TOKEN) == []


# --- Integration with the per-repository loop --------------------------------


def _loop_args(tmp_path):
    return gb.parse_args(
        ["--app-id", "1", "--private-key", str(tmp_path / "k.pem"), "-o", str(tmp_path)]
    )


def _repository(pushed_at="2026-01-01T00:00:00Z"):
    return {
        "name": "r",
        "full_name": "o/r",
        "owner": {"login": "o"},
        "pushed_at": pushed_at,
        "has_wiki": False,
        "_installation_id": 1,
    }


@pytest.fixture
def loop(monkeypatch, tmp_path):
    def run(url, repository):
        monkeypatch.setattr(gb, "get_github_repo_url", lambda a, r: url)
        monkeypatch.setattr(gb, "get_git_auth_env", lambda a, r: dict(os.environ))
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        stats = gb.backup_repositories(_loop_args(tmp_path), str(out), [repository])
        return stats, out / "o" / "repositories" / "r"

    return run


def test_loop_records_failed_fetch_and_does_not_mark_repo_done(loop, tmp_path):
    stats, repo_cwd = loop(f"file://{tmp_path}/nope", _repository())
    assert stats["repositories_failed"] == 1
    assert not (repo_cwd / gb.REPO_METADATA_FILENAME).exists()


def test_loop_counts_archived_refs(loop, upstream):
    loop(f"file://{upstream}", _repository("t1"))
    git("branch", "-D", "hotfix", cwd=upstream)
    stats, _ = loop(f"file://{upstream}", _repository("t2"))
    assert stats["repositories_succeeded"] == 1
    assert stats["git_refs_archived"] == 1


def test_loop_migrates_legacy_clone_then_skips_unchanged_git(loop, upstream, tmp_path):
    repo_cwd = tmp_path / "out" / "o" / "repositories" / "r"
    git("clone", "-q", f"file://{upstream}", str(repo_cwd / "repository"))
    git("config", "remote.origin.url", TOKEN_URL, cwd=repo_cwd / "repository")

    # First run: migrates, scrubs the token, fetches what the old clone
    # lacked (PR heads).
    stats, _ = loop(f"file://{upstream}", _repository())
    mirror = repo_cwd / "repository"
    assert stats["repositories_succeeded"] == 1
    assert stats["repositories_git_skipped_unchanged"] == 0
    assert git("rev-parse", "--is-bare-repository", cwd=mirror) == "true"
    assert files_containing(mirror, FAKE_TOKEN) == []
    assert "refs/pull/1/head" in refs(mirror)

    # Second run: nothing changed on GitHub.
    stats, _ = loop(f"file://{upstream}", _repository())
    assert stats["repositories_git_skipped_unchanged"] == 1


# --- Environment --------------------------------------------------------------


@pytest.mark.parametrize(
    "output, ok",
    [
        ("git version 2.31.0\n", True),
        ("git version 2.52.0.windows.1\n", True),
        ("git version 3.0.0\n", True),
        ("git version 2.30.9\n", False),
        ("git version 1.99.0\n", False),
        ("garbage\n", False),
    ],
)
def test_check_git_version(monkeypatch, output, ok):
    monkeypatch.setattr(
        gb.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=output),
    )
    if ok:
        assert gb.check_git_version() == output.strip()
    else:
        with pytest.raises(Exception, match="git >= 2.31 is required"):
            gb.check_git_version()


def test_check_git_version_reports_missing_git(monkeypatch):
    def missing(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(gb.subprocess, "run", missing)
    with pytest.raises(Exception, match="git is required"):
        gb.check_git_version()


def test_installed_git_is_supported():
    gb.check_git_version()


# --- Regression tests from adversarial review ----------------------------------


def _reachable_from_refs(repo, sha):
    out = git("for-each-ref", "--contains", sha, "--format=%(refname)", cwd=repo)
    return bool(out)


def _object_has_ref(repo, sha):
    """True if sha is referenced by a ref directly or reachable from one."""
    names = git("for-each-ref", "--format=%(objectname)", cwd=repo).split()
    return sha in names or _reachable_from_refs(repo, sha)


def test_migration_keeps_tip_from_before_first_force_push(upstream, tmp_path):
    legacy = tmp_path / "repository"
    git("clone", "-q", f"file://{upstream}", str(legacy))
    git("checkout", "-q", "feature", cwd=upstream)
    first = commit(upstream, "f1")
    git("fetch", "-q", "--all", "--force", "--tags", "--prune", cwd=legacy)
    tips = [first]
    for i in range(3):
        git("reset", "-q", "--hard", "HEAD~1", cwd=upstream)
        tips.append(commit(upstream, f"rewrite {i}"))
        git("fetch", "-q", "--all", "--force", "--tags", "--prune", cwd=legacy)
    git("checkout", "-q", "main", cwd=upstream)

    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")

    for sha in tips:
        assert _object_has_ref(legacy, sha), sha


def test_migration_rescues_commits_behind_dangling_annotated_tag(upstream, tmp_path):
    legacy = tmp_path / "repository"
    git("clone", "-q", f"file://{upstream}", str(legacy))
    git("checkout", "-q", "--detach", cwd=upstream)
    release_only = commit(upstream, "release-only commit")
    git("tag", "-a", "-m", "r1", "rel", cwd=upstream)
    git("checkout", "-q", "main", cwd=upstream)
    git("fetch", "-q", "--all", "--force", "--tags", "--prune", cwd=legacy)
    old_tag = refs(legacy)["refs/tags/rel"]
    git("tag", "-f", "-a", "-m", "r1 again", "rel", "main", cwd=upstream)
    git("fetch", "-q", "--all", "--force", "--tags", "--prune", cwd=legacy)

    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")

    assert _object_has_ref(legacy, old_tag)
    assert _object_has_ref(legacy, release_only)


def test_old_bare_mirror_pruned_commits_are_rescued(upstream, tmp_path, env):
    old = tmp_path / "old"
    git("clone", "-q", "--mirror", f"file://{upstream}", str(old))
    git("checkout", "-q", "-b", "doomed", cwd=upstream)
    doomed = commit(upstream, "doomed")
    git("checkout", "-q", "main", cwd=upstream)
    git("fetch", "-q", "--prune", cwd=old)
    git("branch", "-D", "doomed", cwd=upstream)
    git("fetch", "-q", "--prune", cwd=old)  # old version pruned it

    fetch(upstream, old, env)

    assert _object_has_ref(old, doomed)


def test_rewritten_annotated_tag_on_same_commit_is_archived(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    old_tag = refs(mirror)["refs/tags/v2"]
    git("tag", "-f", "-a", "-m", "re-signed", "v2", cwd=upstream)
    assert fetch(upstream, mirror, env) == 1
    assert old_tag in archived(mirror)


def test_interrupted_archiving_is_completed_on_next_run(
    upstream, tmp_path, env, monkeypatch
):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    hotfix = refs(mirror)["refs/heads/hotfix"]
    git("branch", "-D", "hotfix", cwd=upstream)

    def killed(*args, **kwargs):
        raise KeyboardInterrupt

    with monkeypatch.context() as m:
        m.setattr(gb, "_archive_ref", killed)
        with pytest.raises(KeyboardInterrupt):
            fetch(upstream, mirror, env)
    assert "refs/heads/hotfix" not in refs(mirror)  # fetch already pruned it

    assert fetch(upstream, mirror, env) == 1
    assert hotfix in archived(mirror)


def test_fetch_failing_after_prune_still_archives_deleted_refs(upstream, tmp_path, env):
    git("checkout", "-q", "hotfix", cwd=upstream)
    hotfix = commit(upstream, "only on hotfix")
    git("checkout", "-q", "main", cwd=upstream)
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    # Deletions (prune) and archive refs succeed, any other ref update fails:
    # git prunes first, then the transfer/update fails.
    hook = mirror / "hooks" / "reference-transaction"
    hook.write_text(
        "#!/bin/sh\n"
        '[ "$1" = prepared ] || exit 0\n'
        "while read old new ref; do\n"
        '  case "$ref" in refs/backup/*) continue;; esac\n'
        '  [ "$new" = "$(printf %040d 0)" ] || exit 1\n'
        "done\n"
    )
    hook.chmod(0o755)
    git("branch", "-D", "hotfix", cwd=upstream)
    commit(upstream, "new")

    with pytest.raises(gb.GitCommandError):
        fetch(upstream, mirror, env)

    got = refs(mirror)
    assert "refs/heads/hotfix" not in got
    archived = [n for n, sha in got.items() if sha == hotfix]
    assert archived and all(n.startswith("refs/backup/") for n in archived)


def test_failed_first_fetch_leaves_no_mirror_behind(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    (hook_dir / "reference-transaction").write_text("#!/bin/sh\nexit 1\n")
    (hook_dir / "reference-transaction").chmod(0o755)
    env = dict(env, GIT_CONFIG_PARAMETERS=f"'core.hooksPath={hook_dir}'")
    with pytest.raises(gb.GitCommandError):
        fetch(upstream, mirror, env)
    assert not mirror.exists()


def test_archive_never_overwrites_existing_archive(
    upstream, tmp_path, env, monkeypatch
):
    monkeypatch.setattr(gb, "_archive_timestamp", lambda: "20260101T000000Z")
    git("checkout", "-q", "feature", cwd=upstream)
    a = commit(upstream, "a")
    git("checkout", "-q", "main", cwd=upstream)
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("checkout", "-q", "feature", cwd=upstream)
    git("reset", "-q", "--hard", "HEAD~1", cwd=upstream)
    b = commit(upstream, "b")
    git("checkout", "-q", "main", cwd=upstream)
    fetch(upstream, mirror, env)
    git("branch", "-f", "feature", "main", cwd=upstream)
    fetch(upstream, mirror, env)

    archived = [s for n, s in refs(mirror).items() if n.startswith("refs/backup/")]
    assert a in archived and b in archived


def test_wiki_with_interrupted_migration_is_not_silently_skipped(
    upstream, tmp_path, env
):
    wiki = tmp_path / "wiki"
    git("clone", "-q", f"file://{upstream}", str(wiki))
    os.rename(wiki / ".git", str(wiki) + gb.MIGRATION_SUFFIX)
    import shutil

    shutil.rmtree(wiki)
    with pytest.raises(gb.GitCommandError):
        gb.fetch_repository(
            "w", f"file://{tmp_path}/gone", str(wiki), env, optional=True
        )


def test_notes_are_mirrored(upstream, tmp_path, env):
    git("notes", "add", "-m", "a note", "main", cwd=upstream)
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    assert "refs/notes/commits" in refs(mirror)


def test_git_failure_does_not_block_metadata_backup(loop, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(gb, "backup_labels", lambda *a, **k: calls.append("labels"))
    monkeypatch.setattr(gb, "fetch_repository_metadata_graphql", lambda *a, **k: {})
    monkeypatch.setattr(
        gb,
        "parse_args",
        lambda argv, _orig=gb.parse_args: _orig([*argv, "--labels"]),
    )
    stats, repo_cwd = loop(f"file://{tmp_path}/nope", _repository())
    assert calls == ["labels"]
    assert stats["repositories_failed"] == 1
    assert not (repo_cwd / gb.REPO_METADATA_FILENAME).exists()


# --- Fresh copy as the fallback for broken local backups ----------------------


def _quarantined(path):
    parent, name = os.path.split(str(path))
    return sorted(
        os.path.join(parent, n)
        for n in os.listdir(parent)
        if n.startswith(name + gb.BROKEN_SUFFIX)
    )


def _corrupt_packs(git_dir):
    git("-c", "gc.writeCommitGraph=false", "gc", "-q", cwd=git_dir)
    for pack in (git_dir / "objects" / "pack").glob("*.pack"):
        os.chmod(pack, 0o644)
        pack.write_bytes(b"")


def test_stale_commit_graph_does_not_block_migration(upstream, tmp_path):
    """Seen in the field: 0.3.0's gc deleted unreferenced commits but left
    them listed in the commit-graph cache, so fsck failed."""
    legacy = tmp_path / "repository"
    git("clone", "-q", f"file://{upstream}", str(legacy))
    git("checkout", "-q", "-b", "gone", cwd=upstream)
    commit(upstream, "later deleted")
    git("checkout", "-q", "main", cwd=upstream)
    git("fetch", "-q", "--all", "--prune", cwd=legacy)
    git("commit-graph", "write", "--reachable", cwd=legacy)
    git("branch", "-D", "gone", cwd=upstream)
    git("fetch", "-q", "--all", "--prune", cwd=legacy)
    git("reflog", "expire", "--expire-unreachable=now", "--all", cwd=legacy)
    git("-c", "gc.writeCommitGraph=false", "gc", "-q", "--prune=now", cwd=legacy)
    plain = subprocess.run(
        ["git", "fsck", "--connectivity-only"], cwd=legacy, capture_output=True
    )
    assert plain.returncode != 0  # the situation from the field

    gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")

    assert git("rev-parse", "--is-bare-repository", cwd=legacy) == "true"
    assert _quarantined(legacy) == []


def test_corrupt_legacy_clone_is_kept_and_replaced_by_fresh_copy(
    upstream, legacy_clone, env
):
    legacy, _, _ = legacy_clone
    _corrupt_packs(legacy / ".git")

    result = gb.fetch_repository("r", f"file://{upstream}", str(legacy), env)

    assert result.recovered and "fsck" in result.recovered["reason"]
    moved = _quarantined(legacy)
    assert moved == [result.recovered["moved_to"]]
    assert os.path.isdir(os.path.join(moved[0], ".git"))  # old data kept as is
    assert git("rev-parse", "--is-bare-repository", cwd=legacy) == "true"
    want = {n: s for n, s in refs(upstream).items() if not n.endswith("/merge")}
    assert refs(legacy) == want


def test_unfinishable_migration_state_is_kept_and_replaced(upstream, legacy_clone, env):
    legacy, _, _ = legacy_clone
    os.mkdir(str(legacy) + gb.MIGRATION_SUFFIX)

    result = gb.fetch_repository("r", f"file://{upstream}", str(legacy), env)

    moved = result.recovered["moved_to"]
    assert os.path.isdir(os.path.join(moved, ".git"))
    assert os.path.isdir(moved + gb.MIGRATION_SUFFIX)
    assert not os.path.exists(str(legacy) + gb.MIGRATION_SUFFIX)
    assert refs(legacy)["refs/heads/main"] == refs(upstream)["refs/heads/main"]


def test_damaged_mirror_is_replaced_when_fetch_fails(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    _corrupt_packs(mirror)
    commit(upstream, "new")

    result = gb.fetch_repository("r", f"file://{upstream}", str(mirror), env)

    assert result.recovered and "damaged" in result.recovered["reason"]
    assert refs(mirror)["refs/heads/main"] == refs(upstream)["refs/heads/main"]


def test_remote_failure_never_moves_a_backup_aside(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    _corrupt_packs(mirror)  # even a damaged one: the remote is the problem
    with pytest.raises(gb.GitCommandError):
        gb.fetch_repository("r", f"file://{tmp_path}/gone", str(mirror), env)
    assert _quarantined(mirror) == []
    assert mirror.is_dir()


def test_ownership_problem_never_moves_a_backup_aside(upstream, tmp_path, env):
    if os.geteuid() != 0:
        pytest.skip("needs root to chown")
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    for root, dirs, files in os.walk(mirror):
        for entry in [root, *(os.path.join(root, f) for f in files)]:
            os.chown(entry, 12345, 12345)
    with pytest.raises(gb.GitOwnershipError):
        fetch(upstream, mirror, env)
    assert _quarantined(mirror) == []


def test_loop_reports_recovered_repository_as_success(loop, upstream, tmp_path):
    repo_cwd = tmp_path / "out" / "o" / "repositories" / "r"
    legacy = repo_cwd / "repository"
    git("clone", "-q", f"file://{upstream}", str(legacy))
    _corrupt_packs(legacy / ".git")

    stats, _ = loop(f"file://{upstream}", _repository())

    assert stats["repositories_succeeded"] == 1
    [recovered] = stats["recovered_repositories"]
    assert recovered["repository"] == "o/r"
    assert os.path.isdir(recovered["moved_to"])
