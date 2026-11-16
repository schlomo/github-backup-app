# Delegation: heuristics, models, briefs

Read before the first delegation of a session, before writing any
brief, and whenever you choose inline vs background, resume vs spawn,
or a model. The objectives, the four tiers and when to pick the top
tier are in "Delegation" of the AI working process principles; this
file adds how to apply them.

## Heuristics

- **Inline vs background.** A one-off probe or a lookup you can answer
  directly stays inline: an agent's spin-up would cost more than the
  task. An open-ended investigation sweep, or building an artifact (a
  patch, a doc rewrite, bookkeeping), goes to a background agent,
  especially while a human is live. Background hides the spin-up
  cost exactly when someone is waiting on you. Tool output is re-read
  every turn, so a dump in the delegating session's context is paid
  for again and again.
- **Resume vs spawn.** A follow-up in an area an agent already worked
  resumes that agent: cheaper, and more likely right first time. Spawn
  fresh when the area has moved on or the old context would mislead.
- **Brief quality is the lever.** A precise brief lets a lower tier do
  the job, so invest in the brief first. A narrow-lane agent runs on
  its pinned model and effort; override the model only to raise the
  tier, with the reason in one line; or, where the pinned model isn't
  available to the project, to name the highest tier that is (the
  reviewer's top-tier pin, for example); or, for a delta review, to
  lower it to the standard tier. A tier above a human's per-project
  cap counts as not available. A general-purpose or built-in agent has
  no pin: give it an explicit model every time.
- **Model and effort, in Claude Code.** A narrow-lane agent pins
  `model` and `effort` (`low|medium|high|xhigh|max`) in its
  frontmatter, so its effort doesn't drift with the session's. A
  delegation call sets only the model: the call's `model` (e.g.
  `fable` for analyst, `sonnet` for the reviewer's delta review) beats
  the pinned one and stays on resume, while the pinned `effort` still
  applies — so per delegation the lever is the model. The session's
  effort is a human's setting (`/effort`, or `effortLevel` in
  settings; Opus defaults to `medium`): when the session's problem is
  depth, recommend `/effort high` or `xhigh`. For depth on one open
  question without changing the session's effort, delegate to analyst.
- **Prefer a narrow-lane agent when the task shape fits.** Locate,
  build, review, docs and analysis agents whose reports are the
  result alone save the delegating session's context on work whose
  value is the result, not the narration. Fall back to a
  general-purpose agent the moment the task needs judgment outside the
  lane; narrow agents refuse out-of-lane scope by design.
- **Fewer, precisely briefed agents over many small ones.** Rework is
  what burns budget, and on a metered plan it can hit a limit mid-task.
  A precise brief is cheaper than a correction.
- **Verification is what makes cheap delegation safe.** A cheap model's
  mistake is caught before it is presented as done, not after.

## Briefs and verification

Every brief states the eight points of "Brief anatomy" in the AI
working process principles, in order. Verify what comes back as
"Verify before declaring ready" there says.

A review brief also follows the closing paragraph of "Brief anatomy":
it names the commit under review and the gates already green, asks
open questions, and never states a constraint as the frame the answer
must fit. A review runs once per settled change, a set of related
MRs/PRs as one, and its delta review is the same reviewer called with
`model: sonnet` ("Every change gets an adversarial review").
