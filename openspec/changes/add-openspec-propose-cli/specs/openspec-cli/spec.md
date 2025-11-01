## ADDED Requirements

### Requirement: CLI scaffolding for change proposals
The system SHALL provide a CLI subcommand `openspec propose` that scaffolds a new change proposal directory with `proposal.md`, `tasks.md`, and an example `specs/<capability>/spec.md` file.

#### Scenario: Create a new proposal with id
- **WHEN** a developer runs `openspec propose --id add-foo`
- **THEN** `openspec/changes/add-foo/` is created with `proposal.md`, `tasks.md`, and a `specs/` subdirectory containing at least one `.md` file with `## ADDED Requirements` and `#### Scenario:` entries

#### Scenario: Validate template formatting
- **WHEN** a developer runs `openspec propose --id add-foo --validate`
- **THEN** the tool performs local checks ensuring each spec file contains at least one `#### Scenario:` and returns a non-zero exit code if validation fails
