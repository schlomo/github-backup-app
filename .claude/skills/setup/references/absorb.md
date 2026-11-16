# Absorb existing content

Read before the survey: it holds the survey's brief, and how existing
content is absorbed once the survey is back. The rule: the
project's existing layout wins and the starter fills the gaps. Nothing
is overwritten or deleted without the human's yes, and every absorbed
file appears in the summary with where its content went.

## Survey brief

Give this to the `locator` agent (or the general-purpose stand-in, see
SKILL.md). Completion discipline first: run everything in the
foreground; do not start a background watch and end the turn waiting on
a notification; if something backgrounds anyway, collect it now and
finish.

> Read-only. Report facts with file paths, no recommendations, in about
> 40 lines at most:
>
> 1. Purpose draft: the README's own words, quoted, with its file.
> 2. Languages, package managers, build and test commands (manifests,
>    Makefile, scripts, pipeline files).
> 3. Pipeline files: what each runs on a change and on merge, and what
>    deploys where, as the files say.
> 4. Runtime and deployment hints: container files, compose,
>    infrastructure code, environment names in config.
> 5. Docs inventory: each doc file or folder with its likely role
>    (architecture doc, decisions log, backlog-like list, glossary,
>    troubleshooting log, runbook, other).
> 6. AI instructions inventory: `CLAUDE.md` at any level, `AGENTS.md`,
>    `.claude/` contents (settings keys, hooks, agents, skills,
>    commands, rules), other AI tools' instruction files (for example
>    `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`,
>    `GEMINI.md`). "None" is a normal answer.
> 7. Committed session artifacts: plans, specs, verification reports,
>    migration plans, log archives, transcripts.
> 8. Git: remote host, default branch, merge style seen in the last
>    ~50 trunk commits, number of distinct authors in the last 90 days,
>    tracker hints in commit messages and branch names (issue keys,
>    issue numbers, tracker URLs).

## A plain repo (no AI docs)

This is the common case. There is nothing to absorb from AI files; the
survey still drives the questions, and the docs that exist (README,
docs folder, wiki pointers) are mapped as under "Doc roles".

## Doc roles

The roles are: architecture doc, decisions log, backlog, glossary,
troubleshooting log, design docs.

- An existing file or folder that plays a role is mapped in `AGENTS.md`
  "Where things are" with its path and, for the decisions log, its
  format. No duplicate is created: in seed mode the starter's template
  is not copied, in copied mode its unfilled template is removed.
- Existing decision records in another format (for example one file
  per decision) stay the decisions log; setup's new entries follow that
  format and numbering.
- A mapped architecture doc gets setup's missing sections (purpose,
  stakeholders, decisions in force) appended at its end; existing text
  is not rewritten.
- A role nothing plays gets the starter's template.
- A role only partly covered inside another file (an architecture
  section in the README) is not split out: the starter template is
  created and links to that section.

## README

Never edited; read for the purpose draft. Only when none exists, setup
drafts one with purpose and concepts only, never worked examples it
cannot observe.

## Existing `CLAUDE.md` and `AGENTS.md`

Each instruction is sorted into the starter's `AGENTS.md`: the purpose
line, "Where things are", "Running the tests", or "Facts that bite".
For a fact, follow the placeholder comment there: the headline in the
root file and the full text in the area's path-scoped rule file in
`.claude/rules/`, except an action-triggered fact, kept in full in the
root. An instruction a guardrail or principle already covers is not
repeated; the summary names what covers it. The starter's Guardrails
and Principles sections stay verbatim.
A convention for one area of the tree goes to that area's rule file in
`.claude/rules/`. A short repo-wide convention (for example "run
`make fmt` before committing") stays in the root under "Facts that
bite", in full, like an action-triggered fact; a long one (a style
guide) stays a doc of its own, listed in "Where things are", so the
always-loaded file stays small. The root `CLAUDE.md` becomes the
starter's (`@AGENTS.md`). Nested `CLAUDE.md` files in subdirectories
and `CLAUDE.local.md` stay where they are and are listed.

## Conflicting instructions

An existing instruction that contradicts a guardrail or principle (for
example "push straight to the trunk") is neither kept nor dropped
silently. It is quoted in the deviations question. Kept means a
principle change through "Changing a principle"; dropped means it is
listed as removed in the summary.

## Other AI tools' instruction files

Their facts are absorbed as above. The files stay in place and are
listed for the human, who may later replace them with a pointer to
`AGENTS.md`.

## Existing `.claude/`

- `settings.json` is merged key by key: lists are unioned, objects are
  merged, and a value both define differently is asked (the existing
  value stays until answered). Hooks are kept. An existing
  `attribution` follows the attribution answer (`edits.md`).
- A clash between an existing agent, skill or command name and the
  starter's is asked. Recommended answer: rename the project's own one,
  because the working model's docs call its agents and skills by name.

## Other files at the same path

This applies file by file. When the project already has a file at a
path the starter would copy to (for example its own
`.claude/rules/README.md`, `docs/design/README.md` or a file in
`docs/principles/`), the project's file stays and the starter's is not
copied; the starter's other files in that folder are still copied. The
file is listed for the human with what the starter's version would
add, and the human is asked whether to merge it. If `AGENTS.md` links
to that path (the principles do), the link now leads to the project's
file: say so in the same item.

## Plans and lists

Risk lists, TODO or roadmap files, known issues and go-live gates: their
items go into the backlog. The source file stays and is listed.

## Committed session artifacts

Flagged for the human ("Specs and plans are not repo content" in the
AI working process principles), never deleted by setup.
