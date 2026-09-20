from __future__ import annotations

from fastapi import APIRouter, WebSocket

from astrbot.dashboard.services.live_chat_service import LiveChatService

router = APIRouter(tags=["Live Chat"])
legacy_router = APIRouter(
    prefix="/api",
    tags=["Dashboard Live Chat"],
    include_in_schema=False,
)


def get_service(websocket: WebSocket) -> LiveChatService:
    return websocket.app.state.services.live_chat


async def _run_live_chat_ws(
    websocket: WebSocket,
    *,
    force_ct: str | None,
) -> None:
    await websocket.accept()
    service = get_service(websocket)
    await service.run_websocket_session(
        token=websocket.query_params.get("token"),
        force_ct=force_ct,
        receive_json=websocket.receive_json,
        send_json=websocket.send_json,
        close=websocket.close,
    )


@router.websocket("/live-chat/ws")
async def live_chat_ws(websocket: WebSocket) -> None:
    await _run_live_chat_ws(websocket, force_ct="live")


@router.websocket("/unified-chat/ws")
async def unified_chat_ws(websocket: WebSocket) -> None:
    await _run_live_chat_ws(websocket, force_ct=None)


@legacy_router.websocket("/live_chat/ws")
async def dashboard_live_chat_ws(websocket: WebSocket) -> None:
    await _run_live_chat_ws(websocket, force_ct="live")


@legacy_router.websocket("/unified_chat/ws")
async def dashboard_unified_chat_ws(websocket: WebSocket) -> None:
    await _run_live_chat_ws(websocket, force_ct=None)
