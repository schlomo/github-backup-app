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
    return gb.fetch_repository("r", f"file://{upstream}", str(mirror), env, **kwargs)


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


def test_no_prune_keeps_deleted_branch_in_place(upstream, tmp_path, env):
    mirror = tmp_path / "mirror"
    fetch(upstream, mirror, env)
    git("branch", "-D", "hotfix", cwd=upstream)
    assert fetch(upstream, mirror, env, no_prune=True) == 0
    assert "refs/heads/hotfix" in refs(mirror)


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
    assert (
        gb.fetch_repository(
            "w", f"file://{tmp_path}/nope", str(target), env, optional=True
        )
        == 0
    )
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
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_0"] == "user.name"
    assert env["GIT_CONFIG_KEY_1"] == "http.https://github.com/.extraHeader"
    assert env["GIT_CONFIG_VALUE_1"] == f"Authorization: Basic {basic}"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_git_sends_auth_header_and_never_persists_it(fake_auth, tmp_path):
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host = f"127.0.0.1:{server.server_port}"
    try:
        args = gb.argparse.Namespace(github_host=host)
        env = gb.get_git_auth_env(args, {"_installation_id": 1})
        # The production header is scoped to https://; the test server is http.
        key = f"GIT_CONFIG_KEY_{int(env['GIT_CONFIG_COUNT']) - 1}"
        env[key] = f"http.http://{host}/.extraHeader"
        for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            env.pop(var, None)
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1"
        with pytest.raises(gb.GitCommandError) as err:
            gb.fetch_repository("r", f"http://{host}/o/r.git", str(tmp_path / "m"), env)
    finally:
        server.shutdown()

    basic = base64.b64encode(f"x-access-token:{FAKE_TOKEN}".encode()).decode()
    assert seen and set(seen) == {f"Basic {basic}"}
    assert FAKE_TOKEN not in str(err.value)
    assert not (tmp_path / "m").exists() or not files_containing(
        tmp_path / "m", FAKE_TOKEN
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
    with pytest.raises(Exception, match="left untouched"):
        gb.ensure_mirror_repository(str(legacy), f"file://{upstream}")
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


def test_loop_migrates_and_scrubs_token_even_when_git_is_skipped(
    loop, upstream, tmp_path
):
    repo_cwd = tmp_path / "out" / "o" / "repositories" / "r"
    git("clone", "-q", f"file://{upstream}", str(repo_cwd / "repository"))
    git("config", "remote.origin.url", TOKEN_URL, cwd=repo_cwd / "repository")
    (repo_cwd / gb.REPO_METADATA_FILENAME).write_text(json.dumps({"pushed_at": "same"}))

    stats, _ = loop(f"file://{upstream}", _repository("same"))

    assert stats["repositories_git_skipped_unchanged"] == 1
    mirror = repo_cwd / "repository"
    assert git("rev-parse", "--is-bare-repository", cwd=mirror) == "true"
    assert files_containing(mirror, FAKE_TOKEN) == []
