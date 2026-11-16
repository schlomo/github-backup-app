# Glossary

Reference page, not an essay. Every term below is defined **once**,
here, and used verbatim everywhere else in this project — no synonyms,
no reusing a defined term for a second meaning (see
`principles/engineering.md`'s "One word per concept").

Where a concept is designed but not yet implemented, say so explicitly
rather than letting the definition imply it already exists.

## github-backup-app

This project: the `github-backup` command, the `github-backup-create-app`
helper, the PyPI package and the GHCR image. Not to be confused with
`github-backup`, the PyPI name of python-github-backup, the project it
was derived from.

## GitHub App

The App an operator creates for backups; the tool authenticates as it.
It must be **public** to be installed on more than one account; a
private App can only be installed on the account that owns it. Anyone
can install a public App, so a run names the accounts it backs up.

## Installation

One account (organization or user) the GitHub App is installed on. A
run discovers all installations and backs up each one's repositories.

## Operator

Whoever runs backups with their own GitHub App and storage; the
controller for the personal data in their backups (D6; the
maintainer's reading, not legally reviewed).

## Maintainer's NAS

The project's one environment (D4): the maintainer's own nightly
backup, configured outside this repo.

## Mirror

The bare git repository the tool keeps per backed-up repository, with
every ref GitHub advertises (branches, tags, pull-request heads) except
pull-request merge refs. The only part of a backup
that is restorable, by push (D9).

## Archive ref

A ref under `refs/backup/<UTC timestamp>/<original ref>` in a mirror,
preserving a ref GitHub deleted or force-moved since the previous run.
Never overwritten.

## Metadata dump

The JSON metadata (issues, pull requests, comments, milestones, labels,
hooks, releases) and release assets in a backup. Kept deliberately
without a restore path, as preparation for a possible exit from GitHub
(D9).

## `status.json`

The machine-readable summary each run writes for monitoring. A clean
`status.json` after every run is half of what "working" means (D9).

## PR image

The container image `ghcr.io/schlomo/github-backup-app:pr-<n>` that a
pull request from a branch in this repo publishes, for trying a change
before merging.
