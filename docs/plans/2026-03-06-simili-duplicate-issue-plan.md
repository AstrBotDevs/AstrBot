# Simili Duplicate Issue Triage Plan

## Summary

This repository now includes the Simili duplicate issue triage configuration and the two GitHub Actions workflows needed to run it:

- `simili-triage.yml` runs on issue open, edit, and reopen events.
- `simili-auto-close.yml` scans `potential-duplicate` issues and closes them after the grace period.

The integration only targets normal issue triage. It does not handle pull requests and does not replace the existing stale workflow.

## Required secrets

Add these repository secrets before enabling the workflows:

- `QDRANT_URL`
- `QDRANT_API_KEY`
- `GEMINI_API_KEY` or `OPENAI_API_KEY`

The checked-in `.github/simili.yaml` is configured for Gemini by default. If the repository will run on OpenAI only, update the provider, model, API key variable, and embedding dimensions in `.github/simili.yaml` before use.

Qdrant must be a persistent official deployment target, either cloud-hosted or self-hosted. Do not use an ephemeral GitHub Actions service container if you want the index to survive between runs.

## Behavior and safeguards

- The triage workflow only runs for issues labeled `bug` or `enhancement`.
- Issues labeled `plugin-publish` or `no-simili` are skipped.
- The workflows ensure `potential-duplicate` and `no-simili` labels exist before Simili runs.
- `duplicate` is still the final confirmed label and is not redefined here.
- The existing stale workflow keeps ownership of inactivity handling for bug issues.

## Backfill and rollout

After secrets are configured, backfill the current issue corpus so new similarity checks have historical context:

```bash
gh extension install similigh/simili-bot
gh simili index --repo AstrBotDevs/AstrBot --config .github/simili.yaml
```

Recommended rollout order:

1. Let `simili-triage.yml` run on new issue activity.
2. Trigger `simili-auto-close.yml` manually with `dry_run=true`.
3. Review the dry-run output for skipped and closable issues.
4. Set repository variable `SIMILI_AUTO_CLOSE_ENABLED=true` once the results look correct.

## Operations and rollback

Manual dry-run:

```bash
gh workflow run simili-auto-close.yml -f dry_run=true
```

Temporary rollback options:

- Set repository variable `SIMILI_AUTO_CLOSE_ENABLED=false`.
- Add the `no-simili` label to any issue that should never be triaged by Simili.
- If needed, disable `simili-triage.yml` entirely until Qdrant or model credentials are fixed.
