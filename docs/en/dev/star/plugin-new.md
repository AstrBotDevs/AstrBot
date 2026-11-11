---
outline: deep
head:
  - - style
    - {}
    - '.vp-doc table:has(thead th:nth-child(3)) th:nth-child(-n + 2), .vp-doc table:has(thead th:nth-child(3)) td:nth-child(-n + 2) { white-space: nowrap; }'
---

# AstrBot Plugin Development Guide 🌠

Welcome to the AstrBot Plugin Development Guide! This section will guide you through developing AstrBot plugins. Before we begin, we hope you have the following foundational knowledge:

1. Some experience with Python programming.
2. Some experience with Git and GitHub.

## Environment Setup

### Obtain the Plugin Template

1. Open the AstrBot plugin template: [helloworld](https://github.com/Soulter/helloworld)
2. Click `Use this template` in the upper right corner
3. Then click `Create new repository`.
4. Fill in your plugin name in the `Repository name` field. Plugin naming conventions:
   - Recommended to start with `astrbot_plugin_`;
   - Must not contain spaces;
   - Keep all letters lowercase;
   - Keep it concise.
5. Click `Create repository` in the lower right corner.

### Clone the Project Locally

Clone both the AstrBot main project and the plugin repository you just created to your local machine.

```bash
git clone https://github.com/AstrBotDevs/AstrBot
mkdir -p AstrBot/data/plugins
cd AstrBot/data/plugins
git clone <your-plugin-repository-url>
```

Then, use `VSCode` to open the `AstrBot` project. Navigate to the `data/plugins/<your-plugin-name>` directory.

Update the `metadata.yaml` file with your plugin's metadata information.

> [!WARNING]
> Please make sure to modify this file, as AstrBot relies on the `metadata.yaml` file to recognize plugin metadata.

### Set Plugin Logo (Optional)

You can add a `logo.png` file in the plugin directory as the plugin's logo. Please maintain an aspect ratio of 1:1, with a recommended size of 256x256.

![Plugin logo example](https://files.astrbot.app/docs/source/images/plugin/plugin_logo.png)

### Plugin Display Name (Optional)

You can modify (or add) the `display_name` field in the `metadata.yaml` file to serve as the plugin's display name in scenarios like the plugin marketplace, making it easier for users to read.

Plugin display names and descriptions can follow the WebUI language. See [Plugin Internationalization](./guides/plugin-i18n).

### Plugin Short Description (Optional)

You can add a `short_desc` field to `metadata.yaml` as the short description shown on plugin marketplace cards. Keep it to a concise one-sentence summary. If it is not provided, cards fall back to `desc`.

```yaml
short_desc: A one-line summary of your plugin.
```

### Bundle Skills with a Plugin (Optional)

Plugins can provide a `skills/` directory. After AstrBot loads the plugin, valid Skills inside that directory are automatically included in the Skill Manager, with their source shown as the plugin.

For multiple Skills, use this structure:

```text
your_plugin/
  metadata.yaml
  main.py
  skills/
    web-search-helper/
      SKILL.md
    report-writer/
      SKILL.md
```

If `skills/` itself is one Skill, you can also place `SKILL.md` directly under it:

```text
your_plugin/
  skills/
    SKILL.md
```

In that case, the Skill name uses the plugin directory name. Plugin-provided Skills are managed by the plugin and appear as read-only sources under `Extensions → Skills` in the WebUI. They can be enabled or disabled, but cannot be deleted or edited from Local Skills. When the plugin is uninstalled or updated, its bundled Skills change with the plugin files.

### Declare Supported Platforms (Optional)

You can add a `support_platforms` field (`list[str]`) to `metadata.yaml` to declare which platform adapters your plugin supports. The WebUI plugin page will display this field.

```yaml
support_platforms:
  - telegram
  - discord
```

The values in `support_platforms` must be keys from `ADAPTER_NAME_2_TYPE`. Currently supported:

- `aiocqhttp`
- `qq_official`
- `qq_official_webhook`
- `telegram`
- `wecom`
- `wecom_ai_bot`
- `lark`
- `dingtalk`
- `discord`
- `slack`
- `kook`
- `vocechat`
- `weixin_official_account`
- `weixin_oc`
- `satori`
- `misskey`
- `line`
- `matrix`
- `mattermost`

### Declare AstrBot Version Range (Optional)

You can add an `astrbot_version` field in `metadata.yaml` to declare the required AstrBot version range for your plugin. The format follows dependency specifiers in `pyproject.toml` (PEP 440), and must not include a `v` prefix.

```yaml
astrbot_version: ">=4.16,<5"
```

Examples:

- `>=4.17.0`
- `>=4.16,<5`
- `~=4.17`

If you only want to declare a minimum version, use:

- `>=4.17.0`

If the current AstrBot version does not satisfy this range, the plugin will be blocked from loading with a compatibility error.
In the WebUI installation flow, you can choose to "Ignore Warning and Install" to bypass this check.

### Declare Plugin Category (Optional)

You can add a `category` field in `metadata.yaml` to declare the marketplace category of your plugin. The plugin marketplace, the WebUI and the runtime all follow this field.

```yaml
category: media processing
```

`category` takes one of the following identifiers. The English label is only the display text, so writing it back is not accepted.

| Identifier | English label | Use it for |
| --- | --- | --- |
| `ai tools` | AI Tools | One-shot text abilities on top of an LLM: prompts, rewriting, summarizing and translation |
| `ai image` | AI Image | Text-to-image, image-to-image, style transfer and image editing |
| `ai speech` | AI Speech | TTS and ASR: speech synthesis, voices and tone, speech recognition |
| `ai agent` | Agents & Orchestration | Agent runs, tool calling, multi-agent and workflow orchestration |
| `ai context` | AI Conversation | Cross-turn conversation context: persona and character settings, context compression and injection, reply style and tone; stored memories belong to Long-term Memory, external documents to Knowledge Base |
| `long term memory` | Long-term Memory | Storing and recalling memories, user profiles and long-lived context |
| `knowledge base` | Knowledge Base | Ingesting documents and retrieval QA (RAG), knowledge base management |
| `tools` | Tools | General utilities and command sets: encoding and format conversion, calculation, short links, batch work |
| `productivity` | Productivity | To-dos, schedules, notes and personal workflows |
| `utilities` | Utilities | Everyday lookups and reminders: weather, exchange rates, parcels, almanac, unit conversion |
| `integrations` | Integrations | Wiring a third-party platform or account: GitHub, cloud drives, RSS, music, Notion |
| `platform adapter` | Platform Adapter | New messaging platforms or protocols, such as QQ, Telegram and Discord |
| `media processing` | Media Processing | Parsing, transcoding, joining and sticker generation for images, audio and video |
| `automation` | Automation & Scheduling | Scheduled pushes, auto replies and event-driven flows |
| `security` | Security & Moderation | Content moderation, anti-spam, word filters, permissions and risk control |
| `entertainment` | Entertainment | Generic fun that is not a game: tarot, fortune telling, song requests, stickers, memes and playful chat |
| `group games` | Group Games | Played inside the group chat with rules the plugin implements itself: word chains, word guessing, who-is-the-spy, dice and quizzes |
| `game integration` | Game Integration | Plugins built around another game: connectors, wikis and data lookups, server status and player actions (Minecraft, Palworld, Steam) |
| `other` | Other | Anything that does not fit the categories above |

Declarations are lightly normalized: surrounding whitespace, letter case and space, `-` or `_` separators are ignored, so the underscore spelling works too: `ai tools`, `AI Tools`, `ai-tools` and `ai_tools` are equivalent.

Plugins that do not declare `category` are grouped under `other`. An unsupported value only logs a warning and is also grouped under `other`; it never blocks installation or updates. Adding a new category requires a code change in AstrBot, so prefer the identifiers above.

### Debugging Plugins

AstrBot uses a runtime plugin injection mechanism. Therefore, when debugging plugins, you need to start the AstrBot main application.

You can use AstrBot's hot reload feature to streamline the development process.

After modifying the plugin code, open `Extensions → Plugins` in the AstrBot WebUI, find your plugin, and click the refresh icon (`Reload Extension`) on its card.

If the plugin fails to load due to code errors or other reasons, click its `Reload` button in the `Failed to Load Plugins` list on the same page.

### Plugin Dependency Management

Currently, AstrBot manages plugin dependencies using pip's built-in `requirements.txt` file. If your plugin requires third-party libraries, please be sure to create a `requirements.txt` file in the plugin directory and list the dependencies used, to prevent Module Not Found errors when users install your plugin.

> For the complete format of `requirements.txt`, please refer to the [pip official documentation](https://pip.pypa.io/en/stable/reference/requirements-file-format/).

## Development Principles

Thank you for contributing to the AstrBot ecosystem. Please follow these principles when developing plugins, which are also good programming practices:

- Features must be tested.
- Include comprehensive comments.
- Store persistent data in the `data` directory, not in the plugin's own directory, to prevent data loss when updating/reinstalling the plugin.
- Implement robust error handling mechanisms; don't let a single error crash the plugin.
- Before committing, please use the [ruff](https://docs.astral.sh/ruff/) tool to format your code.
- Do not use the `requests` library for network requests; use asynchronous network request libraries such as `aiohttp` or `httpx`.
- If you're extending functionality for an existing plugin, please prioritize submitting a PR to that plugin rather than creating a separate one (unless the original plugin author has stopped maintaining it).
- If your plugin directly draws on another project's design, feature ideas, or implementation approach, clearly acknowledge the source of inspiration in the README and link to the relevant project.
- If you use, modify, or port code or assets from another project, follow the original project's open-source license and retain copyright and license notices as required by that license.
