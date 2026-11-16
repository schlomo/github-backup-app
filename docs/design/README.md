# Design docs

One file per subsystem or cross-cutting decision that needs more room
than `../architecture.md` gives it — a data model, a delivery
mechanism, a security boundary, anything a later change needs to
understand in depth before touching it.

A design doc is **durable**: written once a decision is real, kept
current as the system evolves, referenced across many future changes.
It is not a session's spec or plan (those are working documents, never
committed — see `../principles/ai-working-process.md`'s "Specs and plans
are not repo content"), and it is not a narrated history of how the
decision was reached (the decision itself gets a dated entry in
[../decisions.md](../decisions.md)).

Before writing a new design doc, check whether an existing one already
covers the territory — including one that was deferred rather than
rejected — and, for tooling, what the ecosystem's native options and
the team's sibling repos (other repos the team owns) already offer.
Reviving and amending an existing doc is the default over starting a
parallel one.

Suggested shape for a new design doc:

1. **What this covers** — one paragraph.
2. **The decision** — what was chosen, stated plainly.
3. **Why** — the reasoning, briefly; enough for someone to judge
   whether it still holds later, not a full discussion transcript.
4. **What this doesn't cover / explicitly rejected alternatives** — a
   rejected option is exactly what the next person is likely to
   propose again; naming it here saves that round-trip.
5. **Open questions**, if any — or a pointer to where they're tracked.
