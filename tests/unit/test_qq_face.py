from astrbot.core.message.qq_face import format_qq_face


def test_format_qq_face_renders_known_system_faces() -> None:
    assert format_qq_face(0) == "[QQ Face: 惊讶 (id: 0)]"
    assert format_qq_face(111) == "[QQ Face: 可怜 (id: 111)]"
    assert format_qq_face("111") == "[QQ Face: 可怜 (id: 111)]"
    assert format_qq_face(348) == "[QQ Face: 福萝卜 (id: 348)]"


def test_format_qq_face_preserves_unknown_and_malformed_identifiers() -> None:
    assert format_qq_face(999) == "[QQ Face: unknown (id: 999)]"
    assert format_qq_face("not-an-id") == "[QQ Face: unknown (id: not-an-id)]"
    assert format_qq_face(None) == "[QQ Face: unknown]"
    assert format_qq_face(True) == "[QQ Face: unknown]"
