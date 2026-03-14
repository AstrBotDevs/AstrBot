from __future__ import annotations

import pytest

from astrbot_sdk.protocol.descriptors import CommandTrigger, HandlerDescriptor
from astrbot_sdk.protocol.messages import InitializeMessage, PeerInfo
from astrbot_sdk.protocol.wire_codecs import (
    JsonProtocolCodec,
    MsgpackProtocolCodec,
    make_protocol_codec,
)


def _sample_initialize_message() -> InitializeMessage:
    return InitializeMessage(
        id="msg-1",
        protocol_version="1.0",
        peer=PeerInfo(name="plugin", role="plugin", version="v4"),
        handlers=[
            HandlerDescriptor(
                id="plugin:hello",
                trigger=CommandTrigger(command="hello"),
            )
        ],
        metadata={"plugin_id": "plugin", "loaded_plugins": ["plugin"]},
    )


class TestJsonProtocolCodec:
    def test_roundtrip(self):
        codec = JsonProtocolCodec()
        message = _sample_initialize_message()

        encoded = codec.encode_message(message)
        decoded = codec.decode_message(encoded)

        assert isinstance(encoded, bytes)
        assert decoded == message


class TestMsgpackProtocolCodec:
    def test_roundtrip(self):
        codec = MsgpackProtocolCodec()
        message = _sample_initialize_message()

        encoded = codec.encode_message(message)
        decoded = codec.decode_message(encoded)

        assert isinstance(encoded, bytes)
        assert decoded == message


def test_make_protocol_codec_rejects_unknown_name():
    with pytest.raises(ValueError, match="未知 wire codec"):
        make_protocol_codec("yaml")
