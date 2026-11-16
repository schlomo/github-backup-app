---
name: setup
description: "Project setup: ask a human a few plain-language questions, then fit the starter to the project. Works in a freshly copied repo, in an existing repo (with or without AI docs of its own, keeping what is there), and again when the setup changes. Use only when a human explicitly asks."
disable-model-invocation: true
---

# Project setup

You set up a project (a freshly copied starter, or an existing repo
the starter is brought into) so every later session works the same
way. You ask, recommend and draft; the human answers, approves
and merges. Assume no skill level: explain in plain words.

## How to talk

- Plain language. Explain each technical term the first time, in one
  clause ("the trunk: the version of the code that counts").
- One question at a time, each with a recommended answer for their
  situation and a two-sentence trade-off. They can simply say "yes".
- Open with two sentences: setup records a few decisions so that later
  sessions work the same way, and it takes a handful of questions.
- Keep each message short. No tool output, no file dumps.

## Where you are

Resolve this skill's own folder with `realpath "${CLAUDE_SKILL_DIR}"`
(`.claude` may be a symlink); the starter tree is three levels up from
`.claude/skills/setup`. Compare it with the root of the git repository
you run in (`git rev-parse --show-toplevel`):

1. Same folder: copied mode. The starter is already copied here. First
   run or re-run, as below.
