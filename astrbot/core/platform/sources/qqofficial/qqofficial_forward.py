"""Images embedded in a quoted QQ Official merged chat record."""

import re
from collections.abc import Iterator

_HEADER = re.compile(r"^=== 消息 [0-9]+ ===[ \t]*\r?$", re.MULTILINE)
_IMAGE_LINE = re.compile(
    r"\[附件[0-9]+\]\s+类型[:：]\s*图片\s+文件名[:：].*\sURL[:：]\s*(\S+)"
)
_QQ_IMAGE = re.compile(
    r"https://multimedia\.nt\.qq\.com\.cn/download\?[A-Za-z0-9._~%&=+/\-]{1,4096}"
)


def _entries(
    element: object, in_record: bool = False, depth: int = 0
) -> Iterator[object]:
    """Walk QQ's numbered transcript and nested type-102 records in order."""
    if not isinstance(element, dict) or depth > 8:
        return
    content = element.get("content")
    if isinstance(content, str) and _HEADER.search(content):
        for line in content.splitlines():
            if match := _IMAGE_LINE.fullmatch(line.strip()):
                yield match[1]

    in_record = in_record or element.get("message_type") in (102, "102")
    attachments = element.get("attachments")
    if in_record and isinstance(attachments, list):
        for item in attachments:
            if isinstance(item, dict) and str(item.get("content_type")).startswith(
                "image/"
            ):
                yield item.get("url")

    children = element.get("msg_elements")
    if isinstance(children, list):
        for child in children:
            yield from _entries(child, in_record, depth + 1)


def quoted_forward_images(element: object, existing: set[str]) -> Iterator[str]:
    """Extract image URLs without duplicating top-level quote attachments.

    Args:
        element: First raw message element of a type-103 reply.
        existing: Images already attached to the reply.

    Yields:
        Up to eight additional QQ CDN image URLs in record order.
    """
    seen = existing.copy()
    for url in _entries(element):
        if isinstance(url, str) and _QQ_IMAGE.fullmatch(url) and url not in seen:
            seen.add(url)
            yield url
            if len(seen) - len(existing) == 8:
                return
