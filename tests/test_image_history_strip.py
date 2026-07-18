from astrbot.core.agent.message import (
    ImageURLPart,
    Message,
    TextPart,
    bind_checkpoint_messages,
    dump_messages_with_checkpoints,
    strip_images_from_history_messages,
)
from astrbot.core.astr_main_agent import _finalize_request_image_urls


def test_dump_messages_strips_image_parts():
    msg = Message(
        role="user",
        content=[
            TextPart(text="see this"),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="data:image/png;base64,AAAA")),
            ImageURLPart(image_url=ImageURLPart.ImageURL(url="https://example.com/x.jpg")),
        ],
    )
    dumped = dump_messages_with_checkpoints([msg])
    content = dumped[0]["content"]
    assert all(part.get("type") != "image_url" for part in content)
    assert sum(1 for part in content if part.get("text") == "[Image]") == 1


def test_bind_checkpoint_messages_strips_polluted_history():
    hist = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "old"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBB"}},
                {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}},
            ],
        }
    ]
    bound = bind_checkpoint_messages(hist)
    types = [getattr(part, "type", None) for part in bound[0].content]
    assert "image_url" not in types
    stripped = strip_images_from_history_messages(hist)
    assert all(part.get("type") != "image_url" for part in stripped[0]["content"])


def test_finalize_request_image_urls_prefers_local_and_limits():
    out = _finalize_request_image_urls(
        [
            "https://example.com/a",
            r"C:\\tmp\\a.jpg",
            "https://example.com/a",
            r"C:\\tmp\\b.jpg",
            "https://example.com/c.jpg",
        ],
        max_total=2,
    )
    assert len(out) == 2
    assert all(not u.startswith("http") for u in out)
