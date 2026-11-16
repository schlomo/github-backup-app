# Platform notes: bash

- **In-place `sed` is always `sed -i.bak`.** BSD sed (default on
  macOS) reads the next argument after `-i` as a required backup
  suffix — a bare `sed -i 's/…/…/' file` swallows the script argument
  and dies with a cryptic error. GNU sed (most Linux distros, most CI
  images) accepts a bare `-i` fine, so this passes in CI and fails on
  half the team's laptops. Always supply the suffix explicitly, and
  clean up the `.bak` file if it lands somewhere something else walks
  (a source tree, a fixture directory).
- **`${VAR:?message}` parses quotes in `message` independently of the
  surrounding shell quoting.** An apostrophe inside the message breaks
  the tokenizer even though the whole expansion sits inside double
  quotes elsewhere in the line. Reword the message to avoid
  apostrophes rather than trying to escape around it.
- **A bare `[ cond ] && main "$@"` as the last line of a
  `set -euo pipefail` script aborts the whole script (or, if sourced,
  the calling shell) the moment `cond` is false** — not just that one
  line. This is the classic "only run main if not sourced" idiom, and
  it needs the `if`-form (`if [[ cond ]]; then main "$@"; fi`), which
  is exempt from this trap; the `&&`-form silently kills everything
  downstream the first time it's actually exercised with a false
  condition.
- **`exit` inside a `$(...)` command substitution only ends that
  subshell, never the calling script.** A function meant to "validate
  or exit loudly," called as `x=$(check_thing)`, silently continues
  with `x` empty when the check fails instead of stopping the script.
  Resolve into a plain variable in the *calling* shell rather than a
  subshell when the function's job is to abort on failure.
- **A tool that exits 0 unconditionally makes its exit code useless as
  a success signal.** Some CLIs (especially thin wrappers around a
  remote API) return 0 for usage errors, API-level business errors,
  and genuine success alike, with human-readable noise wrapped around
  a JSON payload on stdout. Any script consuming such a tool must
  extract and verdict the payload itself, never trust the exit code.
- **Never grep a tool's default human-readable table output.** Table
  formatters are free to truncate, reorder, or reformat at will (long
  values elided with "…", columns reordered by terminal width) with no
  compatibility guarantee — a substring match against formatted text
  can silently stop matching the moment a value gets long enough to
  truncate. Ask for structured output (`--json`/`--format=json`/`-o
  json` or equivalent) and match an exact field, every time.
- **A time shown to a person carries an explicit zone, the team's
  (recorded at setup).** Tools print UTC by default; to convert, use
  `TZ=<zone> date -d <time>` (GNU; on macOS `TZ=<zone> date -r
  <epoch>`). An unknown zone, or a missing zone database as in many
  minimal container images, silently falls back to UTC instead of
  failing, so first check that `TZ=<zone> date +%Z` prints the zone's
  own abbreviation or a numeric offset (such as `+04`, for a zone
  without an abbreviation), not `UTC` or a piece of the zone's name.
