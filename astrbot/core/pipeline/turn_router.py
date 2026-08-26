"""Pure inbound turn routing: command, LLM, or drop."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from astrbot.core.command import (
    CommandCatalog,
    CommandResolution,
    CommandResolutionKind,
)
from astrbot.core.message.components import At, AtAll, Reply

RouteKind = Literal["ordinary", "passthrough", "turn_flush"]
PrivateAccess = Literal["open", "prefix", "off"]
GroupAccess = Literal["open", "prefix", "mention", "prefix_or_mention", "off"]

INBOUND_FLUSH_KEYS = ("turn_flush", "turn_continuation")
MANAGER_FLUSH_TOKEN = "_turn_flush_token"
MANAGER_FLUSH_SENTINEL = object()


def is_manager_flush(extras: dict | None) -> bool:
    """Return whether extras were signed by TurnWindowManager.

    Args:
        extras: Event extras. Adapter-supplied values never compare equal
            to the process-local sentinel.
    """
    if not isinstance(extras, dict):
        return False
    return extras.get(MANAGER_FLUSH_TOKEN) is MANAGER_FLUSH_SENTINEL


@dataclass(frozen=True, slots=True)
class LlmAccess:
    """LLM access policy for one configuration profile."""

    prefixes: tuple[str, ...] = ("/",)
    private: PrivateAccess = "open"
    group: GroupAccess = "prefix"
    reply_to_bot: bool = False


@dataclass(frozen=True, slots=True)
class TurnRouteInput:
    """Inputs for one inbound routing decision."""

    message_str: str
    messages: tuple[object, ...]
    is_private: bool
    command_prefixes: tuple[str, ...]
    llm_access: LlmAccess
    catalog: CommandCatalog
    self_id: str = ""
    is_notice_or_request: bool = False
    has_open_window: bool = False
    is_manager_flush: bool = False
    adapter_preconfigured: bool = False
    ignore_at_all: bool = False


@dataclass(frozen=True, slots=True)
class TurnRouteResult:
    """Routing extras written onto an inbound event."""

    should_run_command: bool
    should_run_llm: bool
    route_kind: RouteKind
    wake_reasons: frozenset[str]
    message_str: str
    stop: bool
    resolution: CommandResolution | None = None


def longest_prefix_match(text: str, prefixes: Sequence[str]) -> str | None:
    """Return the longest prefix that matches on a token boundary.

    Args:
        text: Source text already stripped of surrounding spaces.
        prefixes: Candidate prefixes; empty strings are ignored.

    Returns:
        The matched prefix, or None when nothing matches.
    """
    matched: str | None = None
    for prefix in prefixes:
        if not prefix or not _matches_prefix(text, prefix):
            continue
        if matched is None or len(prefix) > len(matched):
            matched = prefix
    return matched


def public_root_token(text: str, command_prefixes: Sequence[str]) -> str:
    """Normalize a trigger or command path to its first occupancy token.

    Args:
        text: User-typed trigger or command path.
        command_prefixes: Command framing prefixes such as ``/``.

    Returns:
        The first word after stripping the longest command prefix. A bare
        command prefix such as ``/`` yields an empty token.
    """
    stripped = (text or "").strip()
    if not stripped:
        return ""
    prefix = longest_prefix_match(stripped, command_prefixes)
    rest = stripped[len(prefix) :].strip() if prefix else stripped
    if not rest:
        return ""
    return rest.split()[0]


def llm_access_from_config(config: dict) -> LlmAccess:
    """Build LLM access policy from a configuration profile.

    Args:
        config: Mapping that contains ``llm_access``. Missing keys use defaults.

    Returns:
        Frozen LLM access policy.
    """
    raw = config.get("llm_access") or {}
    prefixes = tuple(
        str(item) for item in raw.get("prefixes", ["/"]) if str(item).strip()
    )
    private = raw.get("private", "open")
    group = raw.get("group", "prefix")
    if private not in {"open", "prefix", "off"}:
        private = "open"
    if group not in {"open", "prefix", "mention", "prefix_or_mention", "off"}:
        group = "prefix"
    return LlmAccess(
        prefixes=prefixes or ("/",),
        private=private,
        group=group,
        reply_to_bot=bool(raw.get("reply_to_bot", False)),
    )


def command_prefixes_from_config(config: dict) -> tuple[str, ...]:
    """Return non-empty command prefixes for the active configuration profile.

    Args:
        config: Mapping that contains ``command_prefixes``.

    Returns:
        Command framing prefixes. Defaults to ``("/",)``.
    """
    raw = config.get("command_prefixes") or ["/"]
    prefixes = tuple(str(item) for item in raw if str(item).strip())
    return prefixes or ("/",)


def strip_inbound_flush_flags(extras: dict) -> None:
    """Remove client-supplied flush flags from inbound extras.

    Args:
        extras: Mutable extras dict attached to an adapter event.
    """
    for key in INBOUND_FLUSH_KEYS:
        extras.pop(key, None)
    extras.pop(MANAGER_FLUSH_TOKEN, None)
    if extras.get("route_kind") == "turn_flush":
        extras.pop("route_kind", None)


def route_turn(inp: TurnRouteInput) -> TurnRouteResult:
    """Classify one ordinary inbound message.

    Args:
        inp: Catalog snapshot, configuration, and message facts.

    Returns:
        Routing extras. Command matching strips ``command_prefixes`` first
        and never falls through from ``UNKNOWN_SUBCOMMAND`` to the LLM.
    """
    if inp.is_manager_flush:
        return TurnRouteResult(
            should_run_command=False,
            should_run_llm=True,
            route_kind="turn_flush",
            wake_reasons=frozenset({"turn_continuation"}),
            message_str=inp.message_str,
            stop=False,
        )
    if inp.is_notice_or_request:
        return TurnRouteResult(
            should_run_command=False,
            should_run_llm=False,
            route_kind="passthrough",
            wake_reasons=frozenset(),
            message_str=inp.message_str,
            stop=False,
        )

    blocked_by_other_at = _first_at_is_other(inp)
    command_text, command_prefix = _strip_command_prefix(inp.message_str, inp)
    if command_prefix is not None and not blocked_by_other_at:
        resolution = inp.catalog.resolve(command_text)
        if resolution.kind is CommandResolutionKind.MATCHED:
            return TurnRouteResult(
                True,
                False,
                "ordinary",
                frozenset({"command"}),
                command_text,
                False,
                resolution,
            )
        if resolution.kind is CommandResolutionKind.INCOMPLETE_GROUP:
            return TurnRouteResult(
                False,
                False,
                "ordinary",
                frozenset({"command"}),
                command_text,
                True,
                resolution,
            )
        if resolution.kind is CommandResolutionKind.UNKNOWN_SUBCOMMAND:
            return TurnRouteResult(
                False,
                False,
                "ordinary",
                frozenset({"command"}),
                command_text,
                True,
                resolution,
            )

    if inp.adapter_preconfigured:
        llm_text, reasons = _llm_payload(inp, blocked_by_other_at)
        return TurnRouteResult(
            False,
            True,
            "ordinary",
            frozenset({"adapter_preconfigured", *reasons}),
            llm_text,
            False,
        )

    llm_ok, reasons = _llm_gate(inp, blocked_by_other_at)
    if llm_ok:
        llm_text, extra_reasons = _llm_payload(inp, blocked_by_other_at)
        return TurnRouteResult(
            False,
            True,
            "ordinary",
            frozenset(reasons | extra_reasons),
            llm_text,
            False,
        )
    return TurnRouteResult(False, False, "ordinary", frozenset(), inp.message_str, True)


def _matches_prefix(text: str, prefix: str) -> bool:
    if not text.startswith(prefix):
        return False
    if len(text) == len(prefix):
        return True
    next_ch = text[len(prefix)]
    if next_ch in " \t":
        return True
    last = prefix[-1]
    return not (last.isalnum() and next_ch.isalnum())


def _strip_command_prefix(
    message_str: str, inp: TurnRouteInput
) -> tuple[str, str | None]:
    text = message_str.strip(" \t")
    prefix = longest_prefix_match(text, inp.command_prefixes)
    if prefix is None:
        return text, None
    return text[len(prefix) :].strip(" \t"), prefix


def _first_at_is_other(inp: TurnRouteInput) -> bool:
    if inp.is_private or not inp.messages:
        return False
    first = inp.messages[0]
    if not isinstance(first, At):
        return False
    qq = str(first.qq)
    return qq not in {str(inp.self_id), "all"}


def _llm_gate(inp: TurnRouteInput, blocked_by_other_at: bool) -> tuple[bool, set[str]]:
    if inp.has_open_window:
        return True, {"turn_continuation"}
    mentioned_bot, mentioned_all, reply_to_bot = _mention_flags(inp)
    if inp.is_private:
        mode = inp.llm_access.private
        if mode == "open":
            return True, {"llm_open"}
        if mode == "off":
            return False, set()
        if blocked_by_other_at:
            return False, set()
        if longest_prefix_match(inp.message_str.strip(" \t"), inp.llm_access.prefixes):
            return True, {"llm_prefix"}
        return False, set()

    reasons: set[str] = set()
    base = False
    mode = inp.llm_access.group
    prefix_hit = False
    if not blocked_by_other_at:
        prefix_hit = (
            longest_prefix_match(inp.message_str.strip(" \t"), inp.llm_access.prefixes)
            is not None
        )
    if mode == "open":
        base = True
        reasons.add("llm_open")
    elif mode == "prefix":
        base = prefix_hit
        if prefix_hit:
            reasons.add("llm_prefix")
    elif mode == "mention":
        base = mentioned_bot or mentioned_all
        if mentioned_bot:
            reasons.add("mention_bot")
        if mentioned_all:
            reasons.add("mention_all")
    elif mode == "prefix_or_mention":
        base = prefix_hit or mentioned_bot or mentioned_all
        if prefix_hit:
            reasons.add("llm_prefix")
        if mentioned_bot:
            reasons.add("mention_bot")
        if mentioned_all:
            reasons.add("mention_all")
    if inp.llm_access.reply_to_bot and reply_to_bot:
        base = True
        reasons.add("reply_to_bot")
    if mode != "off" and mentioned_all:
        base = True
        reasons.add("mention_all")
    return base, reasons


def _llm_payload(
    inp: TurnRouteInput, blocked_by_other_at: bool
) -> tuple[str, set[str]]:
    text = inp.message_str.strip(" \t")
    if blocked_by_other_at:
        return text, set()
    prefix = longest_prefix_match(text, inp.llm_access.prefixes)
    if prefix is None:
        return text, set()
    return text[len(prefix) :].strip(" \t"), {"llm_prefix"} if prefix else set()


def _mention_flags(inp: TurnRouteInput) -> tuple[bool, bool, bool]:
    mentioned_bot = False
    mentioned_all = False
    reply_to_bot = False
    for message in inp.messages:
        if isinstance(message, At) and str(message.qq) == str(inp.self_id):
            mentioned_bot = True
        if isinstance(message, AtAll) and not inp.ignore_at_all:
            mentioned_all = True
        if isinstance(message, Reply) and str(
            getattr(message, "sender_id", "") or ""
        ) == str(inp.self_id):
            reply_to_bot = True
    return mentioned_bot, mentioned_all, reply_to_bot
