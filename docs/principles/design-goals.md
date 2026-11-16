# Design goals

The aim: the best working setup for humans and AI agents as
coworkers. The six goals below serve it, for the humans and the
agents alike. They add no rule of their own: each one names the
principles that carry it, and those principles hold the detail.
Where cost and correctness pull apart, correctness wins
("Delegation" in [ai-working-process.md](ai-working-process.md)). A
goal changes only through "Changing a principle" there.

## 1. Quality first

Nothing is ready on a claim: tests and CI gate every change, results
are verified against what actually happened, and every change is
reviewed adversarially. Carried by "Test first"
([engineering.md](engineering.md)), "Verify before declaring ready"
and "Every change gets an adversarial review".

- **Human:** accept "done" only with its evidence, and expect to hear
  UNVERIFIED or UNREVIEWED until there is some.
- **Agent:** report evidence, not intent, and say UNVERIFIED or
  UNREVIEWED until the check has run and the review loop has ended.

## 2. The human decides and merges

Agents recommend; humans decide. Carried by "Roles", "Only a human
merges", "Live systems need a human's go-ahead", "Ask, don't guess"
and "Agree the design before anyone builds it".

- **Human:** make the decisions, a design's sign-off as text before it
  is built included, do the merging, and give or refuse each go-ahead
  for a live system or a paid run.
- **Agent:** recommend and ask; never merge, never touch a live system
  or spend money without a go-ahead, never guess what only a human
  knows, never build a design a human has not signed off.

## 3. Cost-aware by design

Cost is weighed when something is designed, not discovered afterwards,
and a new tool, gate or process step is weighed the same way. Carried
by "Delegation" (the cheapest adequate tier per job, the top tier for
the one review of a settled change and for novel design), the
[context economy](context-economy.md) principles (a small, budgeted
always-loaded context), "Run a test suite once per meaningful change"
in "Verify before declaring ready", decisions batched at milestones
(the architect skill), "Design for cost" and "Agree the design before
anyone builds it" (the test a tool, gate or process step must pass,
and the ecosystem's native option before a custom tool).

- **Human:** keep the always-loaded file small, set cost levers in
  committed settings, answer decisions in batches, and ask of a new
  tool or gate which mistake it catches.
- **Agent:** pick the cheapest tier that does the job well, load and
  read only what the task needs, run a suite once per meaningful
  change, batch questions rather than interrupt, and hold a new tool,
  gate or process step to the test in "Agree the design before anyone
  builds it" before proposing it.

## 4. Transparent

Anyone can see who or what made a change, and why. Humans review a
change through its MR/PR description rather than its code, so the
description's honesty and quality are key. Carried by the append-only
[decisions log](../decisions.md), MR/PR descriptions written as the
human's review surface and attribution of agent-written work ("Work
branches"), the review of each description against its diff ("Every
change gets an adversarial review"), and evidence labels ("Verify
before declaring ready").

- **Human:** record every decision and ruling with its date, and
  review through the MR/PR description, which is written for you.
- **Agent:** mark what it wrote; write the MR/PR description as the
  human's review surface (honest, complete, current with the diff);
  as the reviewer, check every claim in it against the diff; say how
  each claim about a system is known.

## 5. The tested procedure IS the shipped procedure

What runs in tests is what runs in production, and re-running it is
safe. Carried by "The tested procedure IS the shipped procedure",
"Thin CI" and "Test first" ([engineering.md](engineering.md)).

- **Human:** refuse a test-only code path or a pipeline step nobody
  can run locally.
- **Agent:** test the code that ships, through its real entry point,
  and keep every procedure safe to run again.

## 6. Portable and tool-neutral

The working model is tied to no single tool, machine or person.
Carried by `AGENTS.md` as the one instruction file every tool reads,
"Levers are committed and team-wide" and "The repo is shared truth;
auto-memory is personal" ([context-economy.md](context-economy.md)).

- **Human:** put shared settings in committed files, and keep personal
  and machine-specific facts out of the repo.
- **Agent:** write instructions where every tool reads them, and
  depend on nothing that exists only on one person's machine.
