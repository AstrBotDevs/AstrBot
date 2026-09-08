---
name: skill-creator
description: Create, revise, and validate AstrBot Skills built around SKILL.md instruction bundles. Use when the user asks to create, scaffold, improve, package, or review a Skill for an AstrBot workspace, local installation, or plugin.
---

# Create AstrBot Skills

Build small, reusable instruction bundles that another agent can discover and follow reliably.

## Follow the core design rules

- Assume the model already knows general facts. Include only task-specific procedures, constraints, and resources.
- Match instruction precision to risk. Use flexible guidance for judgment-heavy work and deterministic scripts for fragile operations.
- Keep `SKILL.md` focused. Put detailed reference material in `references/`, repeatable automation in `scripts/`, and output material in `assets/`.
- Link every optional resource directly from `SKILL.md` and state when to use it. Avoid deep chains of references.
- Do not add process documents such as `README.md`, changelogs, installation guides, or quick-reference duplicates.
- Do not add OpenAI- or Codex-specific metadata, directories, tools, or installation steps unless the user explicitly targets that runtime.

## Establish the intended behavior

Before writing files, identify:

1. Concrete requests that should trigger the Skill.
2. Expected outputs or actions.
3. Required tools, permissions, and runtime assumptions.
4. Failure cases that need explicit guardrails.

Ask only for information that materially changes the result. Infer ordinary details from the current task and environment.

## Choose the target

Use the runtime declared in the system instructions and the location requested by the user. Do not infer the runtime from filesystem paths.

In local mode, common targets are:

- Workspace Skill: `<workspace>/skills/<skill-name>`
- Locally installed Skill: `<astrbot-data>/skills/<skill-name>`.
- Installed third-party plugin Skill: `<astrbot-data>/plugins/<plugin-name>/skills/<skill-name>`.

If no location is specified in local mode, create the Skill under `skills/<skill-name>` in the current AstrBot workspace. Creating or modifying a locally installed Skill requires administrator access and is enforced by the filesystem tools. If permission is denied, use the workspace target and explain the fallback.

In sandbox mode, do not use `<astrbot-data>` or attempt to install a Skill into the host AstrBot instance. Create it under `skills/<skill-name>` in the current sandbox workspace, and treat it as sandbox-scoped unless the runtime provides a dedicated persistence or release workflow.

Treat plugin-provided Skills as read-only during normal runtime. Modify a plugin Skill only when the user is working in that plugin's source tree and has explicitly requested the change. If the requested target is not writable, create the Skill in the workspace and explain how to install or move it.

## Name the Skill

- Use lowercase letters, digits, and hyphens only.
- Keep the name under 64 characters.
- Prefer a short action-oriented name.
- Name the folder exactly the same as the frontmatter `name`.

## Plan only necessary resources

For each repeated operation, decide whether plain instructions are sufficient:

- Add `scripts/` only for deterministic, repeatable operations.
- Add `references/` only for material the agent may need to consult while working.
- Add `assets/` only for files intended to be copied or incorporated into outputs.

Do not create empty resource directories.

## Write SKILL.md

Start with YAML frontmatter containing only `name` and `description`:

```yaml
---
name: example-skill
description: Describe what the Skill does and the concrete requests or situations that should trigger it.
---
```

Make the description specific enough for discovery. Put all trigger guidance in the description because AstrBot loads the body only after the Skill is selected.

Write the body as direct instructions:

- Use imperative language.
- Put the main workflow before edge cases.
- State important safety boundaries close to the affected action.
- Use the AstrBot tool names actually available in the current runtime when a workflow depends on tools.
- Prefer relative paths inside the Skill so it works after installation or sandbox synchronization.
- Keep examples short and representative.

## Initialize or update files

For a new Skill, prefer the bundled initializer when Python and shell execution are available:

```text
python <this-skill-directory>/scripts/init_skill.py <skill-name> --path <target-skills-root> --description <description>
```

Add `--resources scripts,references,assets` with only the directories that are needed. The initializer refuses to overwrite an existing Skill.

If shell execution is unavailable, create the directory and UTF-8 `SKILL.md` with `astrbot_file_write_tool`. Create optional resources only after their content is known.

When updating a Skill, read its complete `SKILL.md` and directly referenced resources before editing. Preserve useful behavior and avoid unrelated restructuring.

## Validate

When Python and shell execution are available, run:

```text
python <this-skill-directory>/scripts/validate_skill.py <created-skill-directory>
```

Otherwise verify manually:

- The directory name is valid and matches frontmatter `name`.
- `SKILL.md` is UTF-8 and has valid YAML frontmatter.
- `description` explains both capability and trigger conditions.
- The body is non-empty and operational.
- Every referenced file exists and every bundled file has a clear purpose.
- Instructions do not assume unavailable tools, paths, credentials, or permissions.

Run any bundled scripts on representative safe inputs. Fix validation or execution failures before presenting the Skill.

## Finish

Report the created or updated location, included resources, validation performed, and any runtime or activation step still required. Do not enable a globally installed Skill or change an AstrBot configuration unless the user requested it.
