"""Bot bind flow: QQ / WeChat QR + QQ manual credentials."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass

from app.models.user import User
from app.models.wallet import BotBinding
from app.providers.astrbot import AstrBotClient, AstrBotClientError
from app.services.wallet import get_or_create_wallet
from sqlalchemy import select
from sqlalchemy.orm import Session

# QQ create form (avatar + name) often takes several minutes; keep bind_key
# until QQ reports created/expired, not a short client-side timeout.
QR_SESSION_TTL_SECONDS = 900
CHANNEL_QQ = "qq"
CHANNEL_WEIXIN = "weixin"
SUPPORTED_CHANNELS = frozenset({CHANNEL_QQ, CHANNEL_WEIXIN})


@dataclass
class QrBindSession:
    """Server-side QR bind state; secrets never leave the API process."""

    session_id: str
    user_id: str
    channel: str
    # Display string for the console (URL or payload to render as QR).
    qrcode_display: str
    interval: int
    expires_at: float
    # QQ poll credentials
    task_id: str = ""
    bind_key: str = ""
    # WeChat poll credential
    poll_qrcode: str = ""


_sessions: dict[str, QrBindSession] = {}
_sessions_lock = threading.Lock()


def can_bind(user: User, db: Session) -> bool:
    """Return True when the bowl still has rice and account is active."""
    wallet = get_or_create_wallet(db, user.id)
    return wallet.balance_yuan > 0 and wallet.status == "active"


def get_binding(db: Session, user_id: str) -> BotBinding | None:
    """Return the user's binding row if any."""
    return db.scalar(select(BotBinding).where(BotBinding.user_id == user_id))


def normalize_channel(channel: str | None) -> str:
    """Validate and normalize channel id.

    Args:
        channel: Raw channel from the client.

    Returns:
        `qq` or `weixin`.

    Raises:
        ValueError: Unknown channel.
    """
    value = (channel or CHANNEL_QQ).strip().lower()
    if value not in SUPPORTED_CHANNELS:
        raise ValueError("请选择 QQ 官方机器人 或 微信官方机器人")
    return value


def make_adapter_id(user_id: str, channel: str, external_id: str) -> str:
    """Build a stable AstrBot platform id for this fish user + bot."""
    short = user_id.replace("-", "")[:8]
    suffix = "".join(ch for ch in external_id if ch.isalnum())[:32] or "bot"
    prefix = "fish" if channel == CHANNEL_QQ else "fishwx"
    return f"{prefix}_{short}_{suffix}"


def _purge_expired_locked(now: float | None = None) -> None:
    now = time.time() if now is None else now
    expired = [sid for sid, s in _sessions.items() if s.expires_at <= now]
    for sid in expired:
        _sessions.pop(sid, None)


def store_qr_session(session: QrBindSession) -> QrBindSession:
    """Replace any prior QR session for this user and store a new one."""
    with _sessions_lock:
        _purge_expired_locked()
        stale = [sid for sid, s in _sessions.items() if s.user_id == session.user_id]
        for sid in stale:
            _sessions.pop(sid, None)
        _sessions[session.session_id] = session
    return session


def get_qr_session(session_id: str, user_id: str) -> QrBindSession | None:
    """Fetch a non-expired session owned by the user."""
    now = time.time()
    with _sessions_lock:
        _purge_expired_locked(now)
        session = _sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None
        if session.expires_at <= now:
            _sessions.pop(session_id, None)
            return None
        return session


def drop_qr_session(session_id: str) -> None:
    """Remove a QR session after success or cancel."""
    with _sessions_lock:
        _sessions.pop(session_id, None)


def _assert_can_start(user: User, db: Session) -> None:
    if not can_bind(user, db):
        raise ValueError("请先添饭，碗里有饭才能接鱼")
    existing = get_binding(db, user.id)
    if existing is not None and existing.bind_status == "active":
        raise ValueError("你已经接过鱼了，想换请先联系鱼咖")


