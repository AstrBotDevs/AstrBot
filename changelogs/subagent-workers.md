# Native asynchronous subagents

- Keep subagents in Built-in AI at `/subagent`, with global expert configuration and worker progress on one native page. The former plugin-extension entry is replaced by Built-in AI → Subagents.
- Main delegates through `spawn_agent` and manages workers with list, wait, result, message, and cancellation tools. Workers have private histories and configurable personas, models, tools, concurrency, timeouts, and step budgets.
- Continue workers with the same identity and conversation context. Persist worker state and result receipts; recover unfinished work as interrupted without replaying in-flight tools.
- Integrate main-agent construction and lifecycle through `astrbot/core/astr_agent_runtime/main_agent/subagent.py`. Register, recover, and close worker state through core lifecycle rather than plugin loading.
- Remove eager expert orchestration. Keep expert and provider catalogs in system instructions, use fixed control-tool schemas, and resolve expert configurations only when spawning a worker.
- Use explicit `messages` components for spawning and messaging workers. Initial inputs support text, images, and file references; follow-ups currently become text with attachment references. Remove automatic inheritance of parent-event images.
- Retain native `/api/v1/subagents/*` APIs, the Dashboard configuration routes, and legacy Agent handoff SDK compatibility.
- Separate public agent sessions from their runtime-owned conversations. Add an `AgentRuntime` session/turn contract with `AstrAgentRuntime` as the bundled implementation; extensions can register other runtimes without changing the tools or session store.
- Remove synthetic parent-agent IDs and redundant worker/runtime state. Persist input executions and result delivery stages directly, and keep native history preparation and steering inside the built-in runtime.
- Open runtime sessions before returning from `spawn_agent`, then execute model tasks asynchronously. Restore interrupted records without replaying queued inputs; continue existing runtime sessions by agent ID.

- Move built-in main-agent execution, session serialization, history, hooks, and steering behind the runtime boundary. Keep common message preprocessing and output presentation in Core; preserve existing third-party execution paths.

- Deliver worker results to their direct parent runtime/session through `steer()`, queuing unconsumed inputs as targeted pipeline wakeups. Remove subagent-specific step injection and delivery checkpoints while retaining existing plugin lifecycle hooks.

- Share subagents within the owning UMO/conversation instead of isolating them by sender. Preserve each accepted input's caller and permissions, and retain sender metadata for result wakeups.

- Consolidate native construction, tools, computer environments, hooks, and tool execution under `core/astr_agent_runtime`. Move runtime-independent subagent management to `core/subagents` and queue-based wakeups to `core/agent_wakeup.py`. Keep documented `core.astr_agent_context` imports as re-exports of the same classes.

- Expose plugin-facing agent contexts and message types through `astrbot.api.agents`; add public tool-result, conversation, session-filter, data-path, and message-session exports. Update plugin development examples to use the API facade while retaining existing Core imports and the `astrbot.api.agent` decorator.
