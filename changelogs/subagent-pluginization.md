# Asynchronous subagents

- The Subagent extension is bundled under `astrbot/builtin_stars/astrbot_plugin_subagent` and uses the standard built-in plugin loading, configuration, and view mechanisms.
- Main delegates tasks through the Subagent extension while workers run concurrently with private histories and configurable providers, personas, prompts, and tools.
- `spawn_agent` accepts an initial task, expert template, display name, and provider override. Its parameters list available chat providers; its result includes the actual name and resolved provider ID.
- Main can list workers, wait for results, read results repeatedly, send follow-up instructions, and cancel individual workers. Follow-ups steer an active turn or start the next turn with the same identity and history.
- Subagent management provides expert creation, editing, activation, and deletion, plus read-only progress with worker names, provider IDs, states, results, and execution records. The view supports light/dark themes and responsive layouts.
- Results return to main within the original session, conversation, and sender scope. States and pending input persist across restarts; interrupted work resumes on request without replaying tools automatically.
- Core SDK capabilities include Agent lifecycle hooks, caller-owned execution contexts, background task registration, and per-tool timeouts.