async def start_qr_bind(
    user: User,
    db: Session,
    *,
    channel: str,
) -> QrBindSession:
    """Ask AstrBot for a fresh bind QR for the chosen channel.

    Args:
        user: Authenticated fish user.
        db: SQLAlchemy session.
        channel: `qq` or `weixin`.

    Returns:
        QR session stored server-side.

    Raises:
        ValueError: Business rule failures.
        AstrBotClientError: Engine HTTP failures.
    """
    channel = normalize_channel(channel)
    _assert_can_start(user, db)
    client = AstrBotClient()
    now = time.time()
    session_id = str(uuid.uuid4())

    if channel == CHANNEL_QQ:
        data = await client.start_qq_registration()
        task_id = str(
            data.get("task_id") or data.get("registration_code") or ""
        ).strip()
        bind_key = str(data.get("bind_key") or "").strip()
        qrcode = str(data.get("qrcode") or data.get("qrcode_img_content") or "").strip()
        interval = int(data.get("interval") or 2)
        if not task_id or not bind_key or not qrcode:
            raise ValueError("鱼咖接线失败：二维码不完整，请稍后重试")
        return store_qr_session(
            QrBindSession(
                session_id=session_id,
                user_id=user.id,
                channel=channel,
                qrcode_display=qrcode,
                interval=max(interval, 1),
                expires_at=now + QR_SESSION_TTL_SECONDS,
                task_id=task_id,
                bind_key=bind_key,
            )
        )

    data = await client.start_weixin_registration()
    poll_qrcode = str(data.get("qrcode") or data.get("registration_code") or "").strip()
    display = str(data.get("qrcode_img_content") or data.get("qrcode") or "").strip()
    interval = int(data.get("interval") or 1)
    if not poll_qrcode or not display:
        raise ValueError("鱼咖接线失败：微信二维码不完整，请稍后重试")
    return store_qr_session(
        QrBindSession(
            session_id=session_id,
            user_id=user.id,
            channel=channel,
            qrcode_display=display,
            interval=max(interval, 1),
            expires_at=now + QR_SESSION_TTL_SECONDS,
            poll_qrcode=poll_qrcode,
        )
    )


async def poll_qr_bind(
    user: User,
    db: Session,
    *,
    session_id: str,
) -> tuple[str, BotBinding | None, str | None]:
    """Poll QR bind once; on success create the AstrBot bot and save binding.

    Args:
        user: Authenticated fish user.
        db: SQLAlchemy session.
        session_id: Id returned by start_qr_bind.

    Returns:
        Tuple of (status, binding_or_none, message_or_none).

    Raises:
        ValueError: Missing/expired session or business errors.
        AstrBotClientError: Engine HTTP failures.
    """
    if not can_bind(user, db):
        raise ValueError("请先添饭，碗里有饭才能接鱼")
    session = get_qr_session(session_id, user.id)
    if session is None:
        raise ValueError("二维码已失效，请刷新后再扫")

    client = AstrBotClient()
    if session.channel == CHANNEL_QQ:
        data = await client.poll_qq_registration(
            task_id=session.task_id,
            bind_key=session.bind_key,
        )
    else:
        data = await client.poll_weixin_registration(qrcode=session.poll_qrcode)

    status = str(data.get("status") or "").strip().lower()
    if status in {"pending", "slow_down"}:
        return "pending", None, None
    if status == "expired":
        drop_qr_session(session_id)
        return "expired", None, str(data.get("message") or "二维码已过期")
    if status == "denied":
        drop_qr_session(session_id)
        return "error", None, str(data.get("message") or "已取消扫码")
    if status != "created":
        return "error", None, str(data.get("message") or "扫码失败，请重试")

    if session.channel == CHANNEL_QQ:
        appid = str(data.get("appid") or "").strip()
        secret = str(data.get("secret") or "").strip()
        if not appid or not secret:
            return "error", None, "扫码成功但未返回完整凭证"
        binding = await finalize_qq_binding(
            db,
            user=user,
            qq_appid=appid,
            app_secret=secret,
        )
    else:
        token = str(data.get("weixin_oc_token") or "").strip()
        account_id = str(data.get("weixin_oc_account_id") or "").strip()
        base_url = str(data.get("weixin_oc_base_url") or "").strip()
        if not token:
            return "error", None, "扫码成功但未返回微信凭证"
        binding = await finalize_weixin_binding(
            db,
            user=user,
            token=token,
            account_id=account_id or f"wx_{user.id[:8]}",
            base_url=base_url,
        )

    drop_qr_session(session_id)
    return "active", binding, None


