# Platform notes: Kubernetes / ArgoCD

- **A CNI's NetworkPolicy engine can fail a policy closed on an
  unsupported rule shape, silently.** An unsupported selector (e.g. an
  empty `namespaceSelector: {}`) can kill *every* rule in that policy
  rather than just being ignored, leaving the pod at deny-all — and
  the resulting symptom (a downstream connection timing out) looks
  like an auth or DNS problem, not a network-policy problem. If a
  chart's default NetworkPolicy behavior is suspect, verify the
  actual enforcement (a live connection test from inside the mesh),
  don't just review the manifest for plausibility.
- **A CRD's structural-schema defaulting only descends into objects
  that are present.** A child field's documented default is never
  applied if its parent object is entirely absent from the manifest —
  so a "sensible default" claim in a CRD's docs can be silently
  useless if you omit the parent object rather than providing it
  empty. When a resource behaves as if a documented default didn't
  apply, check whether the parent object was omitted, not just
  whether the field itself was.
- **A silently discarded/ignored field produces an error that names
  the wrong subsystem.** A field the tooling drops rather than rejects
  (wrong URL scheme, an incompatible source-type combination) tends to
  surface as an authentication or permissions error downstream, which
  sends debugging effort at credentials instead of the actual
  malformed request. Before touching auth, tokens, or visibility
  settings on a "permission denied"-shaped failure, confirm the
  request being made is actually the one you intended — read the
  resolved URL/fields, not just the error text.
- **ArgoCD's (or any GitOps controller's) generator/apply gating has
  real gaps worth knowing before building a promotion gate on it:** a
  generator that reads git continuously at its own revision can bypass
  a pin applied only to one resulting object; a multi-source
  application doesn't always populate the single-revision status field
  a status-based gate might expect (only a multi-value revisions
  field); a manual sync usually does *not* prune by default; and
  self-heal reconciles toward the configured target reference (e.g.
  branch HEAD), never toward "the last version a gate approved" —
  turning it on for something meant to be gated un-gates it instantly.
- **A gate's timeout is an availability policy, not a progress
  deadline.** Set it against how long the thing being gated on may
  plausibly be unavailable and still recover on its own — not against
  a container orchestrator's own default rollout deadline, which is
  usually much shorter than a real outage-and-recovery window. Two
  companions: prefer a narrow terminal-failure condition (an outright
  refused request) over a broad one (any failure state), since a
  broad match can kill a promotion that was about to self-heal; and
  budget the timeout for the *failing* case, not the typical
  successful one — the two can differ by an order of magnitude.
- **A cluster's API server being reachable only from inside its own
  network is a design constraint that ripples outward.** If CI/CD
  automation can't reach the cluster API directly, in-cluster objects
  (secrets, RBAC, agents) need to be created through whatever
  control-plane-mediated path the platform offers (e.g. a
  provider-managed "install this chart into the cluster" API) instead
  of a direct client. This shapes the whole delivery model, not just
  one resource.
