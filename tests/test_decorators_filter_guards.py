from __future__ import annotations

import pytest

from astrbot_sdk.decorators import (
    append_filter_meta,
    get_handler_meta,
    message_types,
    platforms,
    require_admin,
    require_permission,
)
from astrbot_sdk.protocol.descriptors import (
    MessageTypeFilterSpec,
    Permissions,
    PlatformFilterSpec,
)


def test_platforms_rejects_existing_manual_platform_filter() -> None:
    def handler() -> None:
        return None

    append_filter_meta(
        handler,
        specs=[PlatformFilterSpec(platforms=["qq"])],
    )

    meta = get_handler_meta(handler)
    assert meta is not None
    assert meta.decorator_sources == {}

    with pytest.raises(ValueError, match="已有平台过滤器"):
        platforms("wechat")(handler)


def test_message_types_rejects_existing_manual_message_type_filter() -> None:
    def handler() -> None:
        return None

    append_filter_meta(
        handler,
        specs=[MessageTypeFilterSpec(message_types=["group"])],
    )

    meta = get_handler_meta(handler)
    assert meta is not None
    assert meta.decorator_sources == {}

    with pytest.raises(ValueError, match="已有消息类型过滤器"):
        message_types("private")(handler)


def test_require_permission_sets_normalized_permissions() -> None:
    def handler() -> None:
        return None

    require_permission("admin")(handler)

    meta = get_handler_meta(handler)
    assert meta is not None
    assert meta.permissions == Permissions(require_admin=True)


def test_require_permission_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="只支持"):
        require_permission("owner")  # type: ignore[arg-type]


def test_require_permission_rejects_conflicting_markers() -> None:
    def handler() -> None:
        return None

    require_permission("member")(handler)

    with pytest.raises(ValueError, match="冲突"):
        require_admin(handler)