async def manual_bind(
    user: User,
    db: Session,
    *,
    qq_appid: str,
    app_secret: str,
) -> BotBinding:
    """Create AstrBot QQ bot from pasted credentials and save binding."""
    _assert_can_start(user, db)
    appid = qq_appid.strip()
    secret = app_secret.strip()
    if len(appid) < 4 or len(secret) < 4:
        raise ValueError("AppID 或 AppSecret 不正确")
    return await finalize_qq_binding(
        db,
        user=user,
        qq_appid=appid,
        app_secret=secret,
    )


async def _create_bot_with_retries(
    *,
    adapter_id: str,
    create,
) -> str:
    """Create an AstrBot bot, retrying with a suffix if the id exists."""
    suffix = secrets.token_hex(2)
    candidate = adapter_id
    last_error: AstrBotClientError | None = None
    for attempt in range(3):
        try:
            await create(candidate)
            return candidate
        except AstrBotClientError as exc:
            last_error = exc
            message = str(exc).lower()
            if "already exists" in message or "已存在" in message:
                candidate = f"{adapter_id}_{suffix}{attempt}"
                continue
            raise
    if last_error is not None:
        raise last_error
    return adapter_id


def _upsert_binding(
    db: Session,
    *,
    user: User,
    channel: str,
    adapter_id: str,
    external_id: str,
) -> BotBinding:
    binding = get_binding(db, user.id)
    if binding is None:
        binding = BotBinding(
            user_id=user.id,
            channel=channel,
            qq_appid=external_id,
            adapter_id=adapter_id,
            umo_prefix=adapter_id,
            bind_status="active",
        )
        db.add(binding)
    else:
        binding.channel = channel
        binding.qq_appid = external_id
        binding.adapter_id = adapter_id
        binding.umo_prefix = adapter_id
        binding.bind_status = "active"
    db.commit()
    db.refresh(binding)
    return binding


async def finalize_qq_binding(
    db: Session,
    *,
    user: User,
    qq_appid: str,
    app_secret: str,
) -> BotBinding:
    """Create qq_official instance and upsert bot_bindings."""
    base_id = make_adapter_id(user.id, CHANNEL_QQ, qq_appid)
    client = AstrBotClient()

    async def create(candidate: str) -> None:
        await client.create_qq_official_bot(
            adapter_id=candidate,
            appid=qq_appid,
            secret=app_secret,
        )

    adapter_id = await _create_bot_with_retries(adapter_id=base_id, create=create)
    return _upsert_binding(
        db,
        user=user,
        channel=CHANNEL_QQ,
        adapter_id=adapter_id,
        external_id=qq_appid,
    )


async def finalize_weixin_binding(
    db: Session,
    *,
    user: User,
    token: str,
    account_id: str,
    base_url: str,
) -> BotBinding:
    """Create weixin_oc instance and upsert bot_bindings."""
    base_id = make_adapter_id(user.id, CHANNEL_WEIXIN, account_id)
    client = AstrBotClient()

    async def create(candidate: str) -> None:
        await client.create_weixin_oc_bot(
            adapter_id=candidate,
            token=token,
            account_id=account_id,
            base_url=base_url,
        )

    adapter_id = await _create_bot_with_retries(adapter_id=base_id, create=create)
    return _upsert_binding(
        db,
        user=user,
        channel=CHANNEL_WEIXIN,
        adapter_id=adapter_id,
        external_id=account_id,
    )
