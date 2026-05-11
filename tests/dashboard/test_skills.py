"""Import smoke tests for the skills route module.

Verifies that the ``SkillsRoute`` class and key standalone utilities from
``skills.py`` can be imported without errors.
"""

import re

# ---------------------------------------------------------------------------
# skills.py — SkillsRoute, helpers and constants
# ---------------------------------------------------------------------------
from astrbot.dashboard.routes.skills import (  # noqa: F401
    SkillsRoute,
    _SKILL_NAME_RE,
    _next_available_temp_path,
    _to_bool,
    _to_jsonable,
)


def test_skills_route_class():
    assert SkillsRoute is not None


def test_skill_name_re_is_compiled_regex():
    assert isinstance(_SKILL_NAME_RE, re.Pattern)


def test_to_jsonable_is_callable():
    assert callable(_to_jsonable)


def test_to_bool_is_callable():
    assert callable(_to_bool)


def test_next_available_temp_path_is_callable():
    assert callable(_next_available_temp_path)


def test_to_bool_string_true_values():
    assert _to_bool("true") is True
    assert _to_bool("1") is True
    assert _to_bool("yes") is True
    assert _to_bool("on") is True


def test_to_bool_string_false_values():
    assert _to_bool("false") is False
    assert _to_bool("0") is False
    assert _to_bool("no") is False
    assert _to_bool("off") is False


def test_to_bool_none_default():
    assert _to_bool(None) is False
    assert _to_bool(None, True) is True


def test_to_jsonable_preserves_plain_types():
    assert _to_jsonable({"a": 1}) == {"a": 1}
    assert _to_jsonable([1, 2, 3]) == [1, 2, 3]
    assert _to_jsonable("hello") == "hello"
