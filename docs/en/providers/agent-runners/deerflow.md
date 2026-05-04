# Connect to DeerFlow

Starting from v4.19.2, AstrBot supports connecting to the [DeerFlow](https://github.com/bytedance/deer-flow) Agent Runner.

## Preparation: Deploy DeerFlow

If you have not deployed DeerFlow yet, please complete installation and startup by following the official DeerFlow documentation:

- [DeerFlow GitHub Repository](https://github.com/bytedance/deer-flow)
- [DeerFlow Official Website](https://deerflow.tech/)
- [DeerFlow Configuration Guide](https://github.com/bytedance/deer-flow/blob/main/backend/docs/CONFIGURATION.md)

Make sure DeerFlow is running properly and that AstrBot can reach the DeerFlow gateway. By default, the DeerFlow gateway address is `http://127.0.0.1:2026`.

> [!TIP]
> - `API Base URL` must start with `http://` or `https://`.
> - If AstrBot and DeerFlow run in different containers or on different hosts, replace `127.0.0.1` with the actual reachable LAN address, hostname, or domain of your DeerFlow service.

## Configure DeerFlow in AstrBot

In the WebUI, click "Model Provider" -> "Add Provider", select "Agent Runner", select "DeerFlow", and enter the DeerFlow configuration page.

Fill in the following fields:

- `API Base URL`: DeerFlow API gateway URL. Default: `http://127.0.0.1:2026`
- `DeerFlow API Key`: Optional. Fill this if your DeerFlow gateway is protected by Bearer auth
- `Authorization Header`: Optional. Custom Authorization header value. This takes precedence over `DeerFlow API Key`
- `Assistant ID`: Maps to LangGraph `assistant_id`. Default: `lead_agent`
- `Model name override`: Optional. Overrides the default model configured in DeerFlow
- `Enable thinking mode`: Whether to enable DeerFlow thinking mode
- `Enable plan mode`: Maps to DeerFlow `is_plan_mode`
- `Enable subagent`: Maps to DeerFlow `subagent_enabled`
- `Max concurrent subagents`: Maps to `max_concurrent_subagents`. Effective only when subagents are enabled. Default: `3`
- `Recursion limit`: Maps to LangGraph `recursion_limit`. Default: `1000`

After filling in the configuration, click Save.

> [!TIP]
> - If DeerFlow already has a default model configured on its side, you can leave `Model name override` empty.
> - Only enable `plan mode` or `subagent` related options when the corresponding DeerFlow capabilities are already configured on the DeerFlow side.

## Select Agent Runner

Go to the Configuration page in the left sidebar, click "Agent Execution Method", select "DeerFlow", then select the ID of the DeerFlow Agent Runner you just created in the new configuration option below, and click "Save" in the bottom right corner to complete the configuration.

## Common Checks

If requests are not being executed through DeerFlow correctly, check the following first:

- whether the DeerFlow service is running properly
- whether `API Base URL` is reachable from the AstrBot environment
- whether the authentication settings are correct
- whether `Assistant ID` matches an actual available assistant in DeerFlow
