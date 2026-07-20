"""Tests for ``astrbot.core.provider.modalities.sanitize_contexts_by_modalities``.

These tests focus on the image MIME handling added for issue #9295, where an
animated GIF referenced via a quote could poison the session history and make
subsequent requests to GIF-rejecting Gemini-compatible gateways fail forever.
"""

from __future__ import annotations

from astrbot.core.provider.modalities import (
    ContextSanitizeStats,
    sanitize_contexts_by_modalities,
)


def _image_url_part(url: str) -> dict:
    return {"type": "image_url", "image_url": {"url": url}}


def _user(*parts: dict) -> dict:
    return {"role": "user", "content": list(parts)}


GIF_DATA_URL = "data:image/gif;base64,R0lGODlh8ADwAPcAAPxzxg=="
PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
JPEG_DATA_URL = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD"
WEBP_DATA_URL = "data:image/webp;base64,UklGRkBAAABXRUJQ"


# ---------------------------------------------------------------------------
# Issue #9295: GIF must be stripped even when the model claims image support
# ---------------------------------------------------------------------------


def test_gif_data_url_replaced_when_image_supported_but_gif_unsupported() -> None:
    """Reproduces the exact reporter scenario.

    Provider declares ``[text, image, audio, tool_use]`` (which used to hit the
    fast-path and skip sanitizing), and the context carries a ``data:image/gif``
    block. The GIF must be replaced with ``[Image]``.
    """
    contexts = [_user(_image_url_part(GIF_DATA_URL))]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image", "audio", "tool_use"],
    )

    content = sanitized[0]["content"]
    assert content == [{"type": "text", "text": "[Image]"}]
    assert stats.fixed_image_blocks == 1
    assert stats.changed


def test_gif_data_url_replaced_when_only_text_and_image_supported() -> None:
    """Stripping also applies to the regular image-supported path."""
    contexts = [_user(_image_url_part(GIF_DATA_URL))]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image"],
    )

    assert sanitized[0]["content"] == [{"type": "text", "text": "[Image]"}]
    assert stats.fixed_image_blocks == 1


def test_gif_http_url_replaced_by_extension_fallback() -> None:
    """http(s) URLs ending in ``.gif`` are also detected via extension."""
    contexts = [_user(_image_url_part("https://example.com/animation.gif"))]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image", "tool_use"],
    )

    assert sanitized[0]["content"] == [{"type": "text", "text": "[Image]"}]
    assert stats.fixed_image_blocks == 1


def test_gif_http_url_with_query_string_still_detected() -> None:
    """Query/fragment suffixes on the URL must not defeat detection."""
    contexts = [
        _user(_image_url_part("https://cdn.example.com/a.GIF?token=abc#frag")),
    ]
    sanitized, stats = sanitize_contexts_by_modalities(contexts, ["text", "image"])

    assert sanitized[0]["content"] == [{"type": "text", "text": "[Image]"}]
    assert stats.fixed_image_blocks == 1


# ---------------------------------------------------------------------------
# Non-GIF images must be preserved when image is supported
# ---------------------------------------------------------------------------


def test_png_preserved_when_image_supported() -> None:
    contexts = [_user(_image_url_part(PNG_DATA_URL))]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image", "audio", "tool_use"],
    )

    assert sanitized[0]["content"] == [_image_url_part(PNG_DATA_URL)]
    assert stats.fixed_image_blocks == 0
    assert not stats.changed


def test_jpeg_and_webp_preserved_when_image_supported() -> None:
    contexts = [
        _user(_image_url_part(JPEG_DATA_URL), _image_url_part(WEBP_DATA_URL)),
    ]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image"],
    )

    assert sanitized[0]["content"] == [
        _image_url_part(JPEG_DATA_URL),
        _image_url_part(WEBP_DATA_URL),
    ]
    assert not stats.changed


def test_unknown_mime_image_preserved_when_image_supported() -> None:
    """When no MIME can be determined we must not strip the image.

    Stripping on "unknown" would over-aggressively drop legitimate images and
    break providers that accept arbitrary image formats.
    """
    contexts = [_user({"type": "image_url", "image_url": {"url": "abc-not-a-url"}})]
    sanitized, stats = sanitize_contexts_by_modalities(contexts, ["text", "image"])

    assert sanitized[0]["content"] == contexts[0]["content"]
    assert not stats.changed


# ---------------------------------------------------------------------------
# Existing behavior: full removal when image modality is not declared
# ---------------------------------------------------------------------------


def test_all_images_removed_when_image_not_supported() -> None:
    """Pre-existing behavior must remain: no image modality → strip everything."""
    contexts = [
        _user(
            _image_url_part(GIF_DATA_URL),
            _image_url_part(PNG_DATA_URL),
        )
    ]
    sanitized, stats = sanitize_contexts_by_modalities(contexts, ["text"])

    assert sanitized[0]["content"] == [
        {"type": "text", "text": "[Image]"},
        {"type": "text", "text": "[Image]"},
    ]
    assert stats.fixed_image_blocks == 2


def test_audio_branch_unchanged_by_gif_handling() -> None:
    """The audio-stripping branch must keep working independently."""
    contexts = [
        _user(
            {"type": "input_audio", "input_audio": {"data": "abc", "format": "mp3"}},
        )
    ]
    sanitized, stats = sanitize_contexts_by_modalities(contexts, ["text", "image"])

    assert sanitized[0]["content"] == [{"type": "text", "text": "[Audio]"}]
    assert stats.fixed_audio_blocks == 1
    assert stats.fixed_image_blocks == 0


def test_mixed_text_and_gif_only_gif_is_replaced() -> None:
    """A GIF between text parts must only drop the GIF, preserving the text."""
    contexts = [
        _user(
            {"type": "text", "text": "look at this"},
            _image_url_part(GIF_DATA_URL),
            {"type": "text", "text": "isn't it cool"},
        )
    ]
    sanitized, stats = sanitize_contexts_by_modalities(
        contexts,
        ["text", "image", "audio", "tool_use"],
    )

    assert sanitized[0]["content"] == [
        {"type": "text", "text": "look at this"},
        {"type": "text", "text": "[Image]"},
        {"type": "text", "text": "isn't it cool"},
    ]
    assert stats.fixed_image_blocks == 1


def test_empty_modalities_returns_contexts_unchanged() -> None:
    contexts = [_user(_image_url_part(GIF_DATA_URL))]
    sanitized, stats = sanitize_contexts_by_modalities(contexts, None)

    assert sanitized[0]["content"] == contexts[0]["content"]
    assert not stats.changed


def test_empty_contexts_returns_empty() -> None:
    sanitized, stats = sanitize_contexts_by_modalities([], ["text", "image"])
    assert sanitized == []
    assert isinstance(stats, ContextSanitizeStats)
    assert not stats.changed
