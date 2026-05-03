"""Tests for upload filename sanitization."""

from astrbot.dashboard.routes.chat import _sanitize_upload_filename


def test_sanitize_upload_filename_strips_posix_traversal():
    assert _sanitize_upload_filename("../../outside.txt") == "outside.txt"


def test_sanitize_upload_filename_strips_windows_traversal():
    assert _sanitize_upload_filename(r"..\\..\\outside.txt") == "outside.txt"


def test_sanitize_upload_filename_strips_fakepath():
    assert _sanitize_upload_filename(r"C:\\fakepath\\photo.png") == "photo.png"


def test_sanitize_upload_filename_falls_back_for_empty_values():
    generated = _sanitize_upload_filename("")

    assert generated
    assert generated not in {".", ".."}
    assert "/" not in generated
    assert "\\" not in generated


def test_sanitize_upload_filename_removes_embedded_null_bytes():
    assert _sanitize_upload_filename("evil\x00.txt") == "evil.txt"
    assert _sanitize_upload_filename("\x00leading.txt") == "leading.txt"
    assert _sanitize_upload_filename("trailing\x00.txt\x00") == "trailing.txt"
    assert _sanitize_upload_filename("mid\x00dle.txt") == "middle.txt"

