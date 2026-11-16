# Platform notes: Python

- **Modern Python (the current stable line), with `uv` for tooling and
  dependency management** — one tool for interpreters, environments,
  lockfiles and running scripts.
- **`pathlib` and the modern standard library over hand-rolled
  equivalents;** f-strings, type hints on functions, `dataclass` and
  other modern language features.
- **Idiomatic and easy to read:** expressive names, sensible
  decomposition into functions, reasonable DRY (not taken to an
  extreme). Few comments, high signal — a comment explains what isn't
  obvious from the code; a large comment volume is itself a style
  problem.
- **Tests use `pytest` with fixtures.** The test-first rule is in
  [../engineering.md](../engineering.md) ("Test first").
