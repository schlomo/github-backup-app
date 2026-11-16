# Setup edits: what goes where

Read before drafting. Each file keeps its existing structure; fill it,
don't redesign it. Then remove every template comment (`<!-- ... -->`:
the starter's instruction to whoever fills the file), the
architect-maintained markers included (the list in `AGENTS.md` is the
one authority on which files are architect-maintained), and every
template section the project doesn't use; a section it will fill
later keeps its heading. The project's own comments stay. All of
setup is one seeding change.

## `AGENTS.md`

- Replace the purpose placeholder with the human's one or two sentences.
- Add a "Project setup" section right after the purpose, in this shape:

  ```markdown
  ## Project setup

  Recorded by the setup skill; re-run it when any of this changes.

  - **Starter:** <tag or commit of the starter's source, from `git -C
    <starter tree> describe --tags --always --dirty` | not known>, set
    up <date>.
  - **Git:** <host and repository>, trunk `<branch>`; <squash merges |
    merge commits | linear trunk without squash>, so a branch catches
    up by <merging the trunk in | rebasing while unshared>.
  - **Agent writes:** <push work branches and open draft MRs/PRs |
    commit locally only | nothing without a per-change instruction>.
  - **Attribution:** <AI-written commits name the model as co-author,
    MR/PR descriptions carry a generated-with line | the chosen
    policy>.
  - **Time zone:** <zone>, stated with every time shown to people.
  - **Pipeline:** <what runs on each change>; merging to `<branch>`
    <deploys to X | deploys nothing>. Who may register pipelines and
    edit branch policies: <who | not known>.
  - **Backlog:** <backlog.md | the tracker and project>. Mapping:
    <next-session pointer, in flight, queued, deliberately deferred,
    done>. Access: <how it reaches a command, never a value>.
  - **Environments:** <names, as in the glossary>.
  - **Principles:** `docs/principles/`; a deviation goes through
    "Changing a principle", with an entry in `docs/decisions.md`.
  ```

- In copied mode the starter's source is usually not known: ask once,
  and record "not known" otherwise.
- "Where things are" maps each doc role (architecture doc, decisions
  log, backlog, glossary, troubleshooting log, design docs) to its
  path: the default, or the existing place (`absorb.md`, "Doc roles").
- "Running the tests" and "Facts that bite": filled from the observed
  commands and the absorbed instructions (`absorb.md`; questions.md,
  "Running the tests").
- If the backlog is a tracker, change every mention of `backlog.md` in
  this file to point to it.
- The Claude Code part of this file says what `attribution`
  (`.claude/settings.json`, below) holds: the "`attribution` stays
  unset" sentence while the key is unset, the recorded policy while it
  is set. Whenever setup changes the key, update that sentence, and
  keep its pointer to why only managed settings or a CI trailer check
  enforce it.
- Anything "not known yet" stays in the record as exactly that.

## `docs/architecture.md`

- Title: the product's name.
- Purpose: the human's sentences, under the title.
- Stakeholders line: one entry per role, with who speaks for it.
- "Decisions in force": one short subsection each for delivery (git
  host, pipeline, what merging deploys), work tracking, environments,
  and each organization constraint that shapes the design. State what
  was chosen and why, in a sentence, citing its entry in
  `docs/decisions.md`.
- A mapped architecture doc (`absorb.md`): append the missing sections
  (purpose, stakeholders, decisions in force) at its end; existing text
  is not rewritten.
- If the backlog is a tracker, point the table row and the "Open
  questions" section at it instead of `backlog.md`.

## `docs/decisions.md`

- One entry per decision in force, D1 onwards, dated today, in the
  file's Format: status "in force", the context from the answer, the
  decision, its consequences.
- A mapped decisions log in another format (`absorb.md`): the new
  entries follow that format and numbering.

## `backlog.md`

- Items absorbed from risk lists, TODO or roadmap files, known issues
  and go-live gates are added (`absorb.md`, "Plans and lists").
- If it stays: write "Next session starts here" (setup done, the
  recommended first job), and add every "not known yet" to "Queued" as a
  question naming who could answer it.
- If a tracker replaces it: create the equivalent pinned item there
  only if you have access and the human approved it; otherwise list
  it for the human. Delete `backlog.md`, and change every link to it in
  the repo (search the whole tree, not only the files above).

## `docs/glossary.md`

- Initial terms, one entry each, in the human's words: the product
  name, each environment, each stakeholder role that has a specific
  name here, and domain words the human used that a newcomer would not
  know.
- Don't define general engineering terms; the glossary is for this
  project's own vocabulary.

## `.claude/settings.json`

- An existing file is merged key by key, never overwritten: lists
  unioned, objects merged, hooks kept, and a value both define
  differently asked (the existing value stays until answered). A repo
  that already commits `.claude/settings.json` or `.claude/hooks/` is
  handled this way (`absorb.md`, "Existing `.claude/`").
- `attribution` matches the attribution answer. Not the default: set
  it to the chosen text; to hide attribution entirely, set
  `"commit": ""`, `"pr": ""` and `"sessionUrl": false` under it. The
  default: leave it unset, and remove an `attribution` the project
  already had (the human's answer is the yes to that).
- Why the default leaves it unset: while `attribution` is unset,
  Claude Code adds a co-author trailer naming the model in use to each
  commit and a generated-with line to each MR/PR description, and a
  fixed text could not follow the model. The committed setting
  overrides each person's settings file, but any instruction about
  attribution, a personal one included, outranks the setting unless
  the setting itself is in managed settings. So the setting is a
  default, not an enforced policy: only managed settings, or a CI
  check on commit trailers, enforce it. Tell the human that when they
  answer the attribution question.

## Not touched

- The README (unless none exists, `absorb.md`), other AI tools'
  instruction files, committed session artifacts, and nested
  `CLAUDE.md` files: they stay as they are and are listed for the
  human.
- `docs/principles/`: edited only for a deviation the human stated,
  through "Changing a principle" (SKILL.md step 7).
- Code, pipeline files and settings, except `attribution` above: setup
  records what exists; changing them is later work for an architect
  session.
