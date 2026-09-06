from unittest.mock import patch

from astrbot.core.utils.config_number import coerce_int_config


class TestCoerceIntConfig:
    def test_int_value_returns_unchanged(self):
        assert coerce_int_config(42, default=0) == 42
        assert coerce_int_config(-5, default=0) == -5
        assert coerce_int_config(0, default=10) == 0

    def test_string_int_value_parsed(self):
        assert coerce_int_config("42", default=0) == 42
        assert coerce_int_config("  123  ", default=0) == 123
        assert coerce_int_config("-7", default=0) == -7

    def test_string_non_numeric_uses_default(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config("abc", default=99)
            assert result == 99
            mock_logger.warning.assert_called_once()
            assert "not numeric" in mock_logger.warning.call_args[0][0]

    def test_string_non_numeric_no_warn(self):
        result = coerce_int_config("abc", default=99, warn=False)
        assert result == 99

    def test_bool_value_uses_default(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            assert coerce_int_config(True, default=99) == 99
            assert coerce_int_config(False, default=99) == 99
            assert mock_logger.warning.call_count == 2
            assert "should be numeric" in mock_logger.warning.call_args[0][0]

    def test_bool_value_no_warn(self):
        result = coerce_int_config(True, default=99, warn=False)
        assert result == 99

    def test_none_value_uses_default(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config(None, default=77)
            assert result == 77
            mock_logger.warning.assert_called()
            assert "unsupported type" in mock_logger.warning.call_args[0][0]

    def test_none_value_no_warn(self):
        result = coerce_int_config(None, default=77, warn=False)
        assert result == 77

    def test_float_value_parsed(self):
        assert coerce_int_config(3.14, default=0) == 3
        assert coerce_int_config(-2.5, default=0) == -2

    def test_object_value_uses_default(self):
        class CustomType:
            pass

        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config(CustomType(), default=55)
            assert result == 55
            mock_logger.warning.assert_called()
            assert "unsupported type" in mock_logger.warning.call_args[0][0]

    def test_min_value_enforced(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config(5, default=0, min_value=10)
            assert result == 10
            mock_logger.warning.assert_called()
            assert "below minimum" in mock_logger.warning.call_args[0][0]

    def test_min_value_enforced_no_warn(self):
        result = coerce_int_config(5, default=0, min_value=10, warn=False)
        assert result == 10

    def test_min_value_not_enforced_when_above(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config(15, default=0, min_value=10)
            assert result == 15
            mock_logger.warning.assert_not_called()

    def test_min_value_not_enforced_at_exact_boundary(self):
        with patch("astrbot.core.utils.config_number.logger") as mock_logger:
            result = coerce_int_config(10, default=0, min_value=10)
            assert result == 10
            mock_logger.warning.assert_not_called()

    def test_complex_string_with_whitespace(self):
        assert coerce_int_config("  -42  ", default=0) == -42
        assert coerce_int_config("\t100\n", default=0) == 100
