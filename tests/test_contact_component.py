"""Tests for the OneBot V11 contact segment serialization.

``Contact`` stores the inbound subtype (qq / group) in a private field, so the
generic ``toDict()`` dropped ``data.type`` when an already parsed contact was
serialized back to a router.
"""

import logging

import astrbot.core.message.components as Comp
import pytest
from astrbot.core.message.components import Contact, Image, Music, Plain
from astrbot.core.pipeline.respond.stage import RespondStage


def test_inbound_contact_round_trips_subtype():
    contact = Comp.ComponentTypes["contact"](**{"type": "group", "id": 123})

    assert isinstance(contact, Contact)
    assert contact.toDict() == {
        "type": "contact",
        "data": {"type": "group", "id": "123"},
    }


@pytest.mark.asyncio
async def test_inbound_contact_async_to_dict_matches_sync():
    contact = Comp.ComponentTypes["contact"](**{"type": "qq", "id": "42"})

    assert await contact.to_dict() == contact.toDict()


def test_outbound_contact_serializes_type_and_id():
    assert Contact(type="qq", id=42).toDict() == {
        "type": "contact",
        "data": {"type": "qq", "id": "42"},
    }


def test_contact_type_is_normalized():
    assert Contact(type="  GROUP ", id=1).toDict()["data"]["type"] == "group"


def test_unknown_contact_type_is_kept_and_warned(caplog):
    caplog.set_level(logging.WARNING)

    contact = Contact(type="weird", id=7)

    assert contact.toDict()["data"]["type"] == "weird"
    assert "Unsupported OneBot contact type" in caplog.text


def test_contact_without_type_omits_it():
    data = Contact(id=5).toDict()["data"]

    assert "type" not in data
    assert data["id"] == "5"


def test_contact_without_id_omits_it():
    data = Contact(type="group", id=None).toDict()["data"]

    assert data == {"type": "group"}


def test_respond_stage_contact_validator_uses_subtype():
    validator = RespondStage._component_validators[Comp.Contact]

    assert validator(Contact(type="qq", id=1))
    assert not validator(Contact(id=1))


def test_plain_image_and_music_to_dict_are_unaffected():
    assert Plain("hello").toDict() == {"type": "text", "data": {"text": "hello"}}
    assert Image(file="picture.png").toDict() == {
        "type": "image",
        "data": {"file": "picture.png", "url": "", "path": ""},
    }
    assert Music(_type="163", id=1).toDict() == {
        "type": "music",
        "data": {"type": "163", "id": "1"},
    }
