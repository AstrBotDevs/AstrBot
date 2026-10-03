from unittest.mock import MagicMock

import pytest

from astrbot.core.star.filter.command import (
    CommandFilter,
    GreedyStr,
    unwrap_optional,
)


class TestGreedyStr:
    def test_greedy_str_is_str_subclass(self):
        gs = GreedyStr("hello world")
        assert isinstance(gs, str)
        assert str(gs) == "hello world"


class TestUnwrapOptional:
    def test_optional_with_none(self):
        annotation = int | None
        result = unwrap_optional(annotation)
        assert result == (int,)

    def test_union_with_none(self):
        annotation = int | None
        result = unwrap_optional(annotation)
        assert int in result

    def test_plain_type(self):
        annotation = int
        result = unwrap_optional(annotation)
        assert result == ()

    def test_union_multiple_non_none(self):
        annotation = int | str | float
        result = unwrap_optional(annotation)
        assert int in result
        assert str in result
        assert float in result


class TestCommandFilter:
    def test_init_basic(self):
        cf = CommandFilter(command_name="test")
        assert cf.command_name == "test"
        assert cf.alias == set()
        assert cf.parent_command_names == [""]

    def test_init_with_alias(self):
        cf = CommandFilter(command_name="test", alias={"t", "alias"})
        assert cf.alias == {"t", "alias"}

    def test_init_with_parent_commands(self):
        cf = CommandFilter(
            command_name="sub",
            parent_command_names=["parent"],
        )
        assert cf.parent_command_names == ["parent"]

    def test_get_complete_command_names_single(self):
        cf = CommandFilter(command_name="test")
        names = cf.get_complete_command_names()
        assert "test" in names

    def test_get_complete_command_names_with_alias(self):
        cf = CommandFilter(command_name="test", alias={"t"})
        names = cf.get_complete_command_names()
        assert "test" in names
        assert "t" in names

    def test_get_complete_command_names_with_parent(self):
        cf = CommandFilter(
            command_name="sub",
            parent_command_names=["parent"],
        )
        names = cf.get_complete_command_names()
        assert "parent sub" in names

    def test_get_complete_command_names_cached(self):
        cf = CommandFilter(command_name="test")
        names1 = cf.get_complete_command_names()
        names2 = cf.get_complete_command_names()
        assert names1 is names2

    def test_equals_exact_match(self):
        cf = CommandFilter(command_name="test")
        assert cf.equals("test") is True
        assert cf.equals("other") is False

    def test_equals_with_alias(self):
        cf = CommandFilter(command_name="test", alias={"t"})
        assert cf.equals("test") is True
        assert cf.equals("t") is True

    def test_add_custom_filter(self):
        cf = CommandFilter(command_name="test")
        mock_filter = MagicMock()
        mock_filter.filter.return_value = True
        cf.add_custom_filter(mock_filter)
        assert len(cf.custom_filter_list) == 1

    def test_custom_filter_ok_all_pass(self):
        cf = CommandFilter(command_name="test")
        mock_filter1 = MagicMock()
        mock_filter1.filter.return_value = True
        mock_filter2 = MagicMock()
        mock_filter2.filter.return_value = True
        cf.custom_filter_list = [mock_filter1, mock_filter2]

        result = cf.custom_filter_ok(MagicMock(), MagicMock())
        assert result is True

    def test_custom_filter_ok_one_fails(self):
        cf = CommandFilter(command_name="test")
        mock_filter1 = MagicMock()
        mock_filter1.filter.return_value = True
        mock_filter2 = MagicMock()
        mock_filter2.filter.return_value = False
        cf.custom_filter_list = [mock_filter1, mock_filter2]

        result = cf.custom_filter_ok(MagicMock(), MagicMock())
        assert result is False

    def test_validate_and_convert_params_empty(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {}
        result = cf.validate_and_convert_params([], {})
        assert result == {}

    def test_validate_and_convert_params_string(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"name": str}
        result = cf.validate_and_convert_params(["value"], {"name": str})
        assert result["name"] == "value"

    def test_validate_and_convert_params_int(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"count": int}
        result = cf.validate_and_convert_params(["42"], {"count": int})
        assert result["count"] == 42

    def test_validate_and_convert_params_float(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"rate": float}
        result = cf.validate_and_convert_params(["3.14"], {"rate": float})
        assert result["rate"] == 3.14

    def test_validate_and_convert_params_bool_true(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}
        for val in ["true", "yes", "1", "TRUE", "YES"]:
            result = cf.validate_and_convert_params([val], cf.handler_params)
            assert result["enabled"] is True

    def test_validate_and_convert_params_bool_false(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}
        for val in ["false", "no", "0", "FALSE", "NO"]:
            result = cf.validate_and_convert_params([val], cf.handler_params)
            assert result["enabled"] is False

    def test_validate_and_convert_params_bool_invalid(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"enabled": bool}
        with pytest.raises(ValueError, match="必须是布尔值"):
            cf.validate_and_convert_params(["invalid"], cf.handler_params)

    def test_validate_and_convert_params_missing_required(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"required": int}
        with pytest.raises(ValueError, match="必要参数缺失"):
            cf.validate_and_convert_params([], {"required": int})

    def test_validate_and_convert_params_greedy_str(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"rest": GreedyStr}
        result = cf.validate_and_convert_params(
            ["arg1", "arg2", "arg3"],
            {"rest": GreedyStr},
        )
        assert result["rest"] == "arg1 arg2 arg3"

    def test_validate_and_convert_params_greedy_str_not_last(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"rest": GreedyStr, "extra": str}
        with pytest.raises(ValueError, match=r"GreedyStr.*必须是最后一个参数"):
            cf.validate_and_convert_params(
                ["arg1", "arg2"],
                {"rest": GreedyStr, "extra": str},
            )

    def test_validate_and_convert_params_with_default(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"optional": "default_val"}
        result = cf.validate_and_convert_params([], {"optional": "default_val"})
        assert result["optional"] == "default_val"

    def test_validate_and_convert_params_type_error(self):
        cf = CommandFilter(command_name="test")
        cf.handler_params = {"count": int}
        with pytest.raises(ValueError, match="类型错误"):
            cf.validate_and_convert_params(["not_a_number"], {"count": int})

    def test_print_types_basic(self):
        def handler(self, event, name: str):
            pass

        cf = CommandFilter(command_name="test")
        cf.init_handler_md(MagicMock(handler=handler))
        result = cf.print_types()
        assert "name" in result

    def test_filter_event_not_wake_command(self):
        cf = CommandFilter(command_name="test")
        event = MagicMock()
        event.is_at_or_wake_command = False
        assert cf.filter(event, MagicMock()) is False

    def test_filter_custom_filter_fails(self):
        cf = CommandFilter(command_name="test")
        event = MagicMock()
        event.is_at_or_wake_command = True
        mock_filter = MagicMock()
        mock_filter.filter.return_value = False
        cf.custom_filter_list = [mock_filter]
        assert cf.filter(event, MagicMock()) is False

    def test_filter_no_command_match(self):
        cf = CommandFilter(command_name="test")
        event = MagicMock()
        event.is_at_or_wake_command = True
        event.get_message_str.return_value = "other message"
        assert cf.filter(event, MagicMock()) is False

    def test_filter_command_matched(self):
        def handler(self, event, name: str, value: str):
            pass

        cf = CommandFilter(command_name="test")
        cf.init_handler_md(MagicMock(handler=handler))
        cf.handler_params = {"name": str, "value": str}
        event = MagicMock()
        event.is_at_or_wake_command = True
        event.get_message_str.return_value = "test arg1 arg2"
        event.set_extra = MagicMock()
        assert cf.filter(event, MagicMock()) is True
        event.set_extra.assert_called_once()
