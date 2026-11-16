# Engineering principles

The engineering principles of this project. Each states a rule, why
it matters, and how to apply it. A principle changes only through
"Changing a principle" in [ai-working-process.md](ai-working-process.md).
Language and tool specifics live in the platform notes
([platform-notes/](platform-notes/)).

## Fail early and loudly

**Rule:** a missing precondition, a failed step or an unexpected
state stops the program with an explicit error that says what is
missing and what to do; nothing is silently skipped, defaulted or
swallowed, and no exit status is lost. Dependencies are checked before
any work.
**Why:** a silent failure is a bug that ships; a loud one is a bug
that gets fixed before it ships.
**How:** check preconditions before doing work, not mid-way through.
In shell this means `set -euo pipefail`; in any language it means no
catch-all that continues, and errors to the error stream, not the
output stream.

## Trust the PATH

**Rule:** tools are invoked by bare name through the environment's
lookup path; their presence is required up front and their absence is
a loud stop. Never probe alternate locations, never fall back to
another tool or version.
**Why:** probing alternate locations hides a missing dependency behind
inconsistent behavior instead of a clear error, and makes the
program's real requirements unknowable from reading it.
**How:** if a tool isn't on the PATH, say so and stop — don't guess
where it might be installed. In shell: `#!/usr/bin/env` shebangs and
`command -v` checks; in Python: `shutil.which`.

## Credentials are pure injection

**Rule:** code never obtains, parses, or relays secrets; the
environment provides them and each tool reads its own. Presence
checks are fine; wiring is not.
**Why:** credentials come in many shapes (env vars, SDK credential
files, agency/metadata identity) — hardcoding one shape breaks every
other legitimate injection path and duplicates resolution logic the
tool's own SDK already owns correctly.
**How:** let the tool's own credential chain resolve auth. The only
valid "is it working" check is a benign authenticated operation
through that chain, not an environment-variable presence check.
Never echo, log, or pass a credential value in argv — each tool reads
its own from its own documented path. A missing documented credential
path is a stop-and-report, never a hunt through another tool's stored
tokens as a substitute.

## Test first

