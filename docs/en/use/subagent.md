# Subagents {#agent-handsoff-and-subagent}

Subagents are a native **Built-in AI** capability in AstrBot. Main can continue working while delegating tasks to background workers with independent contexts. No separate plugin installation or activation is required.

## Configuration

Open **Built-in AI → Subagents**, enable orchestration, and click **Save**. Settings are global and apply after saving.

| Setting | Meaning |
| --- | --- |
| Concurrent workers per session | Defaults to 3. Additional tasks wait for an execution slot. |
| Task timeout | Includes time waiting for a slot; defaults to 600 seconds. |
| Maximum steps per turn | Defaults to 30 and never exceeds main's step budget. |

![Native subagent configuration](images/subagent-create-en.png)

## Expert templates

An expert defines a name, task description, optional model provider, and persona. Names start with a lowercase letter and contain up to 64 lowercase letters, digits, or underscores.

Selecting a persona inherits its system prompt, tools, and initial dialogue. Alternatively, configure a custom prompt and tools. An empty tool list disables tools. All-available selection still applies tool activation, plugin scope, and execution permissions.

An unset provider follows the current conversation. Without an expert template, main can create a generic worker using its available delegable tools. Workers do not inherit main's entire chat history: include relevant context and constraints in each task.

The main agent's system prompt lists available expert names and purposes, along with optional model providers. The `spawn_agent` tool definition stays fixed, without an expert catalog or dynamic enums. The selected expert is resolved from current configuration when called; its full persona instructions and preset dialogue apply to the worker.

## Execution and continuation

`spawn_agent` returns an agent ID after opening its runtime session, without waiting for the model task to complete. Main uses `list_agents` for status, `wait_agent` to wait, `get_agent_result` to read results, `send_message` for further instructions, and `cancel_agent` to stop one task.

Both `spawn_agent` and `send_message` accept a `messages` array using the same component format as `send_message_to_user`. These two tools currently support `plain` (`text`), `image`, and `file` (`path` or `url`). Initial images become model image input, while files are references the worker can read with its tools. Original user-message images are never inherited automatically. Native follow-ups are currently flattened to text retaining image and file references; other runtimes receive the original structured input.

```json
{
  "template": "researcher",
  "messages": [
    {"type": "plain", "text": "Analyze this chart and consult the report"},
    {"type": "image", "path": "chart.png"},
    {"type": "file", "path": "report.pdf"}
  ]
}
```

Relative image paths resolve from the current session workspace. Absolute local paths within the caller's permissions and sandbox file paths are also supported. `send_message` uses the same `messages` input and additionally requires the target `agent_id`.

Results are addressed to the direct parent runtime/session. Delivery first calls the parent's active turn's `steer()` and waits for its durable-consumption receipt in an independent notification task. Rejected or unconsumed input is queued through the normal message pipeline with the exact parent session attached; switching the UMO's selected conversation does not redirect the result. Result bodies are carried in the input itself, without a separate step-start injection or delivery checkpoint. Further instructions steer a running worker or start its next turn with the same private history. Workers cannot spawn more workers.

The **Worker progress** section shows states, completed steps, results, and errors. Select a worker to inspect its execution record. Editing an expert does not change already-started workers.

## Persistence and recovery

Public agent IDs, runtime names, runtime session IDs, direct parent session references, and input/result records are persisted by UMO and owning main conversation. Users sharing a conversation share its subagents; isolation follows the main UMO/conversation without an additional sender boundary. Each input retains its own caller identity and permissions. Sender information is retained only as metadata. Each runtime persists its own private history. After restart, unfinished and queued inputs are marked interrupted and are never replayed automatically. Inspect interrupted records, then use `send_message` to send new instructions to the same conversation. The built-in runtime retains complete steps without replaying in-flight tools. Switching main conversations keeps completed results bound to their original parent. Deleted or stopped parents are not woken.

## Agent runtimes

The bundled `astrbot` runtime owns native sessions, history, hooks, model execution, and native capabilities. Main agents and workers use the same session/turn contract; the native tool loop is an implementation detail. Core prepares message inputs and presents outputs. The shared subagent service maintains public identities, accepted tasks, concurrency limits, timeouts, and result delivery without directly reading or writing runtime-owned history storage. Delivery confirmation uses the parent session’s public history view.

Runtime adapters receive typed input through `AgentInput.content`: `PlainInput`, `ImageInput`, and `FileInput` retain the `plain`, `image`, and `file` semantics. These are immutable data objects without IM serialization or media download methods. Tool requests and persisted task records retain the existing `messages` JSON format; conversion happens at the runtime boundary.

An `AgentRuntime` opens or restores an `AgentSession`. `session.run_turn(input)` returns an independently executing turn with replayable `events()`, `result()`, `cancel()`, queued `follow_up()`, and optional `steer()` at a safe boundary. Cancellation of an output reader or result waiter does not implicitly cancel execution. The owner explicitly cancels the turn when its pipeline stops.

Extensions can register a runtime with `ctx.subagents.register_runtime(name, runtime)` and select it using `spawn_agent`'s `runtime` parameter. The default is `astrbot`; an ACP runtime and continuous voice sessions are not included in this phase. Existing third-party main-agent execution paths remain unchanged.

`list_agents` returns each agent's public `agent_id`, `runtime`, and opaque runtime-owned session ID in `conversation_id`. `send_message` resolves the runtime and session by agent ID. `owner_conversation_id` identifies the separate owning main conversation.

## Entry points and APIs

Expert management and worker progress share **Built-in AI → Subagents** at `/subagent`. The former plugin-extension entry is replaced by this native page.

Native APIs are `/api/v1/subagents/config`, `/api/v1/subagents/available-tools`, and `/api/v1/subagents/runtime`; they require the `config` scope. The Dashboard configuration routes under `/api/subagent/*` remain compatible.
