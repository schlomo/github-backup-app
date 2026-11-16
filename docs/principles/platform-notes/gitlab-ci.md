# Platform notes: GitLab CI

- **A job token authenticates git and pipeline-scoped state, but 404s
  on general project/group API endpoints.** A GitLab CI job token can
  read/write its own project's git and Terraform-style state, but
  calls like user lookup, protected-branch settings, or cross-project
  merge-request create/accept fail — typically as a **404**, not a
  401/403. A 404 from a project-scoped API call is a candidate
  *credential* problem before it's a candidate *routing* problem.
  Anything driving the platform's own API, or pushing to another
  project, needs a real token (personal/project/group access token),
  never the ambient job token.
- **A job that consumes no artifacts should say so explicitly**
  (GitLab: `dependencies: []`). Left to the default, a job downloads
  every artifact from every earlier stage, and a missing or expired
  one is a hard job failure with an opaque reason — this bites hardest
  when a downstream job's wall-clock start drifts past an upstream
  credential's short TTL. A job that legitimately needs specific
  upstream artifacts scopes them explicitly (`needs:`) rather than
  inheriting the full default set.
- **A pipeline STAGE is a hard failure boundary — a job's own
  dependency declaration is not.** A failed job skips every job in a
  *later stage* regardless of whether that later job's own
  dependencies are satisfied. An app-level or slow gate that must never
  block an unrelated pipeline needs its own stage placed *after*
  everything it must not block; ordering among jobs that gate legitimately
  owns is still expressed by the dependency graph, which most CI
  systems honor independent of stage placement.
- **Retrying a single job never re-runs its predecessor.** If job B
  consumes a credential or artifact minted by job A, retrying B alone
  reuses A's original output — including a short-lived credential that
  may already be stale. Re-run the whole pipeline, not the failed leg
  alone, whenever a paired producer/consumer job is involved.
- **A merge/PR API response's "current commit" field is not
  necessarily what actually landed**, under a squash-and-fast-forward
  merge strategy: the source branch's tip commit is garbage-collected
  the moment the branch is deleted post-merge, and a squash commit's
  SHA is a *different* field in the API response. A script handing a
  downstream gate a commit SHA to poll for must resolve the actual
  landed commit (the squash/merge SHA, checked as an ancestor of the
  live trunk) and prove it exists before handing it over — otherwise
  the downstream gate burns its entire timeout waiting for a commit
  that was never real.
- **A platform's own UI/API state can be stale or briefly
  inconsistent under load** — a compare view showing changes for
  identical content, a request state that hasn't caught up with reality.
  When the platform's web API and git protocol disagree, git is the
  arbiter: fetch and compare tree hashes or do a real `git diff`
  rather than trusting a compare/status API view.
- **A shared, name-addressed side channel used to carry a verdict
  (e.g. a commit status) needs its writer authenticated, not just the
  report matched by name.** A flat namespace keyed on (subject, name)
  trusts "somebody with write access asserted this" — match on the
  authenticated reporter identity too, so a stale or decommissioned
  reporter can be revoked rather than silently trusted forever.
- **Templating a file into a CLI flag to build a review description
  is fragile** — shell quoting can turn `$(cat file)` into a literal
  string instead of its content; this is why a generated description
  is read back ("Work branches" in
  [../ai-working-process.md](../ai-working-process.md)).
