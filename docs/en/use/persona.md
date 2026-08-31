# Personas

A Persona controls the system prompt, opening dialogue, tools, Skills, and error reply used by an Agent session. Create Personas from **Personas** in the WebUI sidebar and organize larger collections with folders.

## Persona fields

- **Persona ID** is the unique identifier referenced by conversations, profiles, SubAgents, and scheduled jobs. Keep it stable after creation.
- **System prompt** defines the role, goals, boundaries, and response style. Do not store secrets or anything that must not be sent to the model.
- **Custom error reply** is sent first when an LLM request using this Persona fails. Leave it empty to use the system default error message.
- **Opening dialogue** contains alternating user and assistant few-shot examples and must have an even number of entries. These examples enter model context but are not written back as real conversation history.
- **Tools / MCP tools**: `null` means all currently available tools, an explicit name list allows only those tools, and an empty list means no tools.
- **Skills** use the same all, selected-only, or none semantics.

Tools and Skills are permission boundaries, not just prompt optimization. Apply least privilege to shell, file-write, browser, external-account, and administrative tools, and review the selection after models or plugins change.

## Which Persona is selected

The local Agent Runner resolves a Persona in this order:

1. a forced Persona configured for the message session under **Session Management**;
2. the Persona selected on the current conversation record;
3. the profile default Persona: `agent_runner.config.persona.persona_id` for the local runner, or `agent_runner.config.persona_id` for a third-party runner.

Session rules are useful for pinning a role to a platform, group, or user. Without a forced rule, WebChat can select a Persona per conversation. Explicitly selecting no Persona prevents the profile default from being applied.

Updating a Persona refreshes the runtime cache immediately, so an AstrBot restart is normally unnecessary. Existing history is not rewritten; subsequent model requests use the new definition.

## Conversation commands

Admins can use `/persona status` to inspect the current selection, `/persona list` to list Personas, `/persona show <persona_id>` to inspect one, `/persona set <persona_id>` to switch the current conversation, and `/persona unset` to explicitly disable Personas. Entering `/persona` alone displays the subcommand tree.

## Folders and deletion

Folders affect WebUI organization and ordering only. They do not change runtime permissions or scope. Deleting a folder moves its Personas to the root instead of deleting them.

Deleting a Persona removes its definition but does not rewrite every external reference. Before deletion, check:

- the default Persona in each profile;
- Session Management rules and existing conversation selections;
- SubAgents, Cron jobs, or plugins that store the Persona ID;
- learned data associated with that Persona in separate runtime tables.

## Import and export

The Persona card menu exports JSON, and the page toolbar imports JSON. The current interchange format contains only:

```json
{
  "persona_id": "researcher",
  "system_prompt": "You are a careful research assistant.",
  "begin_dialogs": ["Summarize this source.", "Please provide the source."]
}
```

The export does **not** include tools, Skills, the custom error reply, folder placement, ordering, long-term memory, or Persona Runtime learning data.

During import:

- `system_prompt` must be a non-empty string;
- only string entries from `begin_dialogs` are retained;
- the Persona is placed in the folder currently open in the UI;
- ID conflicts receive `_imported`, `_imported_2`, and similar suffixes;
- tools and Skills are set to “all available.”

> [!WARNING]
> Persona JSON is prompt input. Review third-party files before importing them, then immediately configure tools and Skills; otherwise the imported Persona inherits every currently available capability. The export is not a complete backup.

Use AstrBot [runtime-data backup](../deploy/astrbot/backup) for a complete migration instead of relying on Persona JSON alone. After restoration, verify that referenced plugins, MCP servers, Skills, and Providers still exist because a Persona stores their names rather than their implementations.

## Related features

- [SubAgent orchestration](./subagent): a SubAgent can bind a Persona and inherit its prompt, opening dialogue, and tools. Isolated Persona Skills are not currently inherited.
- [Skills](./skills): a Persona can narrow the Skill set visible in a session.
- [Long-term memory](./long-term-memory): memory is stored by user and message session, is not included in Persona exports, and is not automatically erased when a Persona is deleted.
