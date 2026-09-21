from astrbot.core.utils.errors import format_exception


def test_format_exception_keeps_detail():
    assert format_exception(ValueError("bad request")) == "ValueError: bad request"


def test_format_exception_keeps_type_for_parameterless_errors():
    assert format_exception(MemoryError()) == "MemoryError"
