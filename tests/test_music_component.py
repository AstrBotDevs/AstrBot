"""Tests for the OneBot V11 music (and contact) message segments.

``Music`` keeps its OneBot ``data.type`` (qq / 163 / xm / custom) in a private
field, because ``type`` is already the component name. The base ``toDict()`` only
walks model fields, so the segment used to be emitted without the required
``data.type`` key (and inbound ``{"type": "163", ...}`` payloads were rejected).
"""

import logging

import astrbot.core.message.components as Comp
import pytest
from astrbot.core.message.components import Contact, Image, Music, Plain
from astrbot.core.pipeline.respond.stage import RespondStage

CUSTOM = {
    "url": "https://music.example/song.mp3",
    "audio": "https://music.example/song.mp3",
    "title": "Song title",
    "content": "Artist",
    "image": "https://music.example/cover.jpg",
}


def test_music_to_dict_contains_onebot_type():
    music = Music(_type="163", id=123)

    assert music.toDict() == {
        "type": "music",
        "data": {"type": "163", "id": "123"},
    }


@pytest.mark.asyncio
async def test_music_async_to_dict_matches_sync_to_dict():
    music = Music(_type="163", id=123)

    assert await music.to_dict() == music.toDict()


def test_custom_music_segment_is_valid():
    music = Music(_type="custom", **CUSTOM)

    assert music.toDict() == {
        "type": "music",
        "data": {"type": "custom", **CUSTOM},
    }


def test_custom_music_omits_empty_optional_fields():
    music = Music(
        _type="custom",
        url=CUSTOM["url"],
        audio=CUSTOM["audio"],
        title=CUSTOM["title"],
    )

    assert music.toDict()["data"] == {
        "type": "custom",
        "url": CUSTOM["url"],
        "audio": CUSTOM["audio"],
        "title": CUSTOM["title"],
    }


def test_non_custom_music_only_carries_id():
    """qq/163/xm segments reference a song by id; custom fields are ignored."""
    music = Music(_type="163", id=123, url=CUSTOM["url"], title="ignored")

    assert music.toDict() == {
        "type": "music",
        "data": {"type": "163", "id": "123"},
    }


def test_music_accepts_private_and_legacy_type_keywords():
    """``_type`` wins over the inbound ``type`` key, empty values fall back."""
    explicit = Music(_type="163", type="qq", id=1)
    empty_private = Music(_type="", type="163", id=2)

    assert explicit._type == "163"
    assert explicit.toDict()["data"]["type"] == "163"
    assert empty_private._type == "163"


def test_non_str_music_type_is_normalized():
    assert Music(_type=163, id=1).toDict()["data"]["type"] == "163"


def test_invalid_music_type_falls_back(caplog):
    caplog.set_level(logging.WARNING)

    by_id = Music(type=Comp.ComponentType.Music, id=1)
    custom_share = Music(_type="bogus", url=CUSTOM["url"], audio=CUSTOM["audio"])

    assert by_id.toDict()["data"]["type"] == "163"
    assert custom_share.toDict()["data"]["type"] == "custom"
    assert "Unsupported OneBot music type" in caplog.text


def test_music_without_type_derives_one():
    by_id = Music(id=7)
    custom_share = Music(url=CUSTOM["url"], audio=CUSTOM["audio"], title="T")

    assert by_id.toDict()["data"]["type"] == "163"
    assert custom_share.toDict()["data"]["type"] == "custom"


def test_inbound_onebot_music_segment_parses():
    """Inbound segments carry the music type as ``data.type``."""

    music = Comp.ComponentTypes["music"](**{"type": "163", "id": "42"})

    assert isinstance(music, Music)
    assert music._type == "163"
    assert music.toDict() == {
        "type": "music",
        "data": {"type": "163", "id": "42"},
    }


def test_respond_stage_music_validator_uses_type():
    validator = RespondStage._component_validators[Comp.Music]

    # The validators return the last evaluated operand, so only truthiness is
    # asserted here.
    assert validator(Music(_type="163", id=1))
    assert validator(Music(_type="custom", **CUSTOM))
    assert not validator(Music(_type="custom", url=CUSTOM["url"]))


def test_contact_accepts_onebot_type():
    """Contact shares the private-field problem and used to raise AttributeError."""

    contact = Contact(type="qq", id=1)
    validator = RespondStage._component_validators[Comp.Contact]

    assert contact._type == "qq"
    assert Contact(id=2)._type == ""
    assert validator(contact)
    assert not validator(Contact(id=2))


def test_plain_and_image_to_dict_are_unaffected():
    assert Plain("hello").toDict() == {"type": "text", "data": {"text": "hello"}}
    assert Image(file="picture.png").toDict() == {
        "type": "image",
        "data": {"file": "picture.png", "url": "", "path": ""},
    }
