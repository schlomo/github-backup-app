# Troubleshooting

Known failures, keyed by the exact error text a person or an agent
sees. Search here first when something fails ("Verify before
declaring ready" in
[principles/ai-working-process.md](principles/ai-working-process.md)):

```sh
grep -n -i -F "<a distinctive part of the error text>" docs/troubleshooting.md
```

An entry is added once its fix is verified, in the change that
verifies it. Entries are never deleted: one whose cause was fixed
upstream is marked resolved upstream, with the version, because the
same error comes back with an older version. A lesson worth knowing
before anyone hits it belongs with the project's other facts (see
`AGENTS.md`); this page starts from the error.

## Index

One row per entry, the error text exactly as in the entry.

| Error text (verbatim) | Entry |
|---|---|

## Format

```markdown
## <short title>

- **Error:** `<the exact error text, verbatim>`
- **Symptom:** what is seen, and where (command, job, log).
- **Why:** the root cause, with its evidence label.
- **Fix:** the literal command or change.
- **Verify:** the check that proves the fix worked.
- **Observed:** <date>, <tool and version>; open | resolved upstream
  in <version> (<date>).
```
