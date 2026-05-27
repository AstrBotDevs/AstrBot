from types import SimpleNamespace

import pytest

from astrbot.api.message_components import File, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


def test_qqofficial_split_message_chain_keeps_one_media_per_chunk():
    chain = MessageChain(
        chain=[
            Plain("files:"),
            File(name="test1.txt", file="/tmp/test1.txt"),
            Plain("next"),
            File(name="test2.txt", file="/tmp/test2.txt"),
        ],
        use_t2i_=False,
        type="test",
    )

    chunks = QQOfficialMessageEvent._split_message_chain_by_media(chain)

    assert len(chunks) == 2
    assert [type(component) for component in chunks[0].chain] == [
        Plain,
        File,
        Plain,
    ]
    assert [type(component) for component in chunks[1].chain] == [File]
    assert all(chunk.use_t2i_ is False for chunk in chunks)
    assert all(chunk.type == "test" for chunk in chunks)


@pytest.mark.asyncio
async def test_qqofficial_send_by_session_splits_multiple_files(
    monkeypatch,
    event_queue,
    platform_settings,
):
    monkeypatch.setenv("ASTRBOT_DISABLE_METRICS", "1")

    adapter = QQOfficialPlatformAdapter(
        {
            "id": "qq-official",
            "appid": "appid",
            "secret": "secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        platform_settings,
        event_queue,
    )
    adapter.remember_session_message_id("user-1", "incoming-message-id")

    uploaded_files = []
    sent_payloads = []

    async def fake_upload_group_and_c2c_media(
        _self,
        file_source,
        file_type,
        srv_send_msg=False,
        file_name=None,
        **kwargs,
    ):
        uploaded_files.append(
            {
                "file_source": file_source,
                "file_type": file_type,
                "srv_send_msg": srv_send_msg,
                "file_name": file_name,
                "kwargs": kwargs,
            }
        )
        return SimpleNamespace(file_uuid=file_source, file_info=file_name, ttl=0)

    async def fake_post_c2c_message(_self, openid, **payload):
        sent_payloads.append({"openid": openid, "payload": payload})
        return {"id": f"sent-{len(sent_payloads)}"}

    monkeypatch.setattr(
        QQOfficialMessageEvent,
        "upload_group_and_c2c_media",
        fake_upload_group_and_c2c_media,
    )
    monkeypatch.setattr(
        QQOfficialMessageEvent,
        "post_c2c_message",
        fake_post_c2c_message,
    )

    await adapter._send_by_session_common(
        MessageSession(
            platform_name="qq-official",
            message_type=MessageType.FRIEND_MESSAGE,
            session_id="user-1",
        ),
        MessageChain(
            chain=[
                File(name="test1.txt", file="/tmp/test1.txt"),
                File(name="test2.txt", file="/tmp/test2.txt"),
            ]
        ),
    )

    assert [item["file_source"] for item in uploaded_files] == [
        "/tmp/test1.txt",
        "/tmp/test2.txt",
    ]
    assert [item["file_name"] for item in uploaded_files] == [
        "test1.txt",
        "test2.txt",
    ]
    assert [item["kwargs"] for item in uploaded_files] == [
        {"openid": "user-1"},
        {"openid": "user-1"},
    ]
    assert [item["openid"] for item in sent_payloads] == ["user-1", "user-1"]
    assert [
        item["payload"]["media"].file_uuid for item in sent_payloads
    ] == [
        "/tmp/test1.txt",
        "/tmp/test2.txt",
    ]
