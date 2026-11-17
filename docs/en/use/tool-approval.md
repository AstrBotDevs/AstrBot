# Tool Approval and Permission Modes

You can require approval before certain tools run. When the agent wants to call one of them, it first asks the user who started the conversation, and the tool runs only after that user allows it. ChatUI also offers a per-conversation permission mode that narrows access or skips the prompts in the current conversation.

## Choose the tools that need approval

Set these in the AI settings of a configuration file (the "Other Settings" group; you can search for them):

| Setting | Description |
| --- | --- |
| Tools requiring approval (`agent.config.misc.tool_approval.tools`) | A list of tool names, such as `astrbot_execute_shell`, `astrbot_file_write_tool`, or `future_task`. Empty means no approval. |
| Tool approval timeout (seconds) (`agent.config.misc.tool_approval.timeout`) | Default 120. A timeout counts as not approved and the tool does not run. |

This applies only to the built-in AstrBot agent runner. Approval never widens access: the tool still runs under the permission policy of the [local environment](./astrbot-agent-sandbox.md#local-environment).

## How to approve

When a listed tool is called, AstrBot sends the tool name and its full arguments to the requester and waits:

- **ChatUI**: an approval card appears above the input box with **Allow**, **Don't ask again in this conversation**, and **Deny**. While it waits, the tool card shows "Waiting for approval". Afterwards a one-line record of the outcome (Allowed / Not approved / Expired) goes into the run details under the reply, with the tool calls; this also applies to approvals that background sub-agents ask for. The outcome comes from the backend: a click that arrives after the request timed out changes nothing.
- **Other platforms**: a message with the arguments and a four-digit code. Platforms with buttons also get **Allow** and **Deny** buttons. Replying with the code approves; any other message cancels.

Only the requester's own reply counts; replies from other group members are ignored. If the arguments are long, text platforms show the first 1500 characters and say how much is hidden. Deny if you cannot see everything you are approving. Arguments above 100,000 characters are never sent for approval and the tool does not run.

When a tool is denied, times out, or the request cannot be delivered, the model is told the tool did not run and does not retry on its own.

## Scheduled tasks

With `future_task` in the list, creating or editing a scheduled task needs approval, and the card names the task. Approving it also approves the other listed tools that the task uses when it runs on schedule, so those runs are not interrupted. In detail:

- An edit keeps this grant only if the edit itself was approved.
- A task that creates another scheduled task while running still needs approval; the grant does not pass to the new task.
- When a task created without approval calls a listed tool, the task's creator is asked. Tasks with no recorded creator do not run those tools.
- Background wakeups, such as a scheduled task firing or a sub-agent result, never count as the user's answer to an approval.

On platforms other than ChatUI, a scheduled task is never offered for approval with truncated arguments: arguments longer than 1500 characters are refused.

## ChatUI permission modes

In ChatUI, the button next to **+** in the input box shows the conversation's mode (**Ask for approval** by default). Click it to switch:

| Mode | Files and execution | Approval |
| --- | --- | --- |
| Workspace | If the role allows the whole environment, this narrows it to the conversation's workspace; shell and Python must run under process isolation | In the local environment, file read/write/edit/search, shell, and Python tools stop asking; other listed tools still ask |
| Ask for approval (default) | As configured for the role | Listed tools ask every time |
| Full access | As configured for the role | No tool asks, except creating or editing a `future_task` |

Keep in mind:

- **Modes only narrow access; they never widen it.** The [local permission policy](./astrbot-agent-sandbox.md#local-environment) stays the upper limit. Full access does not let a member execute code or access the whole environment.
- **The Workspace mode is not the same as the policy's "Workspace" file scope.** The policy is the limit an administrator sets for a role; the mode is a smaller scope a user picks for one conversation. If the role is already limited to the workspace or has file access off, the Workspace mode does not change access.
- The Workspace mode skips approval only in the local runtime. With a third-party sandbox, listed tools still ask.
- **Don't ask again in this conversation** on an approval card approves this call and stops the conversation from asking, including queued tool calls and running sub-agents of the current turn. It never widens access: from Ask for approval, the conversation switches to Full access; from Workspace, it stays confined to the workspace and sandboxed, and the mode button shows **Workspace · not asking**. Choose Workspace in the menu again to ask again. Like the mode, this is saved per conversation and cleared when the conversation is deleted or you log out; it never passes to scheduled tasks, and creating or editing a `future_task` still asks.
- A mode change takes effect at once: later tool calls and sub-agents of the running turn use the new mode.
- A thread starts with the main conversation's mode. **Don't ask again in this conversation** in a thread affects only the thread, not the main conversation.
- A scheduled task created or edited in the Workspace mode is narrowed to the workspace when it runs. Full access does not pass to scheduled tasks: when they run, the scheduled-task rules above still apply.
- The mode is saved in the browser. The backend keeps it only while the server runs and forgets it when the conversation or thread is deleted.

For API clients, chat requests accept `permission_mode` (`workspace`, `ask`, or `full`). `PUT /api/v1/chat/sessions/{session_id}/permission-mode` changes the mode while a reply is running. It only accepts the caller's own WebChat sessions and returns 403 otherwise.

## Plugin developers

The approval card is an `ActionRow` message component. For the extra fields that ChatUI supports, see [Sending messages: interactive buttons](../dev/star/guides/send-message.md#interactive-buttons).
