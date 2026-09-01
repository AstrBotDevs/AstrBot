<!--
Title: fix(scope): ...
Link a Bug report Issue when one exists.
Breaking: fix(api)!: ... plus BREAKING CHANGE: footer.
-->

## Summary

<!-- Expected vs actual, and what the fix changes. Not a file list. -->

## Related issue

<!-- `Fixes #123` or `Related: #123`. -->

Fixes #

## Root cause

<!-- Why it failed, not only the symptom. -->

## Reproduction

<!-- Minimal steps, or why a reproduction is not practical. -->

## Implementation notes

<!-- Why this fix, not a broader rewrite. Call out compensating cleanup. -->

## Validation

<!-- Exact commands run. Include the regression test. Do not claim a check passed unless you ran it or CI did. -->

```text
ruff format --check .
ruff check .
make check
uv run pytest --test-profile blocking
```

## Compatibility and risk

<!-- Public API, Dashboard protocol, security, performance, migration. Write "None" if not applicable. -->

## Checklist

- [ ] The change is focused and does not include unrelated refactoring.
- [ ] I added or updated a regression test, or explained why a test is not practical.
- [ ] I ran the relevant formatting, lint, build, and test commands.
- [ ] User-visible behavior updates both `docs/zh/` and `docs/en/` when needed.
- [ ] OpenAPI, generated client, `docs/public/openapi.json`, and tests change together when routes or schemas change.
- [ ] No secrets committed. Runtime Python deps update `pyproject.toml`, `requirements.txt`, and `uv.lock` together.
- [ ] I did not restore legacy shims, Python &lt;3.14 fallbacks, or upstream publish/docs URLs as fork artifacts.
- [ ] Breaking API or behavior changes use `!` and a `BREAKING CHANGE:` footer.
- [ ] I will not merge this PR myself. Merge needs a human maintainer review plus a separate AI-assisted review ([AI_POLICY.md](../../AI_POLICY.md)).
- [ ] AI use follows [AI_POLICY.md](../../AI_POLICY.md). Keep exactly one author note below. Do not fabricate the other.

## Human note

<!-- Humans only. Mother tongue, own words: intent, why this approach, what you verified. Delete this section if an agent is the author. -->

## Agent note

<!-- Agents only. Goal, paths touched, checks run, residual risk, tools used. Delete this section if a human is the author. -->
