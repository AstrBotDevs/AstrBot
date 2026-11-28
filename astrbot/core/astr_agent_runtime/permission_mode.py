"""Live ChatUI permission mode per conversation.

A ChatUI message carries the conversation's permission mode, but sub-agents
and later tool calls of a turn keep running with that message's event after
the user changes the mode (in the input bar or with "Allow for this
conversation"). The mode is therefore also kept here per WebChat
conversation, so every tool call reads the current choice. Unattended runs
(scheduled tasks, background wakeups) never take "full" or
"workspace_no_ask" from here: they may only be narrowed to "workspace".
"""

from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent

PERMISSION_MODES = ("workspace", "workspace_no_ask", "ask", "full")
# Modes that confine Local access to the conversation workspace.
WORKSPACE_MODES = ("workspace", "workspace_no_ask")
# Modes that skip approval prompts in attended ChatUI runs. "workspace_no_ask"
# is what "Don't ask again in this conversation" turns workspace into: no
# prompts, same confined access.
NO_ASK_MODES = ("full", "workspace_no_ask")

# WebChat session ID (``webchat!<user>!<conversation>``) -> current mode.
_conversation_modes: dict[str, str] = {}


def conversation_key(username: str, session_id: str) -> str:
    """Return the WebChat session ID of a user's conversation or thread.

    Args:
        username: Dashboard user who owns the conversation.
        session_id: ChatUI conversation or thread ID.

    Returns:
        The event session ID, ``webchat!<user>!<conversation>``.
    """
    return f"webchat!{username}!{session_id}"


def set_conversation_permission_mode(session_id: str, mode: str | None) -> None:
    """Record the mode the user chose for a ChatUI conversation.

    Args:
        session_id: WebChat session ID, ``webchat!<user>!<conversation>``.
        mode: One of PERMISSION_MODES; anything else forgets the choice.
    """
    if mode in PERMISSION_MODES:
        _conversation_modes[session_id] = mode
    else:
        _conversation_modes.pop(session_id, None)


def get_permission_mode(event) -> str | None:
    """Return the permission mode that applies to a tool call now.

    Args:
        event: The event the tool call runs with.

    Returns:
        One of PERMISSION_MODES, or None (ask as configured). Unattended
        runs only ever get "workspace" or None.
    """
    # The local permission policy calls this for every tool context, and
    # plugin-made or minimal events may lack these attributes.
    get_extra = getattr(event, "get_extra", None)
    mode = get_extra("permission_mode") if callable(get_extra) else None
    get_platform_name = getattr(event, "get_platform_name", None)
    live = None
    if callable(get_platform_name) and get_platform_name() == "webchat":
        live = _conversation_modes.get(getattr(event, "session_id", None) or "")
    if isinstance(event, AgentWakeupEvent):
        narrowed = mode in WORKSPACE_MODES or live in WORKSPACE_MODES
        return "workspace" if narrowed else None
    return live or mode
