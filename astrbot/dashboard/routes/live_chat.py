from typing import Any

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.dashboard.fastapi_compat import websocket
from astrbot.dashboard.services.live_chat_service import LiveChatService

from .route import Route, RouteContext


class LiveChatRoute(Route):
    """Live Chat WebSocket 路由"""

    def __init__(
        self,
        context: RouteContext,
        db: Any,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.service = LiveChatService(db, core_lifecycle)
        self.sessions = self.service.sessions

        self.app.websocket("/api/live_chat/ws")(self.live_chat_ws)
        self.app.websocket("/api/unified_chat/ws")(self.unified_chat_ws)

    async def live_chat_ws(self) -> None:
        """Legacy Live Chat WebSocket 处理器（默认 ct=live）"""
        await self._unified_ws_loop(force_ct="live")

    async def unified_chat_ws(self) -> None:
        """Unified Chat WebSocket 处理器（支持 ct=live/chat）"""
        await self._unified_ws_loop(force_ct=None)

    async def _unified_ws_loop(self, force_ct: str | None = None) -> None:
        await self.service.run_websocket_session(
            token=websocket.args.get("token"),
            force_ct=force_ct,
            receive_json=websocket.receive_json,
            send_json=websocket.send_json,
            close=websocket.close,
        )


__all__ = ["LiveChatRoute"]
