"""Ask a person to approve listed tools before they run.

Tools listed in ``agent.config.misc.tool_approval.tools`` wait for the
requester's approval: a card with buttons in ChatUI, buttons where the
platform supports them, and a reply code everywhere. Approving the creation or
edit of a scheduled task (``future_task``) also approves the listed tools the
task uses when it later runs unattended. ChatUI's per-conversation permission
modes (see ``permission_mode.py``) can skip the prompt: "full" and
"workspace_no_ask" for everything except scheduled tasks, "workspace" for the
Local tools it actually confines.
"""

import asyncio
import json
import secrets

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool_executor import CURRENT_TOOL_CALL_ID
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.permission_mode import (
    NO_ASK_MODES,
    WORKSPACE_MODES,
    get_permission_mode,
    set_conversation_permission_mode,
)
from astrbot.core.astr_agent_runtime.tools.computer_tools.util import (
    is_local_runtime,
)
from astrbot.core.astr_agent_runtime.tools.cron_tools import (
    TASK_APPROVAL_GRANTED,
    TOOL_APPROVAL_GRANT_KEY,
)
from astrbot.core.i18n import translate
from astrbot.core.message.components import ActionRow, Button, Json, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.session_lock import session_lock_manager
from astrbot.core.utils.session_waiter import FILTERS, SessionFilter, SessionWaiter

# Action ID of the approve and reject buttons; the "allow for this
# conversation" button (ChatUI only) has its own so the client can switch the
# conversation to full access.
TOOL_APPROVAL_ACTION_ID = "astrbot_tool_approval"
TOOL_APPROVAL_CONVERSATION_ACTION_ID = "astrbot_tool_approval_conversation"
SCHEDULED_TASK_TOOL = "future_task"
# Local tools that "workspace" mode confines to the conversation workspace.
WORKSPACE_CONFINED_TOOLS = frozenset(
    {
        "astrbot_file_read_tool",
        "astrbot_file_write_tool",
        "astrbot_file_edit_tool",
        "astrbot_grep_tool",
        "astrbot_execute_shell",
        "astrbot_shell_session",
        "astrbot_execute_python",
    }
)
# The user must see everything they approve: text platforms show at most this
# many characters of arguments and say how many are hidden; a scheduled task
# (an unattended grant) is never asked about with hidden arguments, and
# arguments above the maximum are refused everywhere.
APPROVAL_TEXT_ARGS_CHARS = 1500
APPROVAL_MAX_ARGS_CHARS = 100_000
APPROVAL_TITLE_NAME_CHARS = 40


class _ToolApprovalFilter(SessionFilter):
    """Match approval replies by session and sender, not by the whole group."""

    def filter(self, event) -> str:
        # Wakeups (a scheduled task firing, a sub-agent result) share the
        # session and sender of the conversation but are not the user's
        # answer; they must not resolve a pending approval.
        if isinstance(event, AgentWakeupEvent):
            return "tool_approval:unattended"
        return f"tool_approval:{event.unified_msg_origin}:{event.get_sender_id()}"


