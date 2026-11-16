"""The source distribution ships the package, its tests and its metadata only."""

import tarfile
from pathlib import Path

from hatchling.builders.sdist import SdistBuilder

ROOT = Path(__file__).resolve().parent.parent

ALLOWED_TOP_LEVEL = {
    "github_backup",
    "tests",
    "README.md",
    "LICENSE.txt",
    "pyproject.toml",
    "PKG-INFO",
    ".gitignore",  # hatchling always adds it
}


def build_sdist_members(tmp_path):
    builder = SdistBuilder(str(ROOT))
    (archive,) = builder.build(directory=str(tmp_path), versions=["standard"])
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    # Each member is "<name>-<version>/<path>"; keep "<path>".
    return {name.split("/", 1)[1] for name in names if "/" in name}


def test_sdist_contains_only_package_tests_and_metadata(tmp_path):
    members = build_sdist_members(tmp_path)
    unexpected = sorted(
        m for m in members if m.split("/", 1)[0] not in ALLOWED_TOP_LEVEL
    )
    assert unexpected == []


def test_sdist_contains_the_package_and_its_tests(tmp_path):
    members = build_sdist_members(tmp_path)
    assert "github_backup/__init__.py" in members
    assert "tests/test_git_mirror.py" in members
