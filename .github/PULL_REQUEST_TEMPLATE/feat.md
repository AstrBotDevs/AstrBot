<!--
Title: feat(scope): ...
Large features need a development Issue first (GOVERNANCE.md).
Breaking: feat(api)!: ... plus BREAKING CHANGE: footer.
-->

## Summary

<!-- User-visible or API behavior this adds, changes, or removes. Not a file list. -->

## Related issue

<!-- `Fixes #123` or `Related: #123`. -->

Related: #

## Behavior

<!-- What callers, Dashboard users, or adapters get after this lands. -->

## Non-goals

<!-- Deliberate omissions. Do not restore legacy shims to cover them. -->

## Implementation notes

<!-- Design decisions, OpenAPI/docs impact, migration. -->

## Validation

<!-- Exact commands run. Do not claim a check passed unless you ran it or CI did. -->

```text
ruff format --check .
ruff check .
make check
uv run pytest --test-profile blocking
```

## Compatibility and risk

<!-- Public API, Dashboard protocol, security, performance, migration. Write "None" if not applicable. -->

## Checklist

- [ ] A Feature request Issue exists for large work, or this is a small, obvious addition.
- [ ] The change is focused and does not include unrelated refactoring.
- [ ] I added or updated tests, or explained why tests are not practical.
- [ ] User-visible behavior updates both `docs/zh/` and `docs/en/`.
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
