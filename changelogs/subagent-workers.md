# Native asynchronous subagents

- Open reusable agent management from Configuration → AI → Capabilities → Subagents → Configure Specialized Agents. Remove its standalone sidebar entry while retaining `/subagent`; generic subagents work without creating saved agent configurations.
- Main delegates through `spawn_agent` and manages workers with list, wait, result, message, and cancellation tools. Workers have private histories and configurable personas, models, tools, concurrency, timeouts, and step budgets.
- Continue workers with the same identity and conversation context. Persist worker state and result receipts; recover unfinished work as interrupted without replaying in-flight tools.
- Integrate main-agent construction and lifecycle through `astrbot/core/astr_agent_runtime/main_agent/subagent.py`. Register, recover, and close worker state through core lifecycle rather than plugin loading.
- Remove eager expert orchestration. Keep selected agent configuration catalogs in system instructions, use fixed control-tool schemas, and resolve agent configurations only when spawning a worker.
- Use explicit `messages` components for spawning and messaging workers. Initial inputs support text, images, and file references; follow-ups currently become text with attachment references. Remove automatic inheritance of parent-event images.
- Use `/api/v1/agent-configs` for reusable agent configuration CRUD and `/api/v1/agent-runtimes` for runtime discovery. Retain subagent tools and legacy Agent handoff SDK compatibility.
- Remove the unused tool catalog endpoints `/api/v1/subagents/available-tools` and `/api/subagent/available-tools`.
- Separate public agent sessions from their runtime-owned conversations. Add an `AgentRuntime` session/turn contract with `AstrAgentRuntime` as the bundled implementation; extensions can register other runtimes without changing the tools or session store.
- Remove synthetic parent-agent IDs and redundant worker/runtime state. Persist input executions and result delivery stages directly, and keep native history preparation and steering inside the built-in runtime.
- Open runtime sessions before returning from `spawn_agent`, then execute model tasks asynchronously. Restore interrupted records without replaying queued inputs; continue existing runtime sessions by agent ID.

- Move built-in main-agent execution, session serialization, history, hooks, and steering behind the runtime boundary. Keep common message preprocessing and output presentation in Core; preserve existing third-party execution paths.

- Deliver worker results to their direct parent runtime/session through `steer()`, queuing unconsumed inputs as targeted pipeline wakeups. Remove subagent-specific step injection and delivery checkpoints while retaining existing plugin lifecycle hooks.

- Share subagents within the owning UMO/conversation instead of isolating them by sender. Preserve each accepted input's caller and permissions, and retain sender metadata for result wakeups.

- Consolidate native construction, tools, computer environments, hooks, and tool execution under `core/astr_agent_runtime`. Move native subagent orchestration from `core/subagents` to `core/astr_agent_runtime/subagents`, and queue-based wakeups to `core/agent_wakeup.py`. Keep documented `core.astr_agent_context` imports as re-exports of the same classes.

- Expose plugin-facing agent contexts and message types through `astrbot.api.agents`; add public tool-result, conversation, session-filter, data-path, and message-session exports. Update plugin development examples to use the API facade while retaining existing Core imports and the `astrbot.api.agent` decorator.

- Add `Context.agent.run_turn()` for programmatic runtime inputs with shared Core admission, runtime-owned history, queued follow-ups, safe-boundary steering, session status, and optional automatic response presentation. Explicit tool and plugin sends remain unchanged.

- Rename SubAgent Orchestration to Subagent Management at the existing `/subagent` route. Replace expanded rows and global settings with two-column cards and per-agent dialogs; remove search and execution progress from the management page; move selection, concurrency and timeout settings into each profile’s native runtime configuration.
- Embed `AgentConfig` under each profile’s `agent`, replacing `agent_runner` and mapping `local` to `astrbot`. Store reusable AgentConfigs in `agent_configs`, preserving runtime-specific JSON and stable UUID references. Import legacy experts before deleting their source data.
- Replace the spawn tool’s template/runtime pair with `config_id`. Enforce selected configurations and parent capabilities at invocation, snapshot native configuration per session, and keep existing session histories intact.

- Simplify the AstrBot agent editor to name, description, persona, and chat model. Inherit other execution settings from the parent when creating a native worker; persist only optional persona/provider overrides in reusable native configurations.

- Move the sidebar Subagent Management entry into the profile’s subagent capability settings. Explain generic workers first, make specialized configurations optional, and open management in a dialog, preserving the current profile edits and refreshing available configurations after changes.

- Share native runner initialization, turn execution, steering settlement and history commits between main agents and subagents. Remove the step-start/step-end hooks and per-step child history writes.

- Keep plugin agent access behind `ctx.agent`, including runtime registration. Inject configuration storage, the runtime registry and delegation services from the core lifecycle instead of exposing them on plugin Context.

- Standardize native runtime output with typed attributed events, portable content, request and tool execution boundaries, and final usage snapshots. Replace `event.data` with `event.payload` and `result.chain` with `result.content`; retain existing plugin hooks and third-party runner execution.

- Admit main-agent inputs through public `AgentInput` and dispatch registered runtimes from both normal messages and `ctx.agent`. Keep native request/configuration construction inside the AstrBot runtime, recheck queued admission after runtime locks, and preserve existing third-party runner paths.
