"""Tests for upload filename sanitization."""

from astrbot.dashboard.services.chat_service import sanitize_upload_filename


def test_sanitize_upload_filename_strips_posix_traversal():
    assert sanitize_upload_filename("../../outside.txt") == "outside.txt"


def test_sanitize_upload_filename_strips_windows_traversal():
    assert sanitize_upload_filename(r"..\\..\\outside.txt") == "outside.txt"


def test_sanitize_upload_filename_strips_fakepath():
    assert sanitize_upload_filename(r"C:\\fakepath\\photo.png") == "photo.png"


def test_sanitize_upload_filename_falls_back_for_empty_values():
    generated = sanitize_upload_filename("")

    assert generated
    assert generated not in {".", ".."}
    assert "/" not in generated
    assert "\\" not in generated


def test_sanitize_upload_filename_removes_embedded_null_bytes():
    assert sanitize_upload_filename("evil\x00.txt") == "evil.txt"
    assert sanitize_upload_filename("\x00leading.txt") == "leading.txt"
    assert sanitize_upload_filename("trailing\x00.txt\x00") == "trailing.txt"
    assert sanitize_upload_filename("mid\x00dle.txt") == "middle.txt"
