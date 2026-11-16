# Platform notes: test harnesses

- **A test harness must not let engineer-specific ambient state leak
  into what it tests, or a local green run stops meaning anything
  about CI.** A git identity, a shell alias, a locale, a config file
  that happens to exist on every contributor's laptop but not in the
  CI container — any of these can make a test pass locally and fail
  in CI (or the reverse) for a reason that has nothing to do with the
  code under test. A test that performs a real action requiring
  ambient state (e.g. making a real git commit, which needs a
  configured identity) supplies that state explicitly itself, and the
  harness's setup scrubs the ambient environment down to what CI
  actually provides — never assume a contributor's global config will
  match the CI container's.
- **Building a "tool-absent" test environment by listing named tools
  to keep, plus a fixed system directory appended to the PATH, is not
  portable.** A fixed directory list (e.g. plain `/usr/bin:/bin`) can
  itself contain the very tool being proven absent on some hosts but
  not others, silently defeating the "absent" test on whichever
  machine happens to package it there. Build the "tool absent" PATH by
  filtering the *ambient* `$PATH` to exclude only the one tool under
  test, never by asserting what a fixed system directory does or
  doesn't contain.
- **Run a test suite once per meaningful change, with its exit code
  captured directly** — never through a pipe whose own exit code
  belongs to the last command in the pipeline, which can mask a real
  failure underneath a downstream `tail`/`grep`/formatter that itself
  exits 0. Don't re-run identical code "to be sure" once it passed: an
  accidental second run on genuinely nondeterministic code is
  diagnostic signal; a deliberate one is waste.
- **A failure diagnostic built during a debugging session is permanent
  harness equipment, not scaffolding to strip back out** once the bug
  it caught is fixed — it's now proof the class of bug can't silently
  recur.
- **Red-run-before-fix for every new test** ("Test first" in
  [../engineering.md](../engineering.md)): confirm it actually fails
  against the unfixed code before trusting that it passes for the
  right reason. A regression test for a bug counts only once it was
  seen failing against the unfixed code: revert the fix, watch the
  test fail, reapply.
- **A flake gets root-caused and hardened (e.g. poll instead of a
  single read against asynchronously-populated state), never blind-
  retried.** A retry loop around a flaky assertion hides a real race
  instead of fixing it, and the next person to hit it has no
  diagnostic trail.
- **A test that structurally can't cover something says so, rather
  than implying coverage it doesn't have** — an upstream limitation, an
  unaddressable internal of a dependency, anything that caps what the
  test can actually prove gets documented as a known weak spot in the
  test itself, not silently accepted as "good enough."
