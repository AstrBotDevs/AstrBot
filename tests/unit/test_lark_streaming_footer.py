import json
from types import SimpleNamespace

import pytest

from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


class _FakeResponse:
    def __init__(self, card_id: str = "card-id") -> None:
        self.code = 0
        self.msg = "ok"
        self.data = SimpleNamespace(card_id=card_id)

    def success(self) -> bool:
        return True


class _FakeCardApi:
    def __init__(self) -> None:
        self.created_request = None

    async def acreate(self, request):
        self.created_request = request
        return _FakeResponse()


class _FakeCardKit:
    def __init__(self) -> None:
        self.v1 = SimpleNamespace(card=SimpleNamespace(acreate=_FakeCardApi().acreate))


def _extract_card_json(request) -> dict:
    body = request.request_body
    return json.loads(body.data)


def _fake_lark_event(card_api: _FakeCardApi):
    return SimpleNamespace(
        STREAMING_TEXT_ELEMENT_ID=LarkMessageEvent.STREAMING_TEXT_ELEMENT_ID,
        STREAMING_FOOTER_ELEMENT_ID=LarkMessageEvent.STREAMING_FOOTER_ELEMENT_ID,
        bot=SimpleNamespace(
            cardkit=SimpleNamespace(
                v1=SimpleNamespace(card=SimpleNamespace(acreate=card_api.acreate))
            )
        ),
    )


@pytest.mark.parametrize(
    (
        "status_enabled",
        "elapsed_enabled",
        "completed",
        "elapsed_seconds",
        "expected",
    ),
    [
        (True, False, False, None, "生成中..."),
        (True, False, True, None, "已完成"),
        (False, True, False, None, ""),
        (False, True, True, 3.24, "耗时 3.2s"),
        (True, True, True, 3.24, "已完成 · 耗时 3.2s"),
        (False, False, True, 3.24, ""),
    ],
)
def test_build_streaming_footer_text(
    status_enabled,
    elapsed_enabled,
    completed,
    elapsed_seconds,
    expected,
):
    assert (
        LarkMessageEvent._build_streaming_footer_text(
            status_enabled=status_enabled,
            elapsed_enabled=elapsed_enabled,
            completed=completed,
            elapsed_seconds=elapsed_seconds,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_create_streaming_card_includes_footer_element_when_enabled():
    card_api = _FakeCardApi()
    event = _fake_lark_event(card_api)

    card_id = await LarkMessageEvent._create_streaming_card(event, "生成中...")

    assert card_id == "card-id"
    card_json = _extract_card_json(card_api.created_request)
    elements = card_json["body"]["elements"]
    assert elements == [
        {
            "tag": "markdown",
            "content": "",
            "element_id": LarkMessageEvent.STREAMING_TEXT_ELEMENT_ID,
        },
        {
            "tag": "markdown",
            "content": "生成中...",
            "element_id": LarkMessageEvent.STREAMING_FOOTER_ELEMENT_ID,
        },
    ]


@pytest.mark.asyncio
async def test_create_streaming_card_omits_footer_element_when_disabled():
    card_api = _FakeCardApi()
    event = _fake_lark_event(card_api)

    card_id = await LarkMessageEvent._create_streaming_card(event, None)

    assert card_id == "card-id"
    card_json = _extract_card_json(card_api.created_request)
    elements = card_json["body"]["elements"]
    assert elements == [
        {
            "tag": "markdown",
            "content": "",
            "element_id": LarkMessageEvent.STREAMING_TEXT_ELEMENT_ID,
        }
    ]


@pytest.mark.asyncio
async def test_create_streaming_card_keeps_empty_footer_element_for_elapsed_only():
    card_api = _FakeCardApi()
    event = _fake_lark_event(card_api)

    card_id = await LarkMessageEvent._create_streaming_card(event, "")

    assert card_id == "card-id"
    card_json = _extract_card_json(card_api.created_request)
    elements = card_json["body"]["elements"]
    assert elements[-1] == {
        "tag": "markdown",
        "content": "",
        "element_id": LarkMessageEvent.STREAMING_FOOTER_ELEMENT_ID,
    }
