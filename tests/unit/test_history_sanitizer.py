from copy import deepcopy

import pytest

from astrbot.core.agent.history_sanitizer import (
    IMAGE_HISTORY_PLACEHOLDER,
    sanitize_history_for_storage,
)
from astrbot.core.conversation_mgr import load_sanitized_history


def _image(url: str) -> dict:
    return {"type": "image_url", "image_url": {"url": url}}


def test_sanitize_history_replaces_only_base64_images_without_mutating_input():
    image_data = "data:image/png;base64,aGVsbG8="
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "caption"},
                _image(image_data),
                _image("https://example.test/image.png"),
            ],
        },
        {"role": "assistant", "content": "old string content"},
    ]
    original = deepcopy(messages)

    sanitized = sanitize_history_for_storage(messages)

    assert sanitized[0]["content"][0] == {"type": "text", "text": "caption"}
    assert sanitized[0]["content"][1]["image_url"]["url"] == IMAGE_HISTORY_PLACEHOLDER
    assert (
        sanitized[0]["content"][2]["image_url"]["url"]
        == "https://example.test/image.png"
    )
    assert messages == original


def test_sanitize_history_tolerates_malformed_parts_and_preserves_caption_text():
    messages = [
        {"role": "user", "content": None},
        {"role": "user", "content": [{"type": "image_url", "image_url": {}}]},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "<image_caption>a cat</image_caption>"},
                "malformed",
            ],
        },
    ]

    assert sanitize_history_for_storage(messages) == messages


def test_load_sanitized_history_handles_empty_and_legacy_base64_history():
    assert load_sanitized_history(None) == []
    assert load_sanitized_history("") == []

    history = '[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,abc"}}]}]'
    loaded = load_sanitized_history(history)
    assert loaded[0]["content"][0]["image_url"]["url"] == IMAGE_HISTORY_PLACEHOLDER


@pytest.mark.parametrize("content", ["text", None, {"unexpected": True}])
def test_sanitize_history_skips_non_list_content(content):
    assert sanitize_history_for_storage([{"role": "user", "content": content}]) == [
        {"role": "user", "content": content}
    ]