async def check_tool_approval(
    tool, run_context: ContextWrapper[AstrAgentContext], tool_args: dict
) -> str | None:
    """Ask the requester to approve a listed tool before it runs.

    Args:
        tool: The tool the model wants to call.
        run_context: The current agent run context.
        tool_args: The arguments the tool would receive.

    Returns:
        None if the tool may run, otherwise the reason (shown to the model)
        why it was not executed.
    """
    event = run_context.context.event
    ctx = run_context.context.context
    approval_config = (
        ctx.get_config(umo=event.unified_msg_origin if event else None)
        .get("agent", {})
        .get("config", {})
        .get("misc", {})
        .get("tool_approval", {})
    )
    grants_task = tool.name == SCHEDULED_TASK_TOOL and tool_args.get("action") in (
        "create",
        "edit",
    )
    if tool.name == SCHEDULED_TASK_TOOL:
        # Cleared on every call so a grant never outlives its own approval.
        TASK_APPROVAL_GRANTED.set(False)
    if tool.name not in (approval_config.get("tools") or []):
        return None
    if not event:
        return f"error: Tool {tool.name} needs approval, but no user can be asked."

    # The conversation's current mode, which follows changes made after this
    # run started (sub-agents keep the event of the turn that spawned them).
    unattended = isinstance(event, AgentWakeupEvent)
    mode = get_permission_mode(event)
    if (
        mode in WORKSPACE_MODES
        and tool.name in WORKSPACE_CONFINED_TOOLS
        # Only the Local runtime is narrowed (get_local_permission_policy
        # confines its files to the workspace in these modes).
        and is_local_runtime(run_context)
    ):
        return None
    # No-ask modes never grant a scheduled task's unattended runs by themselves
    # (unattended runs never get these modes; see get_permission_mode).
    if mode in NO_ASK_MODES and not unattended and not grants_task:
        return None

    approver_id = event.get_sender_id()
    if unattended:
        # A scheduled task asks the user who created it, or runs freely if
        # its creation was approved; a grant cannot spread to further tasks.
        job = None
        if event.source == "cron" and event.source_id:
            job = await ctx.cron_manager.db.get_cron_job(event.source_id)
        payload = job.payload if job and isinstance(job.payload, dict) else {}
        if (
            payload.get(TOOL_APPROVAL_GRANT_KEY) is True
            and tool.name != SCHEDULED_TASK_TOOL
        ):
            return None
        approver_id = payload.get("sender_id")
        if not approver_id:
            return (
                f"error: Tool {tool.name} needs user approval, but this "
                "unattended run has no user to ask, so it was not executed."
            )

    is_webchat = event.get_platform_name() == "webchat"
    args_text = json.dumps(tool_args, ensure_ascii=False, default=str)
    if len(args_text) > APPROVAL_MAX_ARGS_CHARS or (
        grants_task and not is_webchat and len(args_text) > APPROVAL_TEXT_ARGS_CHARS
    ):
        return (
            f"error: Tool {tool.name} was not executed because its arguments "
            f"({len(args_text)} characters) are too long to show for approval. "
            "Split the work into smaller calls or shorten the arguments."
        )
    timeout = coerce_int_config(
        approval_config.get("timeout", 120),
        default=120,
        min_value=1,
        field_name="agent.config.misc.tool_approval.timeout",
    )
    tool_call_id = CURRENT_TOOL_CALL_ID.get()

    async def deliver(message: MessageChain) -> None:
        # A background sub-agent may ask after its turn's reply stream closed;
        # ChatUI then gets the message as a proactive one.
        delivered = await event.send(message)
        if is_webchat and delivered is False:
            if not await ctx.send_message(event.unified_msg_origin, message):
                raise RuntimeError("Approval delivery failed")

    session_id = f"tool_approval:{event.unified_msg_origin}:{approver_id}"
    # A session ID holds one waiter, so concurrent requests take turns.
    async with session_lock_manager.acquire_lock(session_id):
        # While this call waited, "Don't ask again" on another card or a mode
        # change may already cover it.
        if (
            not unattended
            and not grants_task
            and get_permission_mode(event) in NO_ASK_MODES
        ):
            return None
        code = f"{secrets.randbelow(10000):04d}"
        prompt = _approval_prompt(
            event,
            ctx.locale(event.unified_msg_origin),
            tool.name,
            tool_args,
            code,
            timeout,
            grants_task,
            unattended,
        )
        allow_conversation = False
        try:
            approved, allow_conversation = await _wait_for_answer(
                session_id, code, timeout, deliver(prompt)
            )
        except TimeoutError:
            outcome = "expired"
            reason = (
                f"error: Tool {tool.name} was not executed because the approval "
                "request timed out. Do not retry unless the user asks."
            )
        except Exception as exc:
            logger.warning(f"Failed to deliver tool approval: {exc}")
            return (
                f"error: Tool {tool.name} was not executed because we cannot ask "
                f"the user for approval. Approval delivery failed: {exc}"
            )
        else:
            outcome = "approved" if approved else "rejected"
            reason = (
                None
                if approved
                else f"error: The user rejected tool {tool.name}, so it was not "
                "executed. Do not retry unless the user asks."
            )

    if is_webchat and tool_call_id:
        # ChatUI marks the card with what was actually decided: a click can
        # arrive after the request ended and change nothing.
        try:
            await deliver(
                MessageChain(
                    type="approval_result",
                    chain=[
                        Json(data={"tool_call_id": tool_call_id, "outcome": outcome})
                    ],
                )
            )
        except Exception as exc:
            logger.warning(f"Failed to report the approval outcome: {exc}")
    if outcome == "approved":
        if grants_task:
            TASK_APPROVAL_GRANTED.set(True)
        if allow_conversation:
            # Everything in this conversation, including queued calls and
            # running sub-agents, now runs without asking. It never widens
            # access: a workspace conversation stays confined.
            no_ask = (
                "workspace_no_ask"
                if get_permission_mode(event) in WORKSPACE_MODES
                else "full"
            )
            event.set_extra("permission_mode", no_ask)
            set_conversation_permission_mode(event.session_id, no_ask)
    return reason


