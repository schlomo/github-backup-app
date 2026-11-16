# Context economy

What AI-assisted work costs is set by how much context each call
carries and how many calls there are. These principles keep both
small. Each states a rule, why it matters, and how to apply it; the
figures in them were measured on real AI-assisted engineering work.
The per-tool settings that implement them live in the root instruction
file (`AGENTS.md`); the choice of model tier is in
[ai-working-process.md](ai-working-process.md) ("Delegation").

## Always-loaded context is paid on every call

**Rule:** the root instruction file, everything it imports, and every
always-loaded agent or skill definition stay small and point to detail
instead of containing it. Detail loads on demand: a path-scoped rule
that applies to one area of the tree, or a doc read when a task needs
that topic. Tool, MCP-server and plugin listings are always-loaded
too: a project enables only the servers and plugins it uses.
**Why:** always-loaded context enters every session and every
subagent that does work, and is re-read on every turn of each. Output
tokens were about a quarter of a percent of all tokens moved — the
bill is context re-read, and the always-loaded part is paid before any
work starts. One always-loaded instruction file grew to about 32k
tokens before it was cut. Moving each fact's body from a root
instruction file into path-scoped files, headlines kept in the root,
cut that file by about two thirds, an architect kickoff's context from
about 176k to 96k tokens and the session's summed context by about 58
percent, with answers equally correct (5 of 5). A session in an empty
folder already started at about 54k tokens of system prompt, tool and
plugin listings before any project file; neither its split between
system prompt, tools and the user's own plugin and MCP listings nor
what disabling unused ones saves is measured.
**How:** a reference (a path in backticks, a markdown link) is read
on demand; an import directive is always-loaded — import only what
every session needs. The root instruction file holds the guardrails,
one line per principle, pointers and the per-tool settings. Rules for
one area go to path-scoped rule files (this project's are under
`.claude/rules/`, whose README says when they load); a delegated
agent reads the ones its brief names. A principle, a design or a
platform note is its own file, opened when the topic comes up. A
change to what agents read, or to when they read it (a rule, a fact, a
path scope, a memory file), says in its proposal which consumers it
reaches (the main session, a subagent in the session, an agent in a
separate clone, a session in another repo), what it costs per load,
and what keeps it true. A rule that only an agent's memory keeps true
goes into the project's AI docs or the working model (where every agent
reads it), is tied to the file it protects, or is dropped. It is not
enforced by a new script.

## Read the part, not the whole

**Rule:** read the section a task depends on, not the file "to be
safe". A session kickoff reads headers and pointers, not whole
files. Reading the primary source stays the rule for anything that
drives a decision — but only the part that drives it.
**Why:** everything that enters a session is re-read on every later
turn of that session. The largest contributors to context measured
were file reads and command output, and one session kickoff that
read whole docs cost about 155k tokens before any task work began.
One kickoff of 7 tool calls ran 13 model calls, each re-reading the
whole context, about 1.26M tokens summed — so compact command output
(boilerplate stripped, lists filtered) is a lever; its byte savings
were measured, its effect on a session was not.
**How:** the backlog, the architecture doc and design docs keep
section headers that say on their own whether the section is worth
opening; the architect kickoff reads the backlog's headers, its
"Deliberately deferred" list and its "Next session starts here"
pointer, nothing more. Search for the section, then read that range.
Ask commands for structured, filtered output rather than a full dump.

## Dumps go to a subagent; conclusions come back

**Rule:** work whose value is its result, not its narration — a sweep
of the tree, a build, a review, an analysis — runs in a subagent whose
report is the result alone; the delegating session consumes the
conclusion.
Large raw output never lands in a thread that will continue.
**Why:** a dump in the delegating session is paid again on every
following turn; the same dump in a subagent is paid once and ends with
it. Subagents were about seventy percent of all tokens measured, so
what they load and how long they run matters as much as the main
thread does.
**How:** narrow-lane agents (locate, build, review, analyze, docs)
with model and effort pinned in their definition and a fixed report
shape. One precise brief rather than several corrections: a
correction is paid in the full context of both the agent and the
delegating session.

## Restarting is cheap, so sessions stay short

**Rule:** durable state lives in files a fresh session reads quickly
— the backlog's "Next session starts here", the architecture doc,
design docs, the review description — never only in a running
session's memory. A session ends when its job is done or its context
has grown large, and it compacts well before its window is full.
**Why:** a long session carries everything it has read on every call;
nearly all main-thread tokens measured came from sessions longer than
thirty turns. On a one-million-token window, compacting at about forty
percent instead of near the top halved the mean context per
main-thread call (from about 470k to about 240k tokens) and with it
the main thread's cost per turn; compactions stayed rare (under one
percent of calls) and each cost one call. If restarting is expensive,
there is pressure to keep one session running indefinitely — the
costliest shape there is.
**How:** rewrite the next-session pointer at every milestone; suggest
a fresh session when the job changes or the context grows large; set
the compaction threshold in the committed project settings (the
value per tool is in the root instruction file), so a session's
history is condensed early rather than carried to the limit.

## The repo is shared truth; auto-memory is personal

**Rule:** where an agent's auto-memory and the repo differ, the repo
wins. Auto-memory holds only what is true for one person or one
machine (a laptop's setup, a personal preference); anything the team
needs is moved into the repo before the session ends. The backlog,
never always-loaded context, is where task status goes. Auto-memory is
never pointed into the working copy.
**Why:** each person and each machine grows its own memory, so
without a precedence rule the shared truth forks. No other person or
tool reads it, and in Claude Code a subagent doesn't get the
session's auto-memory either, so a team rule kept only there reaches
almost nobody. Status kept in always-loaded context is paid on every
call and goes stale there. Memory pointed into the working copy puts
agent-written files that nobody reviewed into shared git, or leaves
notes stranded in a directory on one host that no one else sees.
**How:** promote a team lesson to its place in the repo (a
path-scoped rule, a platform note, a principle, the backlog) and drop
the memory copy. In Claude Code, never set `autoMemoryDirectory` to a
path inside the working copy, and never give a subagent
`memory: project` or `memory: local`, which both write under the
working copy's `.claude/`; `memory: user` stays outside it.

## Shrink and skip; never compress

**Rule:** cost comes down by loading less and calling less — never by
rewriting or compressing what is already being sent.
**Why:** replayed against real sessions, a request-compressing proxy
reduced request bodies by a fraction of a percent; in a live
comparison on a fixed task the compressed arm used over three times
the cache-read tokens, nearly three times the output tokens, more
turns and about three times the wall time — the model saw the
compression markers and spent turns re-verifying content it no longer
trusted. Terser output targets the quarter of a percent that is
output tokens.
**How:** no compressing or rewriting proxy in the request path. The
levers are the ones above: what is loaded, what is read, what is
delegated, how long a session runs.

## Levers are committed and team-wide

**Rule:** a context-cost lever lives in a committed project file or an
organization-managed setting, so the whole team gets it by default.
No personal tooling around the agent's internals.
**Why:** a lever one person installs helps one person and is never
reviewed with the project; a committed one is measured once and holds
for everyone.
**How:** the settings file, the agent definitions (pinned model and
effort), the path-scoped rules and the root instruction file are the
places. A committed project setting overrides each person's
user-level one; a personal value goes in a personal, uncommitted
project-local setting, which wins over the shared project file (the
file per tool is in the root instruction file). A personal setting is
for trialling a lever before proposing it. Every proposal names where
it is configured.
