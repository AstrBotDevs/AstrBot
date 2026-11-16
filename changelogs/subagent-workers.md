# Native asynchronous subagents

- Built-in AI can delegate background tasks with independent histories and optional personas and models. Generic subagents require no saved configuration or plugin installation.
- Move **SubAgent Orchestration / Subagent Management** from the sidebar to **Config → AI → Capabilities → Subagents → Configure Specialized Agents**. Keep `/subagent` accessible. Selection, concurrency, and timeout settings now belong to each profile.
- Support text, images, and file references when starting tasks. Follow-ups retain the agent's history and currently pass attachments as text references. Parent-message images are not forwarded automatically.
- Share subagents within their owning conversation and return results to that conversation. After a restart, unfinished tasks are marked interrupted without replay; send new instructions to continue.
- Migrate `agent_runner` to `agent`, map `local` to `astrbot`, and import legacy expert configurations without changing existing conversations or history.
- Replace whole-configuration subagent APIs with `/api/v1/agent-configs` and `/api/v1/agent-runtimes`. Remove `/api/v1/subagents/available-tools` and `/api/subagent/available-tools`.
- Add `ctx.agent.run_turn()` for programmatic turns, metadata for hooks, follow-ups, steering, and caller-managed output through `send_to_user=False` and `output.ready`. Extensions can register an Agent runtime through `ctx.agent.register_runtime()`.
- Export plugin-facing Agent types from `astrbot.api.agents`. Runtime consumers use `event.payload` instead of `event.data` and `result.content` instead of `result.chain`.

See the [subagent setup guide](../docs/en/use/subagent.md) and [Agent API guide](../docs/en/dev/star/guides/ai/agent.md) for usage and migration details.
