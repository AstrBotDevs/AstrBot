from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)


def _component_types(chain: MessageChain) -> list[type]:
    return [type(component) for component in chain.chain]


def _split(chain: MessageChain, *, separate_mentions: bool = True):
    return QQOfficialMessageEvent._split_message_chain_by_media(
        chain,
        separate_mentions=separate_mentions,
    )


def test_split_text_and_media_when_mention_is_present():
    chain = MessageChain(
        chain=[
            At(qq="member-1"),
            Plain(" hello"),
            Image.fromURL("https://example.com/cover.jpg"),
        ]
    )

    chunks = _split(chain)

    assert len(chunks) == 2
    assert _component_types(chunks[0]) == [At, Plain]
    assert _component_types(chunks[1]) == [Image]


def test_keep_text_and_media_together_without_mention():
    chain = MessageChain(
        chain=[Plain("hello"), Image.fromURL("https://example.com/cover.jpg")]
    )

    chunks = _split(chain)

    assert len(chunks) == 1
    assert _component_types(chunks[0]) == [Plain, Image]


def test_guild_transport_keeps_mention_and_media_together():
    chain = MessageChain(
        chain=[
            At(qq="member-1"),
            Plain(" hello"),
            Image.fromURL("https://example.com/cover.jpg"),
        ]
    )

    chunks = _split(chain, separate_mentions=False)

    assert len(chunks) == 1
    assert _component_types(chunks[0]) == [At, Plain, Image]


def test_at_all_is_not_treated_as_a_user_mention():
    chain = MessageChain(
        chain=[
            At(qq="all"),
            Plain(" hello"),
            Image.fromURL("https://example.com/cover.jpg"),
        ]
    )

    chunks = _split(chain)

    assert len(chunks) == 1
    assert _component_types(chunks[0]) == [At, Plain, Image]


def test_text_after_media_keeps_original_order():
    chain = MessageChain(
        chain=[
            At(qq="member-1"),
            Plain("before"),
            Image.fromURL("https://example.com/cover.jpg"),
            Plain("after"),
        ]
    )

    chunks = _split(chain)

    assert len(chunks) == 2
    assert _component_types(chunks[0]) == [At, Plain]
    assert _component_types(chunks[1]) == [Image, Plain]


def test_multiple_media_stay_in_separate_messages():
    chain = MessageChain(
        chain=[
            At(qq="member-1"),
            Plain(" hello"),
            Image.fromURL("https://example.com/one.jpg"),
            Image.fromURL("https://example.com/two.jpg"),
        ]
    )

    chunks = _split(chain)

    assert len(chunks) == 3
    assert _component_types(chunks[0]) == [At, Plain]
    assert _component_types(chunks[1]) == [Image]
    assert _component_types(chunks[2]) == [Image]
