# Agent Handoffs and SubAgent Orchestration

SubAgent orchestration lets the main Agent delegate a well-defined task to a specialized Agent through a `transfer_to_<name>` tool. It is useful for grouping search, file-processing, or domain-specific tools behind focused roles while the main Agent continues to interpret the request and compose the final response.

The feature is currently marked **experimental**. Validate model behavior, tool permissions, and cost in a non-critical profile first.

![SubAgent orchestration page](https://files.astrbot.app/docs/source/images/subagent/image.png)

## How it currently works

When orchestration is enabled:

1. The main Agent keeps its existing tools and additionally receives a `transfer_to_*` handoff tool for every enabled SubAgent.
2. The main Agent decides whether to delegate from the handoff description. It passes a task description and can also pass image references or launch a longer task in the background.
3. The SubAgent runs with its own system prompt, opening dialogue, model, and tool set.
4. A synchronous result is returned to the main Agent so it can continue the conversation. A background handoff wakes the main Agent again after completion so the user can be notified.

![Handoff flow](https://files.astrbot.app/docs/source/images/subagent/1.png)

> [!IMPORTANT]
> Enabling SubAgents does not automatically remove domain tools from the main Agent. Tools assigned to SubAgents are hidden from the main tool set only when **Deduplicate main LLM tools** is also enabled. Main-Agent tools that do not overlap remain available.

## Configuration

Open **SubAgents** in the WebUI sidebar.

### 1. Prepare a Persona

The current UI requires each SubAgent to be bound to a Persona. The SubAgent reads these Persona fields:

- system prompt;
- opening dialogue;
- tool list. When the Persona means “all tools,” the SubAgent receives all currently active regular tools and applicable Computer tools, but not other `transfer_to_*` tools.

Persona Skills and the custom error reply are not currently inherited as isolated SubAgent settings. Put required behavioral rules in the Persona system prompt and grant only the tools needed for that role.

### 2. Add a SubAgent

Select **Add SubAgent** and configure:

- **Agent name**: must start with a lowercase ASCII letter and contain only lowercase letters, digits, and underscores. It must also be globally unique. For example, `web_search` creates `transfer_to_web_search`.
- **Chat Provider (optional)**: overrides the chat model used by this SubAgent. When empty, AstrBot follows the provider resolved for the current session.
- **Persona**: supplies the prompt, opening dialogue, and tool permissions.
- **Description for the main LLM**: becomes the handoff tool description. State when to delegate, what input is required, and what the Agent returns; do not copy a long Persona prompt here.

After saving, use the card preview to verify the tool name and description shown to the main Agent. Individual SubAgents can be disabled independently.

### 3. Decide whether to deduplicate tools

Deduplication is off by default, which is useful during rollout: the main Agent can either call a tool directly or delegate the task.

With **Deduplicate main LLM tools** enabled, every same-named tool assigned to an enabled SubAgent is removed from the main Agent. This reduces the main tool schema but makes that capability depend on a handoff. Before enabling it, verify that:

- each SubAgent description gives the model a reliable routing signal;
- no Persona accidentally grants all tools;
- critical tools work with the model selected for the SubAgent.

## Design guidance

- Give each SubAgent one responsibility that is easy to recognize, such as “research public sources and return a cited summary.”
- State boundaries clearly so several SubAgents do not all claim the same class of task.
- Use a smaller model for low-risk, structured work and a stronger model for complex reasoning or multi-tool work.
- Apply least privilege, especially for shell, file-write, browser, and external-system tools.
- Current orchestration is a single handoff layer from the main Agent. Handoff tools are excluded from a SubAgent's tool set, so do not design for recursive multi-level delegation.

## Current limitations

- The feature is experimental and its configuration and behavior may continue to change.
- SubAgents do not persist separate conversation histories. Each handoff builds context from that invocation, the Persona's opening dialogue, and tool results.
- Persona Skills are not currently isolated and inherited by SubAgents.
- SubAgents use profile-wide settings such as `agent_runner.config.misc.max_steps`, streaming behavior, and tool timeout; there is no separate per-SubAgent step limit.
