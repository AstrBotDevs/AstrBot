"""Peer SDK plugin providing host-scoped and direct services."""

from __future__ import annotations

from typing import Any

from astrbot_sdk import DirectContext, Plugin, on


class FullApiPeerPlugin(Plugin):
    """Export host-scoped and direct cross-plugin services."""

    @on.service("summarize")
    async def summarize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Increment a KV counter and summarize the requested topic."""
        topic = str(payload.get("topic") or "")
        calls = int(await self.ctx.storage.get("peer_calls", 0)) + 1
        await self.ctx.storage.set("peer_calls", calls)
        return {"summary": f"peer:{topic}", "calls": calls}

    @on.direct_service("fast_tag")
    async def fast_tag(
        self,
        payload: dict[str, Any],
        dctx: DirectContext,
    ) -> dict[str, Any]:
        """Compute a lightweight tag using DirectContext with zero Host privileges."""
        assert isinstance(dctx, DirectContext)
        assert not hasattr(dctx, "storage")
        assert not hasattr(dctx, "messages")
        assert not hasattr(dctx, "plugins")
        text = str(payload.get("text") or "")
        return {"tag": f"[{dctx.plugin.name}] {text}"}
