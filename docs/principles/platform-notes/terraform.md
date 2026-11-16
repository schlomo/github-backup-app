# Platform notes: Terraform

- **`||` does not short-circuit against a null attribute access.**
  `var.x == null || var.x.some_attribute == "y"` still evaluates the
  right operand and fails with "attempt to get attribute from null
  value" even when the left side is already true. Guard a nullable
  object with a ternary (`var.x == null ? default : var.x.attribute`),
  or use `can(...)`, which genuinely swallows the error — never the
  `||` form. This is version-dependent (some versions fail loudly,
  newer ones may pass silently), which makes it easy to miss in local
  testing and only surface in CI on a different version.
- **`output -json` silently drops a null-valued entry**, and
  `one([])` returns `null` rather than erroring — so `try(one(...),
  "")` is dead code, since `one([])` already returns `null` before
  `try()` ever sees an error to catch. Model an "absent" cross-layer
  value as an explicit empty-string sentinel via a real conditional,
  not by relying on null propagation through these functions.
- **An unpinned, "latest" internal module means a plan can change with
  no local edit at all.** If module versions are deliberately left
  unpinned, `terraform init -upgrade` (run on every plan) can pick up
  a new module version mid-session — a new default value published
  upstream becomes every consumer's new desired state with no review
  of that specific change. A published module's own contract should
  treat a **changed default** as a breaking change (needs an opt-in),
  even though a brand new variable is safe for existing callers. On
  the consuming side, read an unexpected non-empty plan as
  "possibly not my change" before hunting for drift in your own diff.
- **The same commit can produce two different desired states within
  one pipeline run**, when an unpinned module publishes mid-pipeline.
  This is expected behavior under an unpinned-module design, not
  drift to chase — treat it as a re-run signal, not a mystery.
- **`terraform{}` / `required_providers{}` must be written multi-line**
  — nested blocks cannot go on one line.
- **A module's own input validation is not a substitute for a
  mechanical pre-check run before any state-changing operation.**
  Overlapping checks in two places (a fast pre-flight lint with no
  state/credentials needed, and the module's own `precondition`/
  validation blocks) are deliberate, not redundant: the lint catches
  mistakes before any cost is incurred and works even when someone
  runs the tool by hand outside the normal pipeline; the module-level
  check is the hard stop that fires regardless of how it's invoked.
- **A cloud-managed catalog entry can be deleted from Terraform's view
  but still be listed by the provider's own API** — a resource that
  Terraform's refresh reports as gone can still collide on next
  create, or 404 on an adopt-by-id download. Don't assume "Terraform
  doesn't see it" means "the provider doesn't see it either."
- **A provider that refuses an in-place update on a field forces
  destroy+create, which detaches the resource from anything bound to
  it for the duration** — know which fields on a live resource are
  update-in-place versus destroy-and-recreate before changing them
  casually (e.g. rewording a description on a security-relevant
  object); a frozen field belongs in code comments as a warning, not
  edited on a whim.
- **A trust-anchor resource (a key, a bound identity) should be
  retained deliberately on teardown, not merely "detached and
  forgotten."** Many cloud key-management services never truly delete
  a key — a "deleted" key still occupies its name/alias for a
  retention window — so a clean teardown procedure removes the key
  from Terraform's management (state-rm) before destroying everything
  else, and re-adopts it (import) on the way back in, rather than
  relying on `prevent_destroy` alone (which a module's own tests may
  need to bypass, and which lifecycle arguments generally can't be made
  conditional on a variable).