2. The starter tree is outside this repo: seed mode. The starter gets
   copied in as part of the approved change (see "Propose, approve,
   write").
3. The starter tree is inside this repo but not its root: this is the
   starter's source repo. Do not set it up. Ask for the target repo's
   path, then give the human the launch steps with both real paths
   filled in, and stop:
   - CLI: `cd <target> && claude --add-dir <starter tree>`, then
     `/setup`.
   - Claude Desktop (Code tab): start a session in the target repo's
     folder, click **+** next to the prompt box, choose **Add
     folder**, and pick the starter tree (or start from a saved
     environment that lists both folders under **Folders**). Send
     any first message, then type `/setup`: until the session has
     started, the `/` menu lists only the main folder's skills.
   - If the target already has a skill named `setup`, this one runs
     as `/<starter tree's folder name>:setup` (needs Claude Code
     v2.1.309 or later).

Not inside a git repository: stop, say setup runs inside the target
repo, and ask the human to open the session there (or make the folder
a git repository first).

Seed mode in a repo whose `AGENTS.md` already has a "Project setup"
section: it was set up before. Updating it from a newer starter isn't
supported yet: say so, name the recorded starter version, and stop; a
re-run uses the repo's own copy of setup.

## Observe, then ask

- Facts you can observe, read yourself and confirm in one line instead
  of asking: the git remote and trunk, pipeline files that exist, an
  existing README, and the survey's results (below). They turn
  questions into confirmations ("Your README says ...; is that still
  the purpose?").
- Everything else is asked ("Ask, don't guess" in the principles): the
  purpose, the people, the tracker, what deploys where, the
  organization's rules, how credentials reach a command.
- Never ask for a secret value, and never write one into a file or
  the chat.

## Before the first question

1. Read the root instruction file (`AGENTS.md`) and the docs it maps:
   the architecture doc, the headers of the backlog, and the glossary.
   In seed mode, read the target repo's own files instead, and read
   `<starter tree>/AGENTS.md` (Guardrails, Principles, Where things
   are) before the survey: absorbing compares every existing
   instruction against them, and an added folder's `AGENTS.md` is never
   loaded on its own.
2. If `AGENTS.md` already has a "Project setup" section in copied
   mode, this is a re-run: show the recorded answers in a few lines,
   ask what changed, and ask only about that.
3. Survey: unless the repo holds nothing but the starter's own files,
   read `references/absorb.md` first, then delegate the survey with
   the brief in it to the `locator` agent; if the project already has
   its own agent named `locator`, use a general-purpose agent on the
   standard tier with the same brief.
4. Observe what you can (above) so your questions confirm rather than
   interrogate.
5. Check for names shared with the starter's (skills `architect` and
   `setup`, the agents under the starter's `.claude/agents/`; a
   command's name is its file name without `.md`). A personal skill
   beats the project's, and a personal command may too (`ls
   ~/.claude/skills ~/.claude/commands 2>/dev/null`), so one that
   matches can silently shadow the starter's: tell the human and
   suggest renaming the personal one.
   Personal agents are not checked, because a project agent beats a
   personal one. In seed mode, the project's own skills, agents and
   commands (`.claude/skills/`, `.claude/agents/`, `.claude/commands/`)
   are checked too; a match is asked, per `references/absorb.md`. In
   copied mode, a definition with a starter name there is the
   starter's own file.

## The questions, in this order

Read `references/questions.md` before asking the first one. It has, per
question, the plain wording, the recommended default by situation, and
the trade-off.

1. **Product and purpose**: what it does, for whom, what success looks
   like.
2. **Stakeholders**: who uses it, operates it, is responsible for its
   security, pays for it, and is legally affected.
3. **Git host, trunk and merge method**.
4. **Pipeline**: what runs on each change, what merging deploys, and
   where.
5. **Where work and project management lives**: issues on the git host,
   the default `backlog.md`, Jira, or another tracker. This matters
   most: from now on "the backlog" means this place.
6. **Environments**: where the software runs (for example only on a
   laptop, or a test system and production).
7. **Organization constraints**: rules the project must follow (data
   protection, approved vendors or hosting, security policies,
   budget, licenses).
8. **How far agents write to the repo**: push branches and open draft
   MRs/PRs, commit locally only, or nothing without a per-change
   instruction.
9. **Commit attribution**: whether AI-written commits and MRs/PRs say
   so.
10. **Time zone** for times shown to people.

Last, ask whether the project deliberately differs from any of its
principles. Only the human can say so; don't suggest deviations.

## Propose, approve, write

1. Draft every change first. Read `references/edits.md` for what goes
   where in each file.
2. Show the human a summary: one line per file, what changes, in plain
   language, plus anything recorded as "not known yet". In seed mode it
   also lists the starter files to be copied and each one merged
   instead of copied. For every existing file absorbed, it says where
   its content went. Ask for approval or corrections. Write nothing
   before they approve.
3. Before writing anything, switch to a new work branch, unless the
   session already runs on one. Without a remote, the branch stays
   local for the human to merge. The one exception is a repo with no
   commits yet: there the change becomes the first commit, made only
   after approval.
4. In seed mode, copy the starter in now, never overwriting: a
   destination that exists is merged per `references/absorb.md`, and
   a doc role mapped to an existing place gets no starter template.
5. Apply the approved changes to:
   - `AGENTS.md`: the purpose line and a "Project setup" record section;
   - `docs/architecture.md`: purpose, stakeholders, decisions in force;
   - `docs/decisions.md`: one dated entry per decision in force;
   - `backlog.md`: seeded, or removed with every link pointing to the
     chosen tracker instead;
   - `docs/glossary.md`: initial terms;
   - `.claude/settings.json`: `attribution`, made to match the
     attribution answer (`references/edits.md`);
   - the content absorbed from existing files, per `references/absorb.md`.

   In copied mode, a doc role mapped to an existing place has its
   unfilled template removed. In both modes, every link to a mapped
   role's default path is repointed (search the whole tree).
6. Remove every template comment (`<!-- ... -->`: the starter's
   instruction to whoever fills the file, such as a `Fill in:` line),
   the architect-maintained markers included, and every template
   section the project doesn't use. Filled content stays, and so do
   the project's own comments.
7. A deviation the human stated is a principle change: follow
   "Changing a principle" in `docs/principles/ai-working-process.md`
   (the principle, its line in `AGENTS.md` and an entry in
   `docs/decisions.md`, in one change).
8. Check your own result: every relative link in the changed files
   resolves; in `AGENTS.md`, `backlog.md` if it stays, and each file
   under `docs/` this change created or changed, every comment
   `grep -n '<!--'` finds is the project's own, none a template
   comment; no answer appears that the human did not give;
   and nothing existing was overwritten or deleted without the
   human's yes.
9. Commit the change on that branch. Push it and open a draft MR/PR
   only at the write level chosen in question 8; otherwise tell the
   human it is committed and waiting for their push.

## Finish

Report in under 10 lines: what was recorded, what is still "not known
yet" and who could answer it, and the next step. The next step is
usually an architect session, which works from what you recorded.
Add anything flagged for the human: committed session artifacts, other
tools' instruction files, conflicting instructions.
