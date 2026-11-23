"""Public KOOK enum display and JSON contracts remain stable."""

import json
from enum import Enum

import pytest
from pydantic import TypeAdapter

from astrbot.core.platform.sources.kook.kook_types import (
    KookChannelType,
    KookMentionTagName,
    KookModuleType,
    KookRoleExtraType,
)


@pytest.mark.parametrize(
    "enum_type",
    [KookChannelType, KookMentionTagName, KookModuleType, KookRoleExtraType],
)
def test_kook_enum_keeps_display_and_wire_values(enum_type: type[Enum]) -> None:
    codec = TypeAdapter(enum_type)
    for member in enum_type:
        display = f"{enum_type.__name__}.{member.name}"
        assert str(member) == display
        assert format(member, ">40") == format(display, ">40")
        assert member == member.value
        wire_value = json.dumps(member.value).encode()
        assert codec.validate_json(wire_value) is member
        assert json.loads(codec.dump_json(member)) == member.value
        assert json.dumps(member) == json.dumps(member.value)
