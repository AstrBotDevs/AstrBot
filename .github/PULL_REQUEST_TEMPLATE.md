<!--
Title: English Conventional Commits, e.g.
  fix(dashboard): reject truncated backup zip without leaving partial files

Types: feat, fix, refactor, perf, style, test, docs, build, ops, chore.
Do not use ci; use ops. Breaking: feat(api)!: ... plus BREAKING CHANGE: footer.

Prefer a typed template via `template=<file>` on the compare URL or
`gh pr create --template .github/PULL_REQUEST_TEMPLATE/<file>`:

  feat.md      feat
  fix.md       fix
  docs.md      docs
  refactor.md  refactor, perf, style
  chore.md     chore, build, ops, test

This fallback is for mixed or untyped PRs. See CONTRIBUTING.md.
-->

## Summary

<!-- What problem does this solve, and what changed? Behavior and design, not a file list. -->

## Related issue

<!-- `Fixes #123` or `Related: #123`. Development Issues track defects and features; they are not user support. -->

Related: #

## Implementation notes

<!-- Design decisions, compatibility, deliberate non-goals, OpenAPI/docs impact. -->

## Validation

<!-- Exact commands run. Do not claim a check passed unless you ran it or CI did. -->

```text
ruff format --check .
ruff check .
make check
```

## Compatibility and risk

<!-- Public API, Dashboard protocol, security, performance, migration. Write "None" if not applicable. -->

## Checklist

- [ ] The change is focused and does not include unrelated refactoring.
- [ ] I added or updated tests, or explained why tests are not practical.
- [ ] I ran the relevant formatting, lint, build, and test commands.
- [ ] User-visible behavior updates both `docs/zh/` and `docs/en/` when needed.
- [ ] OpenAPI, generated client, `docs/public/openapi.json`, and tests change together when routes or schemas change.
- [ ] No secrets committed. Runtime Python deps update `pyproject.toml`, `requirements.txt`, and `uv.lock` together.
- [ ] I did not restore legacy shims, Python &lt;3.14 fallbacks, or upstream publish/docs URLs as fork artifacts.
- [ ] Breaking API or behavior changes use `!` and a `BREAKING CHANGE:` footer.
- [ ] I will not merge this PR myself. Merge needs a human maintainer review plus a separate AI-assisted review ([AI_POLICY.md](../AI_POLICY.md)).
- [ ] AI use follows [AI_POLICY.md](../AI_POLICY.md). Keep exactly one author note below. Do not fabricate the other.

## Human note

<!-- Humans only. Mother tongue, own words: intent, why this approach, what you verified. Delete this section if an agent is the author. -->

## Agent note

<!-- Agents only. Goal, paths touched, checks run, residual risk, tools used. Delete this section if a human is the author. -->
