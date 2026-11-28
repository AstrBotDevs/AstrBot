# Built-in Agent Runner

By default, AstrBot uses the built-in Agent Runner as the default executor. You don't need to configure anything to use AstrBot's powerful built-in Agent Runner.

![image](https://files.astrbot.app/docs/source/images/astrbot-agent-runner/image.png)

With the built-in Agent Runner, you can use AstrBot's [MCP Server](/use/mcp), [Knowledge Base](/use/knowledge-base), [Web Search](/use/websearch), and persona features.


## Dynamic tool discovery

In the WebUI, open **Config** and select the profile you want to edit. Open **AI → Other Settings**, set **Tool Schema Mode** to **Dynamic (on demand)**, and save. The configuration key is `agent.config.misc.tool_schema_mode` with the value `dynamic`. Use a chat model that supports function calling.

The model uses three fixed functions to search, describe, and call built-in, plugin, or connected MCP tools available to the current run. Search returns up to three new matches. The model then asks for a selected tool's schema before calling it. If it already knows the tool's name, it can describe it without searching. For example, after connecting a GitHub MCP server with a pull request tool, ask which pull requests still need review.

Persona choices, session plugin settings, and built-in capability settings determine the candidate tools. A call still goes through permission and argument checks. Each agent run starts with no described tools. Search and describe can add model requests, so this mode works best for larger catalogs. The top-level function definitions stay fixed during discovery, but actual prompt-cache savings depend on the provider and model.

**Full schema**, the default, sends complete definitions on every request. **Skills-like (two-stage)** sends all names and descriptions first, then requests arguments for the selected tools.
