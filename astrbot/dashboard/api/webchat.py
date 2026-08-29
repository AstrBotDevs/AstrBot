from fastapi import APIRouter, WebSocket

from astrbot.dashboard.services.webchat_service import WebChatService

router = APIRouter(tags=["Chat"])


def get_service(websocket: WebSocket) -> WebChatService:
    return websocket.app.state.services.webchat


async def _run_unified_chat_ws(
    websocket: WebSocket,
) -> None:
    await websocket.accept()
    service = get_service(websocket)
    await service.run_websocket_session(
        token=websocket.query_params.get("token"),
        receive_json=websocket.receive_json,
        send_json=websocket.send_json,
        close=websocket.close,
    )


@router.websocket("/unified-chat/ws")
async def unified_chat_ws(websocket: WebSocket) -> None:
    await _run_unified_chat_ws(websocket)
