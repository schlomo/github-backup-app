---
paths:
  - ".claude/rules/**"
---

# Path-scoped rules

The root instruction file (`AGENTS.md`) is always loaded, so it stays
small (see `../../docs/principles/context-economy.md`). A rule that
only matters for one area of the tree (a subsystem's own
conventions, a language-specific style rule, a directory with unusual
constraints) does not belong there; it belongs in a path-scoped rule
instead, so it's loaded only when it's actually relevant.

A rule file without a `paths` header loads in every session, so only
a rule that truly applies everywhere omits it; this README has one, so
it loads only when a rule file is read or edited.

Claude Code loads rule files scoped by path under `.claude/rules/`;
other tools have their own mechanism. Claude Code documents that a
rule loads once the session's file tools (read, write, edit) touch a
file the rule's paths match. Beyond that:

- a read through a shell command has been observed both to load a
  matching rule and not to, depending on the command and the tool
  version; this is undocumented;
- in another copy of the repo, such as a delegated agent's own clone,
  no rule was observed to load;
- a subagent gets the starting session's instructions, not those of
  its working directory.

So never rely on a rule loading by itself: read the area's rule file
yourself before you work there, and a brief names, by path, the
rule files of the area its task touches for the agent to read (Brief
anatomy in `../../docs/principles/ai-working-process.md`).

Give a rule the narrowest path pattern that is its area (`ci/**`,
`**/*.tf`, `docs/design/<topic>*`), never a list of single files (the
next file of that kind is missed). A pattern that spans unrelated
areas is a catch-all: with `docs/**`, every doc read loads the rule. A
doc that names every area's terms, such as an architecture doc or a
backlog, stays out of every rule's paths, or each read of it loads
them all. The cost adds up across rules: four 20 KB rules all matching
`docs/**` can put 80 KB into the context of a docs-only task (a sum
of file sizes, so an upper bound).

The principle, regardless of mechanism:

- One rule file per scope that genuinely needs its own conventions —
  not one file per tiny fact; a handful of related rules for the same
  area belong together.
- State the rule the same way `../../docs/principles/engineering.md`
  does: a short rule, why it matters if it's not obvious, how to apply
  it.
- If a rule turns out to apply everywhere, it doesn't belong here
  either — promote it into the root `AGENTS.md`, or into
  `docs/principles/` if it is a principle (through "Changing a
  principle").
