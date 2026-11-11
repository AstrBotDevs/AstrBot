"""Bot binding routes: QQ / WeChat QR + QQ manual AppID/Secret."""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.engine import get_db
from app.models.user import User
from app.providers.astrbot import AstrBotClient, AstrBotClientError
from app.schemas.commerce import (
    BindingManualRequest,
    BindingPublic,
    BindMetaPublic,
    QrPollPublic,
    QrPollRequest,
    QrStartPublic,
    QrStartRequest,
)
from app.services import bot_bind

router = APIRouter(prefix="/bot", tags=["bot"])


def _http_from_value_error(exc: ValueError) -> HTTPException:
    detail = str(exc) or "Bad request"
    code = status.HTTP_400_BAD_REQUEST
    if "添饭" in detail:
        code = status.HTTP_402_PAYMENT_REQUIRED
    elif "已经接过" in detail:
        code = status.HTTP_409_CONFLICT
    return HTTPException(status_code=code, detail=detail)


def _http_from_astrbot(exc: AstrBotClientError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if code == 503:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="鱼咖接线服务还没配好，稍后再试或找鱼咖",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"鱼咖接线失败：{exc}",
    )


@router.get("/bind/meta", response_model=BindMetaPublic)
def bind_meta() -> BindMetaPublic:
    """Public bind-page hints (egress IP, whether AstrBot key is set)."""
    return BindMetaPublic(
        qq_egress_ip=settings.qq_egress_ip.strip(),
        astrbot_ready=AstrBotClient().configured(),
        channels=["qq", "weixin"],
    )


@router.get("/binding", response_model=BindingPublic | None)
def get_binding(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BindingPublic | None:
    """Return the user's bot binding."""
    row = bot_bind.get_binding(db, current_user.id)
    return BindingPublic.model_validate(row) if row else None


@router.post("/bind/qr/start", response_model=QrStartPublic)
async def bind_qr_start(
    body: QrStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QrStartPublic:
    """Create a one-time bind QR for QQ or WeChat; secrets stay server-side."""
    try:
        session = await bot_bind.start_qr_bind(
            current_user,
            db,
            channel=body.channel,
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except AstrBotClientError as exc:
        raise _http_from_astrbot(exc) from exc
    expires_in = max(int(session.expires_at - time.time()), 1)
    return QrStartPublic(
        session_id=session.session_id,
        channel=session.channel,
        qrcode=session.qrcode_display,
        interval=session.interval,
        expires_in=expires_in,
    )


@router.post("/bind/qr/poll", response_model=QrPollPublic)
async def bind_qr_poll(
    body: QrPollRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QrPollPublic:
    """Poll QR bind once; on success create the AstrBot instance."""
    try:
        status_name, binding, message = await bot_bind.poll_qr_bind(
            current_user,
            db,
            session_id=body.session_id.strip(),
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except AstrBotClientError as exc:
        raise _http_from_astrbot(exc) from exc
    return QrPollPublic(
        status=status_name,
        message=message,
        binding=BindingPublic.model_validate(binding) if binding else None,
    )


@router.post("/bind/manual", response_model=BindingPublic)
async def bind_manual(
    body: BindingManualRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BindingPublic:
    """Advanced QQ path: paste AppID + AppSecret (not returned in response)."""
    try:
        binding = await bot_bind.manual_bind(
            current_user,
            db,
            qq_appid=body.qq_appid,
            app_secret=body.app_secret,
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except AstrBotClientError as exc:
        raise _http_from_astrbot(exc) from exc
    return BindingPublic.model_validate(binding)