**Rule:** every behavior change starts with a failing test, and the
test is part of the change. Never weaken a test to make it pass.
Tests and CI gate every change. Exception: a time-boxed throwaway
spike to learn something — never merged; what it taught goes into a
test-first change.
**Why:** a test seen failing first proves it can catch the bug; a
test written after the code tends to prove what the code does, not
what it should do. Tests and CI, not a human reading the code, keep
the software production grade.
**How:** write the test, watch it fail for the expected reason, then
make it pass. Use the ecosystem's standard test framework (the
platform notes name it per language). A local hook (pre-commit,
pre-push) gives early feedback or adds a safeguard on top of the
check of record (CI, the server, or a human's review), and is never
that check itself. Anyone can skip it, a fresh clone doesn't have
it, and it can differ from machine to machine, so a passing hook is
a hint, not a verification.

## The tested procedure IS the shipped procedure

**Rule:** no parallel test-only implementations. Idempotency is part
of the contract — re-running is the upgrade path.
**Why:** a test harness that exercises a different code path than
production proves nothing about production; a procedure that isn't
safe to re-run isn't safe to run at all, since re-running is exactly
what recovery looks like.
**How:** the same script/program that ships is the one under test. If
something must behave differently under test, that's a sign the
design needs a seam, not a fork.

## Thin CI

**Rule:** CI configuration — YAML or otherwise — only wires jobs;
every behavior lives in scripts or programs testable without a
pipeline.
**Why:** logic in pipeline configuration can't run locally, can't be
unit-tested, and turns every debugging cycle into a pipeline
round-trip.
**How:** if a CI step needs an `if`, a loop, or more than a couple of
lines, it belongs in a script the CI job merely invokes.

## Prefer tested code over clever shell

**Rule:** non-trivial logic belongs in a real, tested language, not
clever shell. Keep new shell to a few lines of glue; no inline
one-liners of another language embedded in a shell script.
**Why:** shell has weak error handling, near-nonexistent testability,
and its subtleties (quoting, subshells, `set -e` edge cases) create
bugs that survive review.
**How:** a shell script that grows conditionals, data structures, or
parsing is a sign to port the logic to a tested language and leave a
thin invocation shell behind.

## Data vs structure

**Rule:** values, names, and configuration are data — discovered or
supplied, never hardcoded. Structural concepts (environments,
pipeline stages, the shape of the system) are deliberate and few, and
change rarely.
**Why:** conflating the two means every new value requires a code
change, and every structural change gets buried in what should have
been a data diff.
**How:** ask, for anything you're about to hardcode, whether it's
naming a *thing* (data — externalize it) or naming the *shape of the
system* (structure — a real, considered decision).

## Derived files are rewritten, not defended

**Rule:** fully derived content is regenerated wholesale; the diff is
the review boundary. Skip warn-and-refuse ceremony around it.
**Why:** a derived file has no independent truth to protect — trying
to preserve or diff-guard it just adds process around something that
has one correct value: whatever generates it produces.
**How:** when a file is fully computable from other committed state
or from applied infrastructure, regenerate it on every run rather than
hand-editing or "protecting" it.

## Names track the design

**Rule:** after fast iteration, do a fresh-eyes naming pass — file
names, symbols, comments say what things ARE now. A stale comment is
a bug.
**Why:** names and comments are load-bearing documentation; once they
drift from what the code does, they actively mislead the next reader
instead of helping.
**How:** when a review or a refactor changes what something does,
check whether its name should change too — don't let "it used to be
called that" survive the thing it named.

## One word per concept

**Rule:** pick a term and use it verbatim everywhere; don't introduce
synonyms, and don't reuse a taken word for a second meaning.
**Why:** a synonym reads as a *different* concept until proven
otherwise, forcing every reader to check; a reused word reads as the
*same* concept until proven otherwise, which is worse.
**How:** the glossary (`docs/glossary.md` unless `AGENTS.md` maps it
elsewhere) is the authority; check it
before naming something new.

## Respect deliberate patterns; open decisions stay open

**Rule:** tighten a chosen design rather than replacing it unasked.
An open decision stays open until a human closes it; never settle one
as a side effect of other work.
**Why:** a pattern that was chosen deliberately usually has reasons
that aren't visible from the diff in front of you; replacing it
without asking discards that reasoning, and quietly resolving an open
question forecloses a decision nobody actually made.
**How:** if a pattern seems wrong, propose changing it explicitly
rather than routing around it. If a question is marked open or
deferred, leave it open even when touching adjacent code, however
tempting a passing answer looks.

## Security by design and defense in depth

**Rule:** a new access, network, or secrets design defaults to least
privilege and layered controls — no single mechanism's failure may
compromise the whole. Name the layers: what each one denies, and what
still holds when it fails.
**Why:** a single boundary is a single point of failure; naming the
layers up front is what turns "we hope this holds" into something you
can actually reason about.
**How:** for any new access path, write down each control in the
chain and what it denies on its own — if removing any one layer would
be catastrophic rather than merely degraded, add another layer.

## Design for cost

**Rule:** weigh a hyperscaler's or vendor's cost behavior when adding
or sizing anything. A cost estimate is part of a design, not a
follow-up.
**Why:** cost decisions made at design time are cheap; cost decisions
discovered after the fact require a redesign under budget pressure.
**How:** for any new resource class, know roughly what it costs and
who pays for it before proposing it, not after it ships.

## A pipeline never depends on a third party being reachable

**Rule:** automated convergence and verification assert facts you
own — your own state, your own committed data — never a partner's or
vendor's live service. A state only a partner can clear is a loud
notice that passes, never a failure.
**Why:** a pipeline that can fail because someone else's service is
briefly unreachable turns an external hiccup into your own outage.
**How:** end-to-end reachability against a third party is a deliberate
manual human step, not something a pipeline probes.
**Exception in this project** (live GitHub backup test, D10): CI runs
a real backup of this repository against GitHub's API with the CI
job's own token. GitHub hosts the pipeline and is the system under
test, so an outage stops both together; a red run caused by GitHub is
rerun, not worked around. This test runs only in CI, never on a
laptop; the offline suite stays credential-free.

## Never-deployed things don't need migrations

**Rule:** for anything not yet live, compat shims, migration paths and
rename machinery are waste — just make the change.
**Why:** migration machinery exists to protect something real that's
already running; building it for something nobody depends on yet is
pure ceremony.
**How:** derive liveness rather than declaring it by hand (a
deployment record, a merge-base check) — and once something genuinely
is live, that's when migration discipline starts to matter.
