# Built-in Agent Runner

By default, AstrBot uses the built-in Agent Runner as the default executor. You don't need to configure anything to use AstrBot's powerful built-in Agent Runner.

![image](https://files.astrbot.app/docs/source/images/astrbot-agent-runner/image.png)

With the built-in Agent Runner, you can use AstrBot's [MCP Server](/use/mcp), [Knowledge Base](/use/knowledge-base), [Web Search](/use/websearch), and persona features.


## Dynamic tool discovery

In the WebUI, open **Config → AI → Other Settings**, set **Tool Schema Mode** to **Dynamic (on demand)**, and save. The configuration key is `agent.config.misc.tool_schema_mode` with the value `dynamic`. Use a chat model that supports function calling.

The model starts with a search tool. It can find built-in, plugin, and connected MCP tools available to the current run. Each search loads up to three matches. The model receives their full definitions on the next request and can search again as needed. For example, after connecting a GitHub MCP server with a pull request tool, ask which pull requests still need review.

Persona choices, session plugin settings, and built-in capability settings determine the candidate tools. A call still goes through permission and argument checks. The next agent run starts with a fresh set of loaded tools. Search adds a model round and is best suited to larger tool catalogs.

**Full schema**, the default, sends complete definitions on every request. **Skills-like (two-stage)** sends all names and descriptions first, then requests arguments for the selected tools.
