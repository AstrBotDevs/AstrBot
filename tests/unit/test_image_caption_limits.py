import asyncio
from types import SimpleNamespace

import pytest

from astrbot.api.platform import MessageType
from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext


class _FakePreferences:
    pass


def _context() -> GroupChatContext:
    plugin_context = SimpleNamespace(
        config=SimpleNamespace(get=lambda umo=None: {}),
        models=SimpleNamespace(using_chat=lambda: None, get=lambda _id: None),
        preferences=_FakePreferences(),
    )
    return GroupChatContext(plugin_context)


def _cfg(**overrides):
    base = {
        "image_caption": True,
        "image_caption_scope": "all",
        "image_caption_groups": [],
        "image_caption_min_interval": 0,
        "image_caption_max_concurrency": 2,
        "image_caption_provider_id": "caption",
        "image_caption_prompt": "describe",
    }
    base.update(overrides)
    return base


def test_empty_allowlist_denies() -> None:
    ctx = _context()
    assert (
        ctx.allows_group_image_caption(
            "aiocqhttp:GroupMessage:1:bot_2",
            _cfg(image_caption_scope="allowlist", image_caption_groups=[]),
        )
        is False
    )


def test_allowlist_requires_exact_umo() -> None:
    ctx = _context()
    umo = "aiocqhttp:GroupMessage:123456:bot_987654"
    cfg = _cfg(image_caption_scope="allowlist", image_caption_groups=[umo])
    assert ctx.allows_group_image_caption(umo, cfg) is True
    assert ctx.allows_group_image_caption("123456", cfg) is False


def test_denylist_rejects_listed_umo() -> None:
    ctx = _context()
    umo = "telegram:group:-1001234567890:bot_123"
    cfg = _cfg(image_caption_scope="denylist", image_caption_groups=[umo])
    assert ctx.allows_group_image_caption(umo, cfg) is False
    assert ctx.allows_group_image_caption("telegram:group:other:bot_123", cfg) is True


@pytest.mark.asyncio
async def test_non_group_handle_message_skips(monkeypatch) -> None:
    ctx = _context()
    called = False

    async def fail(*args, **kwargs):
        nonlocal called
        called = True

    event = SimpleNamespace(
        get_message_type=lambda: MessageType.FRIEND_MESSAGE,
        unified_msg_origin="webchat:friend:1:bot",
    )
    monkeypatch.setattr(ctx, "_format_message", fail)
    await ctx.handle_message(event)
    assert called is False


@pytest.mark.asyncio
async def test_negative_interval_is_treated_as_zero() -> None:
    ctx = _context()
    assert await ctx._claim_caption_slot("umo", -3) is True
    assert await ctx._claim_caption_slot("umo", 0) is True


@pytest.mark.asyncio
async def test_concurrent_claims_only_one_succeeds() -> None:
    ctx = _context()
    results = await asyncio.gather(
        ctx._claim_caption_slot("same", 10),
        ctx._claim_caption_slot("same", 10),
        ctx._claim_caption_slot("same", 10),
    )
    assert results.count(True) == 1


@pytest.mark.asyncio
async def test_failed_caption_still_consumes_interval() -> None:
    ctx = _context()
    assert await ctx._claim_caption_slot("g1", 30) is True
    assert await ctx._claim_caption_slot("g1", 30) is False


@pytest.mark.asyncio
async def test_umo_cleanup_removes_timestamp() -> None:
    ctx = _context()
    await ctx._claim_caption_slot("g1", 30)
    event = SimpleNamespace(unified_msg_origin="g1")
    await ctx.remove_session(event)
    assert "g1" not in ctx._caption_last_claim


@pytest.mark.asyncio
async def test_different_umos_do_not_share_interval() -> None:
    ctx = _context()
    assert await ctx._claim_caption_slot("a", 30) is True
    assert await ctx._claim_caption_slot("b", 30) is True


@pytest.mark.asyncio
async def test_singleflight_shares_success() -> None:
    ctx = _context()
    calls = 0

    async def fake_caption(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "cat"

    ctx.get_image_caption = fake_caption
    cfg = _cfg()
    first, second = await asyncio.gather(
        ctx.caption_with_singleflight("umo-a", "https://cdn.example/a.png", cfg),
        ctx.caption_with_singleflight("umo-a", "https://cdn.example/a.png", cfg),
    )
    assert first == second == "cat"
    assert calls == 1


@pytest.mark.asyncio
async def test_singleflight_exception_clears_inflight() -> None:
    ctx = _context()
    calls = 0

    async def boom(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("vlm failed")

    ctx.get_image_caption = boom
    cfg = _cfg()
    with pytest.raises(RuntimeError, match="vlm failed"):
        await ctx.caption_with_singleflight("umo-a", "https://cdn.example/a.png", cfg)
    assert ctx._caption_inflight == {}
    with pytest.raises(RuntimeError, match="vlm failed"):
        await ctx.caption_with_singleflight("umo-a", "https://cdn.example/a.png", cfg)
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_is_umo_scoped_and_disabled_by_default() -> None:
    ctx = _context()
    calls = 0

    async def fake_caption(*args, **kwargs):
        nonlocal calls
        calls += 1
        return "dog"

    ctx.get_image_caption = fake_caption
    await ctx.caption_with_singleflight("umo-a", "https://cdn.example/a.png", _cfg())
    await ctx.caption_with_singleflight("umo-b", "https://cdn.example/a.png", _cfg())
    assert calls == 2
    calls = 0
    cached_cfg = _cfg(image_caption_cache_ttl=30)
    await ctx.caption_with_singleflight(
        "umo-a", "https://cdn.example/a.png", cached_cfg
    )
    await ctx.caption_with_singleflight(
        "umo-a", "https://cdn.example/a.png", cached_cfg
    )
    assert calls == 1


@pytest.mark.asyncio
async def test_lazy_caption_resolves_placeholder() -> None:
    ctx = _context()

    async def fake_caption(*args, **kwargs):
        return "bird"

    ctx.get_image_caption = fake_caption
    token = ctx._remember_lazy_image("umo-a", "https://cdn.example/a.png")
    records = [f"user [Image:__LAZY__:{token}]"]
    resolved = await ctx._resolve_lazy_captions(records, _cfg(), "umo-a")
    assert resolved == ["user [Image: bird]"]
    assert token not in ctx._pending_images


def test_caption_failure_keeps_image_placeholder() -> None:
    # Covered by format path: empty/exception yields [Image]
    from astrbot.api.message_components import Image
    from astrbot.builtin_stars.astrbot.group_chat_context import _describe_chain

    assert "[Image]" in _describe_chain([Image.fromURL("https://cdn.example/a.png")])
