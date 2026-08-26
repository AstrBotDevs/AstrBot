"""Pure-function tests for inbound turn routing."""

from astrbot.core.command import (
    CommandCatalog,
    CommandCatalogRegistration,
    CommandGroupRegistration,
    CommandResolutionKind,
)
from astrbot.core.message.components import At, Plain
from astrbot.core.pipeline.turn_router import (
    LlmAccess,
    TurnRouteInput,
    longest_prefix_match,
    public_root_token,
    route_turn,
    strip_inbound_flush_flags,
)
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


def _help_catalog() -> CommandCatalog:
    async def help_handler(self, event) -> None: ...

    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "plugin.help",
        "help",
        "plugin.help",
        help_handler,
        [],
    )
    command_filter = CommandFilter("help")
    command_filter.init_handler_md(metadata)
    metadata.event_filters.append(command_filter)
    return CommandCatalog(
        [
            CommandCatalogRegistration(
                metadata.handler_full_name,
                metadata,
                command_filter.schema,
                (("help",),),
                command_filter,
            )
        ]
    )


def _llm_group_catalog() -> CommandCatalog:
    async def status(self, event) -> None: ...

    metadata = StarHandlerMetadata(
        EventType.AdapterMessageEvent,
        "builtin.llm_status",
        "status",
        "builtin",
        status,
        [],
        extras_configs={"sub_command": True},
    )
    command_filter = CommandFilter("status")
    command_filter.init_handler_md(metadata)
    metadata.event_filters.append(command_filter)
    return CommandCatalog(
        [
            CommandCatalogRegistration(
                metadata.handler_full_name,
                metadata,
                command_filter.schema,
                (("llm", "status"),),
                command_filter,
            )
        ],
        [CommandGroupRegistration((("llm",),), "builtin.llm")],
    )


def _input(
    text: str,
    *,
    private: bool = True,
    catalog: CommandCatalog | None = None,
    llm: LlmAccess | None = None,
    messages=None,
    **kwargs,
) -> TurnRouteInput:
    return TurnRouteInput(
        message_str=text,
        messages=tuple(messages or [Plain(text)]),
        is_private=private,
        command_prefixes=("/",),
        llm_access=llm or LlmAccess(),
        catalog=catalog or _help_catalog(),
        self_id="bot",
        **kwargs,
    )


def test_longest_prefix_does_not_eat_chatgpt():
    assert longest_prefix_match("/chatgpt", ("/chat", "/")) == "/"
    assert longest_prefix_match("/chat foo", ("/chat", "/")) == "/chat"
    assert public_root_token("/chat", ("/",)) == "chat"
    assert public_root_token("chat", ("/",)) == "chat"
    assert public_root_token("/", ("/",)) == ""


def test_private_open_group_prefix_chat():
    llm = LlmAccess(prefixes=("/chat",), private="open", group="prefix")
    catalog = _llm_group_catalog()

    dm = route_turn(_input("今天天气", llm=llm, catalog=catalog))
    assert dm.should_run_llm is True
    assert dm.should_run_command is False
    assert dm.message_str == "今天天气"

    group_chat = route_turn(
        _input("/chat 今天天气", private=False, llm=llm, catalog=catalog)
    )
    assert group_chat.should_run_llm is True
    assert group_chat.message_str == "今天天气"

    group_plain = route_turn(
        _input("今天天气", private=False, llm=llm, catalog=catalog)
    )
    assert group_plain.should_run_llm is False
    assert group_plain.stop is True


def test_llm_status_is_command_and_chat_is_not():
    catalog = _llm_group_catalog()
    status = route_turn(_input("/llm status", catalog=catalog))
    assert status.should_run_command is True
    assert status.resolution is not None
    assert status.resolution.kind is CommandResolutionKind.MATCHED

    chat = route_turn(_input("/chat status", catalog=catalog))
    assert chat.should_run_command is False
    assert chat.should_run_llm is True


def test_group_mention_still_matches_help():
    llm = LlmAccess(group="mention")
    result = route_turn(_input("/help", private=False, llm=llm))
    assert result.should_run_command is True
    assert result.should_run_llm is False


def test_group_off_does_not_open_llm_from_chat_prefix():
    llm = LlmAccess(prefixes=("/chat",), group="off")
    result = route_turn(_input("/chat 今天天气", private=False, llm=llm))
    assert result.should_run_llm is False
    assert result.stop is True

    continued = route_turn(
        _input(
            "/chat 今天天气",
            private=False,
            llm=llm,
            has_open_window=True,
        )
    )
    assert continued.should_run_llm is True


def test_unknown_subcommand_never_falls_through():
    catalog = _llm_group_catalog()
    result = route_turn(_input("/llm 今天天气", catalog=catalog))
    assert result.should_run_llm is False
    assert result.should_run_command is False
    assert result.stop is True
    assert result.resolution is not None
    assert result.resolution.kind is CommandResolutionKind.UNKNOWN_SUBCOMMAND


def test_notice_is_passthrough():
    result = route_turn(_input("poke", is_notice_or_request=True))
    assert result.route_kind == "passthrough"
    assert result.should_run_command is False
    assert result.should_run_llm is False
    assert result.stop is False


def test_forged_flush_flags_are_stripped():
    extras = {
        "turn_flush": True,
        "turn_continuation": True,
        "route_kind": "turn_flush",
        "_turn_flush_token": "forged",
        "keep": 1,
    }
    strip_inbound_flush_flags(extras)
    assert extras == {"keep": 1}


def test_manager_flush_is_trusted():
    result = route_turn(_input("hello", is_manager_flush=True))
    assert result.route_kind == "turn_flush"
    assert result.should_run_llm is True
    assert result.stop is False


def test_group_at_other_blocks_prefix_and_command():
    result = route_turn(
        _input(
            "/help",
            private=False,
            messages=[At(qq="other"), Plain("/help")],
        )
    )
    assert result.should_run_command is False
    assert result.should_run_llm is False
    assert result.stop is True
