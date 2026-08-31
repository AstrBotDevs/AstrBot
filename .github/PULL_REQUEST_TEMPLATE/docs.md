<!--
Title: docs(scope): ...
Documentation-only. Any runtime or config behavior change belongs in feat or fix.
-->

## Summary

<!-- What the docs get wrong today, and what this corrects. -->

## Related issue

<!-- `Fixes #123` or `Related: #123`. Optional for small copy fixes. -->

Related: #

## Pages

<!-- List `docs/zh/` and `docs/en/` paths. Note `docs/.vitepress/config.mjs` if navigation changes. -->

- zh:
- en:

## Implementation notes

<!-- Structural alignment vs natural translation. Do not point Dashboard, API errors, or hints at `docs.astrbot.app`. -->

## Validation

<!-- Exact commands run. Do not claim a check passed unless you ran it or CI did. -->

```text
cd docs && pnpm install --frozen-lockfile && pnpm run docs:build
make check-md
```

## Compatibility and risk

<!-- Navigation, `/help/` base, or in-app doc links. Write "None" if not applicable. -->

## Checklist

- [ ] This PR is documentation-only (no product, API, or toolchain behavior change).
- [ ] `docs/zh/` and `docs/en/` stay structurally aligned; wording is a natural translation.
- [ ] Navigation changes update `docs/.vitepress/config.mjs`.
- [ ] I did not commit `docs/.vitepress/dist/` or Dashboard `help/` output.
- [ ] I did not restore `docs.astrbot.app`, a docs container, or upstream publish URLs as fork artifacts.
- [ ] I ran `docs:build` and Markdown checks for the touched pages.
- [ ] I will not merge this PR myself. Merge needs a human maintainer review plus a separate AI-assisted review ([AI_POLICY.md](../../AI_POLICY.md)).
- [ ] AI use follows [AI_POLICY.md](../../AI_POLICY.md). Keep exactly one author note below. Do not fabricate the other.

## Human note

<!-- Humans only. Mother tongue, own words: intent, why this approach, what you verified. Delete this section if an agent is the author. -->

## Agent note

<!-- Agents only. Goal, paths touched, checks run, residual risk, tools used. Delete this section if a human is the author. -->
