<!--
Title: refactor(scope): ... | perf(scope): ... | style(scope): ...
No intended user-visible or API behavior change. If behavior changes, use feat.md or fix.md.
-->

## Summary

<!-- What structure, performance, or formatting this improves, and why now. -->

## Related issue

<!-- `Fixes #123` or `Related: #123`. Optional. -->

Related: #

## Behavior guarantee

<!-- Confirm no intended external/API/UI change. List any observable side effect if one exists. -->

No intended behavior change.

## Performance

<!-- Required for `perf`. Before/after or why numbers are not available. Delete this section for `refactor` / `style`. -->

## Implementation notes

<!-- Scope of the rewrite. Call out anything deliberately left alone. -->

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

- [ ] Conventional Commit type is `refactor`, `perf`, or `style`.
- [ ] The change is focused and does not mix in features or bug fixes.
- [ ] Tests cover the touched paths, or I explained why extra tests are not practical.
- [ ] I ran the relevant formatting, lint, build, and test commands.
- [ ] OpenAPI, generated client, `docs/public/openapi.json`, and tests change together when routes or schemas change.
- [ ] No secrets committed. Runtime Python deps update `pyproject.toml`, `requirements.txt`, and `uv.lock` together.
- [ ] I did not restore legacy shims, Python &lt;3.14 fallbacks, or upstream publish/docs URLs as fork artifacts.
- [ ] I will not merge this PR myself. Merge needs a human maintainer review plus a separate AI-assisted review ([AI_POLICY.md](../../AI_POLICY.md)).
- [ ] AI use follows [AI_POLICY.md](../../AI_POLICY.md). Keep exactly one author note below. Do not fabricate the other.

## Human note

<!-- Humans only. Mother tongue, own words: intent, why this approach, what you verified. Delete this section if an agent is the author. -->

## Agent note

<!-- Agents only. Goal, paths touched, checks run, residual risk, tools used. Delete this section if a human is the author. -->
