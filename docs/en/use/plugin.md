---
outline: deep
---

# AstrBot Plugins {#astrbot-star}

Plugins are extensions that add features to AstrBot. They can introduce chat commands, connect external services, or give AI agents new tools without requiring changes to AstrBot itself.

For example, if you want your bot to check the weather, subscribe to updates, generate images, or interact with a service in chat, look for a suitable plugin in the market. **Using plugins usually requires no programming. Writing or modifying a plugin does.**

This guide starts with installation and everyday use. If you want to build a plugin, go to the [Plugin Development Guide](/en/dev/star/plugin-new.html).

## What are plugins, and what can they do?

AstrBot handles the basics: receiving messages, connecting models, and managing conversations. Plugins use AstrBot's APIs to add functionality to these workflows. In development documentation and code, plugins are also called **Stars**.

| Capability | How it works and examples |
| --- | --- |
| Chat commands | A specific command triggers a feature, such as retrieving information, generating content, or performing an administration task. Each plugin defines its command names and arguments. |
| AI tools | An agent can call tools to perform tasks such as retrieving data from a service. Users describe their needs in natural language, and the model decides whether to call a tool. |
| Message processing | Plugins listen for messages or other events, respond to matching content, or modify AI requests and responses. |
| External integrations | Plugins connect third-party APIs, databases, or business systems. Some require an API key, account, or service URL. |
| Management pages and skills | Plugins can provide their own WebUI pages and bundle Skills that guide agents through particular tasks. |

These are capabilities of the plugin system; **individual plugins do not necessarily provide all of them**. Check the author's documentation for features, supported platforms, model requirements, and configuration.

::: tip Do all plugins need AI?
Command and message-processing plugins do not necessarily need an AI model. Plugins that provide AI tools typically require a model that supports tool calling and a persona that allows the relevant tools. Installing a plugin does not make every feature participate in every conversation automatically.
:::

## Getting started: install your first plugin

For your first plugin, use the plugin market and follow the complete workflow below.

### 1. Open the plugin market

In the AstrBot WebUI, select **Extensions** in the sidebar, open the **Plugins** tab, and switch to **AstrBot Plugin Market**.

- **Installed**: manage plugins installed in this AstrBot instance.
- **AstrBot Plugin Market**: browse, search for, and install plugins.

The same workspace has **Skills**, **MCP Servers**, and **Handlers** tabs for skills, MCP servers, and registered commands, tools, and other handlers.

### 2. Choose a suitable plugin

Search by plugin name or a keyword describing the feature you want. You can also filter by categories such as AI enhancement, entertainment, productivity, integrations, utilities, and others. Open a plugin's details and check:

- **Features and usage**: whether it meets your needs and whether you use it through commands, natural language, or another trigger.
- **Supported platforms**: whether it works with your messaging platform. Some features depend on platform-specific APIs.
- **AstrBot version requirements**: whether your installed version is compatible.
- **Configuration and dependencies**: whether it needs an API key, external service, additional program, or particular deployment environment.

If the description is incomplete, open the repository and read its README and usage documentation. Stars, downloads, and update dates can help you browse, but they do not replace compatibility checks or usage instructions.

### 3. Install and check that it loads

Click **Install**, confirm the installation source, and wait for the operation to finish. Return to **Installed**, find the plugin, and check that it is open and has no loading errors.