def _approval_prompt(
    event,
    locale: str,
    tool_name: str,
    tool_args: dict,
    code: str,
    timeout: int,
    grants_task: bool,
    unattended: bool,
) -> MessageChain:
    """Build the approval prompt: a card in ChatUI, text and buttons elsewhere.

    Args:
        event: The event the tool call runs with.
        locale: Reply language of the session (``Context.locale``).
        tool_name: The tool asking to run.
        tool_args: Its arguments.
        code: Reply code that approves this request.
        timeout: Seconds the request stays valid.
        grants_task: Whether approving grants a scheduled task's later runs.
        unattended: Whether the request comes from an unattended run.

    Returns:
        The message to send.
    """

    def text(key: str, **params) -> str:
        return translate(f"tool_approval_{key}", locale, **params)

    if grants_task:
        # The model chooses the name: keep the title one short line.
        name = " ".join(str(tool_args.get("name") or "").split())
        if len(name) > APPROVAL_TITLE_NAME_CHARS:
            name = name[:APPROVAL_TITLE_NAME_CHARS] + "…"
        title = text("task_title", name=name) if name else text("task_title_unnamed")
        notice = text("task_notice")
    else:
        title = text("tool_title", tool=tool_name)
        notice = ""
    args_text = json.dumps(tool_args, ensure_ascii=False, default=str)
    if len(args_text) > APPROVAL_TEXT_ARGS_CHARS:
        args_text = args_text[:APPROVAL_TEXT_ARGS_CHARS] + text(
            "args_cut",
            total=len(args_text),
            hidden=len(args_text) - APPROVAL_TEXT_ARGS_CHARS,
        )
    prompt_text = f"{title}\n{notice}{text('args')}{args_text}\n" + text(
        "how_to", code=code, timeout=timeout
    )
    buttons = [
        Button(
            id=TOOL_APPROVAL_ACTION_ID,
            label=text("allow"),
            style=Button.Style.SUCCESS,
            action=Button.CallbackAction(data={"code": code, "approve": True}),
        ),
        Button(
            id=TOOL_APPROVAL_ACTION_ID,
            label=text("deny"),
            style=Button.Style.DANGER,
            action=Button.CallbackAction(data={"code": code, "approve": False}),
        ),
    ]
    if event.get_platform_name() != "webchat":
        return MessageChain(
            chain=[
                Plain(prompt_text),
                ActionRow(buttons=buttons, action_timeout=timeout, single_use=True),
            ]
        )
    if not unattended:
        # Only ChatUI keeps a per-conversation mode to switch to, and an
        # unattended run must not widen its own permissions.
        buttons.insert(
            1,
            Button(
                id=TOOL_APPROVAL_CONVERSATION_ACTION_ID,
                label=text("allow_conversation"),
                style=Button.Style.PRIMARY,
                action=Button.CallbackAction(data={"code": code, "approve": True}),
            ),
        )
    # One card with the full arguments folded in a scrollable detail.
    return MessageChain(
        chain=[
            ActionRow(
                buttons=buttons,
                action_timeout=timeout,
                single_use=True,
                title=title,
                detail=notice
                + json.dumps(tool_args, ensure_ascii=False, default=str, indent=2),
                tool_call_id=CURRENT_TOOL_CALL_ID.get(),
                fallback_text=prompt_text,
            )
        ]
    )


async def _wait_for_answer(
    session_id: str, code: str, timeout: int, send_prompt
) -> tuple[bool, bool]:
    """Send the prompt and wait for the approver's reply or click.

    The waiter is keyed by the approver rather than the waiting event (for
    a scheduled task it is the task's creator), so the ``session_waiter``
    decorator, which derives the key from the event, does not fit.

    Args:
        session_id: Waiter key, ``tool_approval:<umo>:<approver>``.
        code: Reply code that approves this request.
        timeout: Seconds to wait.
        send_prompt: Coroutine sending the prompt.

    Returns:
        ``(approved, allow_conversation)``.

    Raises:
        TimeoutError: If nobody answered in time.
        Exception: If the prompt could not be delivered.
    """
    session_filter = _ToolApprovalFilter()
    FILTERS.append(session_filter)
    waiter = SessionWaiter(session_filter, session_id, False)
    allow_conversation = False

    async def on_reply(controller, reply) -> None:
        nonlocal allow_conversation
        interaction = reply.get_button_interaction()
        if interaction is None:
            approved = reply.message_str.strip() == code
        else:
            # The code ties a click to this request, so a button left over
            # from an earlier request cannot approve this one.
            data = interaction.data if isinstance(interaction.data, dict) else {}
            approved = (
                interaction.action_id
                in (TOOL_APPROVAL_ACTION_ID, TOOL_APPROVAL_CONVERSATION_ACTION_ID)
                and data.get("code") == code
                and data.get("approve") is True
            )
            allow_conversation = (
                approved
                and interaction.action_id == TOOL_APPROVAL_CONVERSATION_ACTION_ID
            )
        controller.future.set_result(approved)

    def on_sent(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            waiter.session_controller.stop(task.exception())

    # register_wait runs up to its first suspension before this task starts,
    # so even an immediate reply finds the waiter registered.
    send_task = asyncio.create_task(send_prompt)
    send_task.add_done_callback(on_sent)
    try:
        approved = await waiter.register_wait(on_reply, timeout)
    finally:
        send_task.cancel()
    return approved, allow_conversation
