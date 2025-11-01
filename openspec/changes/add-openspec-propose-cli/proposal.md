## Why

Creating and validating OpenSpec change proposals is a repetitive process. Authors must scaffold directories, populate `proposal.md`/`tasks.md`, and add spec delta files with exact formatting. A small CLI helper plus validation automation will reduce human error, speed up proposal creation, and ensure delta files meet formatting rules before review.

## What Changes

- Add a new CLI command `openspec propose` (or `openspec propose --id <change-id>`) that scaffolds `openspec/changes/<change-id>/` with `proposal.md`, `tasks.md`, and an example `specs/<capability>/spec.md` delta.  
- Add a strict validation step (`openspec propose --validate`) that runs local parsing checks and optionally `openspec validate <id> --strict` if the tool is available.  
- Add documentation and an example in `openspec/changes/add-openspec-propose-cli/` to serve as a canonical template.

**BREAKING?** No

## Impact

- Affected specs: none (this is tooling/authoring support)
- Affected code: CLI layer (new `openspec` subcommand implementation) and docs
- Developer UX: Faster, less error-prone proposal scaffolding; consistent delta templates

## Rollout Plan

1. Add scaffolding implementation and template files under `openspec/cli/` or equivalent.
2. Add `proposal.md`/`tasks.md`/sample spec in `openspec/changes/add-openspec-propose-cli/` for reviewers.
3. Optional: Add an automated validator that can be invoked by `openspec propose --validate`.

## Acceptance Criteria

- `openspec propose --id add-foo` creates `openspec/changes/add-foo/` with `proposal.md`, `tasks.md`, and at least one `specs/<capability>/spec.md` file.
- Created spec delta files follow the OpenSpec formatting rules (have `## ADDED|MODIFIED|REMOVED Requirements` and at least one `#### Scenario:` per requirement).
- `openspec propose --validate` returns exit code 0 when templates pass local validation checks.
