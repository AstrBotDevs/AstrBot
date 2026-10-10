# Persona Management

AstrBot personas define the bot's role, system prompt, preset dialogs, and the tools and Skills it can use. Manage personas from the `Persona` page in the WebUI, where you can create, edit, and delete them and organize them into folders.

## Managing Personas

Open the `Persona` page in the WebUI:

- Click `Create Persona` to add a persona.
- Use the buttons on a persona card to view, edit, move, or delete it.
- Switch between folders with the folder tree on the left or the breadcrumb at the top. You can also drag a persona into a folder.

## Persona Fields

| Field | Description |
| --- | --- |
| Persona ID (`persona_id`) | Unique identifier of the persona |
| System Prompt (`system_prompt`) | System prompt sent to the model, defining the role and behavior |
| Preset Dialogs (`begin_dialogs`) | Optional preset dialogs. The count must be even; they alternate as user / assistant starting from user. They help the model understand the role |
| Tools / Skills | Tools and Skills available to this persona |

For tool and Skill configuration, see [Tool Use](./function-calling.md) and [Skills](./skills.md).

## Importing a Persona

Choose `Import Persona` from the `…` menu at the top right of the `Persona` page to import a persona JSON file exported from AstrBot.

A format description dialog appears first, and the same information is provided below. The file picker filters for `.json` files, but the import handler does not enforce the extension; the file must contain valid JSON with the following fields:

| Field | Required | Description |
| --- | --- | --- |
| `system_prompt` | Yes | System prompt. Import fails if it is missing. |
| `persona_id` | No | Persona ID. Defaults to `imported_persona`. If it already exists, an `_imported` suffix is appended; on further conflicts, `_imported_1`, `_imported_2`, and so on are appended. |
| `begin_dialogs` | No | Preset dialog list. Defaults to an empty array `[]`. The count must be even; entries alternate as user / assistant starting from user. An odd count is rejected by the API. |

Minimal example:

```json
{
  "persona_id": "my_persona",
  "system_prompt": "You are a helpful assistant.",
  "begin_dialogs": ["Hello", "Hi! How can I help you?"]
}
```

> [!WARNING]
> `tools` and `skills` are not imported. After import, the persona uses all tools and Skills by default. When migrating or backing up personas, you must configure tools and Skills again manually.

## Exporting a Persona

Choose `Export` on a persona card or in the detail dialog to download the persona's JSON file.

> [!NOTE]
> Export also includes only the system prompt and preset dialogs, not the tools and Skills configuration.