If it appears under **Failed to Load Plugins**, read the error, follow the [troubleshooting advice](#troubleshooting), and click **Reload** after fixing the problem.

### 4. Configure the plugin

If configuration is required, click the gear icon (**Configure**) on the plugin card, fill in the parameters described by its author, and save. External integrations may need an API key, service URL, or subscription target.

Skip this step if the plugin has no additional settings. Credentials requested by a plugin belong in its configuration, rather than unrelated model settings.

### 5. Try its simplest feature

On a messaging platform connected to AstrBot, follow the plugin's instructions to test a basic feature:

- **Command plugins**: send the documented command and arguments. Send `/help` to see currently enabled commands, or manage them under **Extensions → Handlers → Command**.
- **AI tool plugins**: describe your request to the bot. Check that the current model supports tool calling and that the current persona allows the tool.
- **Event-based plugins**: trigger the documented event, such as sending a message that matches a rule.

::: info Command prefixes
Examples here use the default `/` prefix. If you changed the wake prefix to `!`, use `!help` and the corresponding prefix for plugin commands. Some commands require AstrBot administrator permissions; check the plugin documentation and command management settings.
:::

## The plugin market

The market is a place to discover and install community plugins. Installed plugins are managed on the **Installed** page; they run in your AstrBot environment, rather than in the market.

The market provides search, categories, and sorting. Beginners can usually use the **default plugin source**. If needed, use plugin source management to add or switch custom sources. A source determines the plugin list you browse; adding a source does not install all its plugins.

::: warning Understand the source before installing
Plugins run in AstrBot's Python environment. Install plugins from sources you trust. Inclusion in the market does not guarantee stability or security. Agent local isolation settings restrict agent execution; they do not automatically isolate arbitrary plugin code.
:::

For authors, **Submit My Extension** at the bottom of the market opens the [AstrBot Cloud publishing page](https://cloud.astrbot.app/publish). See [Publishing Plugins](/en/dev/star/plugin-publish.html) for the full process.

## Install from a repository or file

You can manually install a plugin that is not listed in the market, or a specific package supplied by its author. Click the **Install (+)** button in the lower-right corner of the installed plugins or market page.

### Install from a URL

1. Select **Install from URL**.
2. Enter the plugin's Git repository URL supplied by its author, such as `https://github.com/author/plugin-repository`.
3. Confirm the source, install, and check its status on the **Installed** page.

Use the code repository URL, rather than a tutorial, a WebUI address, or an arbitrary webpage.

### Install from a file

1. Obtain the plugin's `.zip` package from its author.
2. Select **Install from File**, upload the ZIP, and install it.
3. Check that it loads, then configure and use it as documented.

The archive must contain a complete AstrBot plugin. A standalone Python file, MCP configuration, or Skills archive is not a plugin installation package. Installing from a file also does not guarantee offline operation: installing dependencies or accessing external services may still require network access.

## Configuration and management

### Plugin settings and availability

The following settings control different things:

| Location | What it controls |
| --- | --- |
| Extensions → Plugins → the plugin's gear icon | The plugin's own parameters, such as service URLs, credentials, and feature switches. These are typically shared across the AstrBot instance; a plugin may implement more specific settings itself. |
| Config → select a profile → Plugin | Which plugins that profile can use. By default, it uses all plugins that have not been closed; you can select a subset. Save the profile after changes. |
| The persona's capabilities settings | Which tools and skills the current persona can use. For plugins with AI tools, check that the relevant tool is allowed here. |
| Extensions → Handlers | Registered commands, function tools, and other handlers. Commands can have their own enabled state, name, and permission settings. |

**First check that the plugin is open, then check the profile and persona used by the current conversation.** Selecting a closed plugin in a profile does not open it. If you route platforms or conversations to different profiles, edit the one that actually applies.

### Update, reload, close, or delete

On the **Installed** page, you can:

| Action | When to use it |
| --- | --- |
| Update | Download the author's new code. Read the changes first and back up configuration and data for important plugins. |
| Reload | Load the existing code again, for example after fixing dependencies or editing code. Reloading does not download a new version. |
| Open / Close plugin | Activate or stop the plugin. Close it when you temporarily do not need it, keeping its files for later use. |
| Handlers | Inspect the commands, tools, and other handlers registered by the plugin. |
| Delete | Uninstall a plugin. The dialog lets you separately choose whether to also delete its configuration and persistent data. |

Pay attention to the options for deleting plugin configuration files and persistent data. Leave the corresponding option unchecked if you want to retain settings or business data.

## Plugins, MCP, and Skills

| Extension | Main purpose | Learn more |
| --- | --- | --- |
| Plugins | Python extensions integrated into AstrBot's message and AI workflows, with commands, tools, event handlers, pages, and more. | This page and the [Plugin Development Guide](/en/dev/star/plugin-new.html) |
| MCP | Connect independent tool services through the MCP protocol so models can call their tools. | [MCP](/en/use/mcp.html) |
| Skills | Provide task instructions, workflows, reference materials, and scripts to guide an agent. | [Skills](/en/use/skills.html) |

They can work together. A plugin may provide tools and bundle a Skill explaining how to use them. Plugin-bundled Skills appear under **Extensions → Skills** and can be enabled or disabled. Their files are managed by the plugin and cannot be edited or deleted directly through the local Skills page.

## Troubleshooting

### Installation fails, or the market does not load

Read the error and logs in the installation dialog. For download timeouts or connection failures, check whether **the device or container running AstrBot** can reach the plugin source, code repository, and dependency download services. Access from your browser does not prove that AstrBot's environment can reach them.

For URL installations, check the repository address. For file installations, check that the ZIP is complete. If a version incompatibility warning appears, check the requirements and choose compatible AstrBot and plugin versions.

### A plugin fails to load

Read the error under **Failed to Load Plugins**, or open **Data & Logs → Logs** for details.

- **Missing Python dependency**: install the dependency as documented by the plugin. The logs page also provides a Pip package installation option. Install into the Python environment actually running AstrBot; with Docker, installing only on the host is insufficient.
- **Missing external program or service**: configure the required program, account, or service according to the plugin documentation.
- **Code errors or incompatible versions**: check the plugin and AstrBot versions, review known issues, and contact the author if necessary.

After fixing the problem, click **Reload**. You do not need to restart the entire AstrBot process just to reload a failed plugin.

### Installation succeeds, but the bot does not respond

Check in this order:

1. The plugin is open and has no loading errors.
2. The profile applied to the current conversation allows it.
3. Its parameters are complete and any external service is available.
4. The command name, prefix, arguments, platform, and permissions match the instructions.
5. For AI tools, the current model supports tool calling and the current persona allows the relevant tools.

Not every plugin has chat commands, and the model does not call every available tool for every message. Start with the author's simplest example before trying more complex requests.

### How do I report a problem?

Use the plugin repository's Issues page or the author's stated support channel. Include the AstrBot version, plugin version, messaging platform, deployment method, reproduction steps, and relevant error logs. Do not publish API keys, tokens, or other credentials.

## Develop your own plugin

If existing plugins do not meet your needs, you can build one in Python. Basic Python and Git / GitHub experience is recommended. Follow this learning path:

1. **Create a project**: follow the [Plugin Development Guide](/en/dev/star/plugin-new.html) and create a repository from the [helloworld template](https://github.com/Soulter/helloworld). An `astrbot_plugin_` name prefix is recommended.
2. **Set up development**: place the repository in AstrBot's `data/plugins/<plugin-directory>/` and fill in `metadata.yaml` so AstrBot can identify its name, version, author, and other metadata.
3. **Build a minimal feature**: start with a command that receives a message and replies. See [Message Event Listening](/en/dev/star/guides/listen-message-event.html) and [Sending Messages](/en/dev/star/guides/send-message.html), then test with your bot.
4. **Add capabilities gradually**: introduce [AI tools and model interaction](/en/dev/star/guides/ai.html), [plugin configuration](/en/dev/star/guides/plugin-config.html), [data storage](/en/dev/star/guides/storage.html), or [plugin pages](/en/dev/star/guides/plugin-pages.html) as needed. Reload through the WebUI after code changes.
5. **Document usage**: describe features, installation, commands or tools, configuration, dependencies, supported platforms, and version requirements in the README. Declare required Python dependencies and complete the plugin metadata.
6. **Publish**: push the code to GitHub and follow the [publishing guide](/en/dev/star/plugin-publish.html) to submit through [AstrBot Cloud](https://cloud.astrbot.app/publish). Publishing requires an AstrBot Cloud account.

The development guide covers environment setup and API usage in detail. For a first plugin, get a simple command working before adding configuration, tools, or external services; this makes problems easier to diagnose.
