import asyncio
import json
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import jwt
from starlette.websockets import WebSocketDisconnect

from astrbot import logger
from astrbot.core.agent.mcp_client import MCPInteractionCoordinator, MCPInteractionKey
from astrbot.core.auth.models import WEBCHAT_INSTANCE_TOOL_ACTIONS
from astrbot.core.db.protocols import ChatStore
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.datetime_utils import to_utc_isoformat
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.webchat.message_parts import (
    build_webchat_message_parts,
    create_attachment_part_from_existing_file,
    strip_message_parts_path_fields,
    webchat_message_parts_have_content,
)
from astrbot.core.webchat.result_reducer import (
    BotMessageAccumulator,
    build_bot_history_content,
    collect_plain_text_from_message_parts,
    merge_webchat_refs,
    parse_webchat_attachment,
)
from astrbot.core.webchat.run_coordinator import (
    DuplicateWebChatRunError,
    WebChatRun,
    WebChatRunCoordinator,
)
from astrbot.dashboard.services.auth_service import (
    AuthService,
    DashboardSessionPrincipal,
    DashboardTokenValidator,
)
from astrbot.dashboard.services.chat_service import (
    ChatServiceError,
    ensure_webchat_platform_session_owner,
)

if TYPE_CHECKING:
    from astrbot.core.config.astrbot_config import AstrBotConfig
    from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
    from astrbot.core.utils.shared_preferences import SharedPreferences

SendJson = Callable[[dict], Awaitable[None]]
ReceiveJson = Callable[[], Awaitable[dict]]
CloseWebSocket = Callable[[int, str], Awaitable[None]]


class WebChatAuthError(Exception):
    pass


class WebChatSession:
    """WebChat 会话管理器"""

    def __init__(
        self,
        session_id: str,
        username: str,
        dashboard_principal: DashboardSessionPrincipal | None = None,
    ) -> None:
        self.session_id = session_id
        self.username = username
        self.dashboard_principal = dashboard_principal
        self.webchat_step_up_tokens: dict[str, str] = {}
        self.webchat_step_up_session_id: str | None = None
        self.chat_subscriptions: dict[str, str] = {}
        self.chat_subscription_tasks: dict[str, asyncio.Task] = {}
        self.chat_request_tasks: dict[str, asyncio.Task] = {}
        self.interrupted_chat_requests: set[str] = set()
        self.ws_send_lock = asyncio.Lock()


class WebChatService:
    def __init__(
        self,
        db: ChatStore,
        *,
        preferences: SharedPreferences,
        config: AstrBotConfig,
        platform_message_history_manager: PlatformMessageHistoryManager,
        webchat_run_coordinator: WebChatRunCoordinator,
        mcp_interaction_coordinator: MCPInteractionCoordinator | None = None,
        token_validator: DashboardTokenValidator | None = None,
        auth_service: AuthService | None = None,
    ) -> None:
        self.db = db
        self.preferences = preferences
        self.webchat_run_coordinator = webchat_run_coordinator
        self.mcp_interaction_coordinator = mcp_interaction_coordinator
        self.config = config
        self.token_validator = token_validator or DashboardTokenValidator(
            self.config["dashboard"].get("jwt_secret", "")
        )
        self.auth_service = auth_service
        self.platform_history_mgr = platform_message_history_manager
        self.sessions: dict[str, WebChatSession] = {}
        self._mcp_publishers: dict[str, tuple[WebChatSession, SendJson]] = {}
        self.attachments_dir = os.path.join(get_astrbot_data_path(), "attachments")
        self.webchat_img_dir = os.path.join(get_astrbot_data_path(), "webchat", "imgs")
        os.makedirs(self.attachments_dir, exist_ok=True)
        if self.mcp_interaction_coordinator is not None:
            self.mcp_interaction_coordinator.set_publisher(self._publish_mcp_input)

    async def _publish_mcp_input(self, payload: dict) -> None:
        """Send elicitation to only the WebChat connection owning its UMO."""
        umo = payload.get("unified_msg_origin")
        target = self._mcp_publishers.get(str(umo))
        if target is None:
            return
        session, send_json = target
        await self.send_chat_payload(session, {"ct": "chat", **payload}, send_json)

    def authenticate_token(
        self,
        token: str | None,
    ) -> str:
        if not token:
            raise WebChatAuthError("Missing authentication token")
        try:
            return self.token_validator.validate(token).username
        except jwt.ExpiredSignatureError as exc:
            raise WebChatAuthError("Token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise WebChatAuthError("Invalid token") from exc

    async def _validate_dashboard_principal(
        self, token: str
    ) -> DashboardSessionPrincipal | None:
        """Validate account state before accepting a Dashboard WebSocket."""

        if self.auth_service is None:
            return None
        try:
            principal = self.token_validator.validate(token)
        except jwt.ExpiredSignatureError as exc:
            raise WebChatAuthError("Token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise WebChatAuthError("Invalid token") from exc
        if (
            not principal.account_id
            or not await self.auth_service.validate_dashboard_principal(principal)
        ):
            raise WebChatAuthError("Invalid token")
        return principal

    def create_session(
        self,
        username: str,
        dashboard_principal: DashboardSessionPrincipal | None = None,
    ) -> WebChatSession:
        session_id = f"webchat!{username}!{uuid.uuid4()}"
        session = WebChatSession(session_id, username, dashboard_principal)
        self.sessions[session_id] = session
        return session

    @staticmethod
    def _dashboard_principal_payload(
        session: WebChatSession,
        step_up_tokens: dict[str, str] | None = None,
        *,
        webchat_session_id: str | None = None,
        include_step_up_tokens: bool = True,
    ) -> dict[str, dict[str, object]]:
        principal = session.dashboard_principal
        if principal is None or not principal.account_id:
            return {}
        payload: dict[str, object] = {
            "account_id": principal.account_id,
            "sid": principal.sid,
            "username": principal.username,
            "auth_strength": principal.auth_strength,
        }
        if webchat_session_id is not None and (
            session.webchat_step_up_session_id != webchat_session_id
        ):
            session.webchat_step_up_tokens = {}
            session.webchat_step_up_session_id = None
        if step_up_tokens is not None:
            session.webchat_step_up_tokens = {
                action: token
                for action, token in step_up_tokens.items()
                if action in WEBCHAT_INSTANCE_TOOL_ACTIONS
                and isinstance(token, str)
                and 0 < len(token) <= 512
            }
            session.webchat_step_up_session_id = webchat_session_id
        if (
            include_step_up_tokens
            and webchat_session_id is not None
            and session.webchat_step_up_session_id == webchat_session_id
            and session.webchat_step_up_tokens
        ):
            payload["step_up_tokens"] = dict(session.webchat_step_up_tokens)
        return {"_dashboard_principal": payload}

    async def _owns_chat_session(
        self,
        session: WebChatSession,
        chat_session_id: str,
    ) -> bool:
        """Check that a persistent WebChat session belongs to this user."""

        get_session = getattr(self.db, "get_platform_session_by_id", None)
        # Lightweight unit doubles without an authenticated Dashboard
        # principal are accepted only in tests. An authenticated Dashboard
        # WebSocket must always have the runtime DB; fail closed if that store
        # is unavailable.
        if not callable(get_session):
            return session.dashboard_principal is None
        try:
            await ensure_webchat_platform_session_owner(
                self.db,
                username=session.username,
                session_id=chat_session_id,
            )
        except ChatServiceError:
            return False
        return True

    async def cleanup_session(self, session: WebChatSession) -> None:
        if session.session_id in self.sessions:
            await self.cleanup_chat_subscriptions(session)
            del self.sessions[session.session_id]

    async def run_websocket_session(
        self,
        *,
        token: str | None,
        receive_json: ReceiveJson,
        send_json: SendJson,
        close: CloseWebSocket,
    ) -> None:
        try:
            username = self.authenticate_token(token)
            dashboard_principal = (
                await self._validate_dashboard_principal(token)
                if self.auth_service is not None and token is not None
                else None
            )
        except WebChatAuthError as exc:
            await close(1008, str(exc))
            return

        session = self.create_session(username, dashboard_principal)
        self._mcp_publishers[session.session_id] = (session, send_json)
        logger.info(f"[WebChat] WebSocket connection established: {username}")

        def finish_chat_request(completed: asyncio.Task, request_id: str) -> None:
            if session.chat_request_tasks.get(request_id) is completed:
                session.chat_request_tasks.pop(request_id, None)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error(
                    "[WebChat] WebSocket chat request failed: %s",
                    safe_error("", exc),
                )

        try:
            while True:
                message = await receive_json()
                if message.get("ct", "chat") == "chat":
                    if message.get("t") == "send":
                        request_id = str(message.get("message_id") or uuid.uuid4())
                        message["message_id"] = request_id
                        existing_task = session.chat_request_tasks.get(request_id)
                        if existing_task and not existing_task.done():
                            await self.send_chat_payload(
                                session,
                                {
                                    "ct": "chat",
                                    "t": "error",
                                    "data": "Duplicate active message_id",
                                    "code": "INVALID_MESSAGE_FORMAT",
                                    "message_id": request_id,
                                },
                                send_json,
                            )
                            continue
                        task = asyncio.create_task(
                            self.handle_chat_message(session, message, send_json),
                            name=f"chat_ws_request_{request_id}",
                        )
                        session.chat_request_tasks[request_id] = task
                        task.add_done_callback(
                            lambda completed, request_id=request_id: (
                                finish_chat_request(completed, request_id)
                            )
                        )
                    else:
                        await self.handle_chat_message(session, message, send_json)
                else:
                    await self.send_chat_payload(
                        session,
                        {
                            "ct": "chat",
                            "t": "error",
                            "data": "Unsupported message channel",
                            "code": "INVALID_MESSAGE_FORMAT",
                        },
                        send_json,
                    )

        except WebSocketDisconnect as exc:
            logger.debug(
                f"[WebChat] WebSocket disconnected: {username}, code={exc.code}"
            )
        except Exception as exc:
            logger.error(f"[WebChat] WebSocket error: {exc}", exc_info=True)

        finally:
            await self.cleanup_session(session)
            self._mcp_publishers.pop(session.session_id, None)
            logger.info(f"[WebChat] WebSocket connection closed: {username}")

    async def create_attachment_from_file(
        self, filename: str, attach_type: str, display_name: str | None = None
    ) -> dict | None:
        kwargs = {
            "attach_type": attach_type,
            "insert_attachment": self.db.insert_attachment,
            "attachments_dir": self.attachments_dir,
            "fallback_dirs": [self.webchat_img_dir],
        }
        if display_name is not None:
            kwargs["display_name"] = display_name
        return await create_attachment_part_from_existing_file(filename, **kwargs)

    def extract_web_search_refs(
        self,
        accumulated_text: str,
        accumulated_parts: list,
    ) -> dict:
        supported = [
            "web_search_baidu",
            "web_search_tavily",
            "web_search_bocha",
            "web_search_brave",
        ]
        web_search_results = {}
        tool_call_parts = [
            p
            for p in accumulated_parts
            if p.get("type") == "tool_call" and p.get("tool_calls")
        ]

        for part in tool_call_parts:
            for tool_call in part["tool_calls"]:
                if tool_call.get("name") not in supported or not tool_call.get(
                    "result"
                ):
                    continue
                try:
                    result_data = json.loads(tool_call["result"])
                    for item in result_data.get("results", []):
                        if idx := item.get("index"):
                            web_search_results[idx] = {
                                "url": item.get("url"),
                                "title": item.get("title"),
                                "snippet": item.get("snippet"),
                            }
                except json.JSONDecodeError, KeyError:
                    pass

        if not web_search_results:
            return {}

        ref_indices = {
            match.strip() for match in re.findall(r"<ref>(.*?)</ref>", accumulated_text)
        }

        used_refs = []
        for ref_index in ref_indices:
            if ref_index not in web_search_results:
                continue
            payload = {"index": ref_index, **web_search_results[ref_index]}
            if favicon := self.preferences.temporary_cache.get("_ws_favicon", {}).get(
                payload["url"]
            ):
                payload["favicon"] = favicon
            used_refs.append(payload)

        return {"used": used_refs} if used_refs else {}

    async def save_bot_message(
        self,
        webchat_conv_id: str,
        message_parts: list[dict],
        agent_stats: dict,
        refs: dict,
        llm_checkpoint_id: str | None = None,
    ):
        new_his = build_bot_history_content(
            message_parts,
            agent_stats=agent_stats,
            refs=refs,
        )

        return await self.platform_history_mgr.insert(
            platform_id="webchat",
            user_id=webchat_conv_id,
            content=new_his,
            sender_id="bot",
            sender_name="bot",
            llm_checkpoint_id=llm_checkpoint_id,
        )

    async def send_chat_payload(
        self,
        session: WebChatSession,
        payload: dict,
        send_json: SendJson,
    ) -> None:
        async with session.ws_send_lock:
            await send_json(payload)

    async def forward_chat_subscription(
        self,
        session: WebChatSession,
        run: WebChatRun,
        send_json: SendJson,
    ) -> None:
        try:
            while True:
                result = await self.webchat_run_coordinator.next_result(run)
                if not result:
                    continue
                await self.send_chat_payload(
                    session, {"ct": "chat", **result}, send_json
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                f"[WebChat] chat subscription forward failed ({run.session_id}): {exc}",
                exc_info=True,
            )
        finally:
            if session.chat_subscriptions.get(run.session_id) == run.request_id:
                session.chat_subscriptions.pop(run.session_id, None)
            session.chat_subscription_tasks.pop(run.session_id, None)

    async def ensure_chat_subscription(
        self,
        session: WebChatSession,
        chat_session_id: str,
        send_json: SendJson,
    ) -> str:
        existing_request_id = session.chat_subscriptions.get(chat_session_id)
        existing_task = session.chat_subscription_tasks.get(chat_session_id)
        if existing_request_id and existing_task and not existing_task.done():
            return existing_request_id

        request_id = f"ws_sub_{uuid.uuid4().hex}"
        run = self.webchat_run_coordinator.create_run(
            session_id=chat_session_id,
            username=session.username,
            request_id=request_id,
            kind="subscription",
        )
        try:
            task = self.webchat_run_coordinator.start_task(
                run,
                self.forward_chat_subscription(session, run, send_json),
                name=f"chat_ws_sub_{chat_session_id}",
            )
        except Exception:
            await self.webchat_run_coordinator.close_run(run)
            session.chat_subscriptions.pop(chat_session_id, None)
            raise

        session.chat_subscriptions[chat_session_id] = request_id
        session.chat_subscription_tasks[chat_session_id] = task
        return request_id

    async def cleanup_chat_subscriptions(self, session: WebChatSession) -> None:
        tasks = [
            *session.chat_subscription_tasks.values(),
            *session.chat_request_tasks.values(),
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for request_id in list(session.chat_subscriptions.values()):
            run = self.webchat_run_coordinator.get_run(request_id)
            if run is not None:
                await self.webchat_run_coordinator.close_run(run)
        session.chat_subscriptions.clear()
        session.chat_subscription_tasks.clear()
        session.chat_request_tasks.clear()
        session.interrupted_chat_requests.clear()

    async def handle_chat_message(
        self,
        session: WebChatSession,
        message: dict,
        send_json: SendJson,
    ) -> None:
        msg_type = message.get("t")
        message_id = str(message.get("message_id") or uuid.uuid4())
        request_metadata = (
            {"message_id": message_id}
            if msg_type == "send" or message.get("message_id")
            else {}
        )
        if await self._handle_chat_control_message(
            session,
            message,
            send_json,
            request_metadata=request_metadata,
        ):
            return

        payload = message.get("message")
        session_id = message.get("session_id") or session.session_id
        selected_provider = message.get("selected_provider")
        selected_model = message.get("selected_model")
        persona_prompt = message.get("persona_prompt")
        show_reasoning = message.get("show_reasoning")
        enable_streaming = message.get("enable_streaming", True)
        raw_step_up_tokens = message.get("webchat_step_up_tokens")
        step_up_tokens = (
            {
                action: token
                for action, token in raw_step_up_tokens.items()
                if action in WEBCHAT_INSTANCE_TOOL_ACTIONS
                and isinstance(token, str)
                and 0 < len(token) <= 512
            }
            if isinstance(raw_step_up_tokens, dict)
            else None
        )

        if not await self._owns_chat_session(session, str(session_id)):
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Authorization denied",
                    "code": "FORBIDDEN",
                    **request_metadata,
                },
                send_json,
            )
            return

        (
            message_parts,
            validation_error,
        ) = await self._build_non_empty_chat_message_parts(payload)
        if validation_error:
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": validation_error,
                    "code": "INVALID_MESSAGE_FORMAT",
                    **request_metadata,
                },
                send_json,
            )
            return
        assert message_parts is not None

        try:
            run = self.webchat_run_coordinator.create_run(
                session_id=session_id,
                username=session.username,
                request_id=message_id,
                kind="chat",
            )
            self.webchat_run_coordinator.bind_task(run)
        except DuplicateWebChatRunError:
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Duplicate active message_id",
                    "code": "INVALID_MESSAGE_FORMAT",
                    **request_metadata,
                },
                send_json,
            )
            return

        llm_checkpoint_id = str(uuid.uuid4())

        pending_bot_message_flusher = None
        try:
            await self.ensure_chat_subscription(session, session_id, send_json)
            principal_payload = self._dashboard_principal_payload(
                session,
                step_up_tokens,
                webchat_session_id=session_id,
            )
            # The opaque proofs are one-time credentials.  Keep them only in
            # the event payload that starts this run; a later WebSocket send
            # must not replay a consumed token from the session cache.
            session.webchat_step_up_tokens = {}
            await self.webchat_run_coordinator.dispatch(
                run,
                {
                    "message": message_parts,
                    "selected_provider": selected_provider,
                    "selected_model": selected_model,
                    "persona_prompt": persona_prompt,
                    "show_reasoning": show_reasoning,
                    "enable_streaming": enable_streaming,
                    "llm_checkpoint_id": llm_checkpoint_id,
                    **principal_payload,
                },
            )

            message_parts_for_storage = strip_message_parts_path_fields(message_parts)
            saved_user_record = await self.platform_history_mgr.insert(
                platform_id="webchat",
                user_id=session_id,
                content={"type": "user", "message": message_parts_for_storage},
                sender_id=session.username,
                sender_name=session.username,
                llm_checkpoint_id=llm_checkpoint_id,
            )
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "type": "user_message_saved",
                    "data": {
                        "id": saved_user_record.id,
                        "created_at": to_utc_isoformat(saved_user_record.created_at),
                        "llm_checkpoint_id": llm_checkpoint_id,
                    },
                    **request_metadata,
                },
                send_json,
            )

            message_accumulator = BotMessageAccumulator()
            agent_stats = {}
            refs = {}

            async def flush_pending_bot_message():
                nonlocal message_accumulator, agent_stats, refs
                if not (message_accumulator.has_content() or refs or agent_stats):
                    return None

                message_parts_to_save = message_accumulator.build_message_parts(
                    include_pending_tool_calls=True
                )
                plain_text = collect_plain_text_from_message_parts(
                    message_parts_to_save
                )
                try:
                    extracted_refs = self.extract_web_search_refs(
                        plain_text,
                        message_parts_to_save,
                    )
                    extracted_refs = merge_webchat_refs(extracted_refs, refs)
                except Exception as exc:
                    logger.exception(
                        f"[WebChat] Failed to extract web search refs: {exc}",
                        exc_info=True,
                    )
                    extracted_refs = refs

                saved_record = await self.save_bot_message(
                    session_id,
                    message_parts_to_save,
                    agent_stats,
                    extracted_refs,
                    llm_checkpoint_id,
                )
                message_accumulator = BotMessageAccumulator()
                agent_stats = {}
                refs = {}
                return saved_record

            pending_bot_message_flusher = flush_pending_bot_message

            async def send_attachment_saved_event(part: dict | None) -> None:
                if not part or not part.get("attachment_id") or not part.get("type"):
                    return

                await self.send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "type": "attachment_saved",
                        "data": {
                            "id": part["attachment_id"],
                            "type": part["type"],
                        },
                        **request_metadata,
                    },
                    send_json,
                )

            while True:
                if (
                    message_id in session.interrupted_chat_requests
                    or run.interrupt_requested.is_set()
                ):
                    session.interrupted_chat_requests.discard(message_id)
                    await flush_pending_bot_message()
                    break

                result = await self.webchat_run_coordinator.next_result(
                    run,
                    wait_seconds=1,
                )

                if not result:
                    continue

                result_text = result.get("data", "")
                result_type = result.get("type")
                streaming = result.get("streaming", False)
                chain_type = result.get("chain_type")
                if chain_type == "agent_stats":
                    try:
                        parsed_agent_stats = json.loads(result_text)
                        agent_stats = parsed_agent_stats
                        await self.send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "agent_stats",
                                "data": parsed_agent_stats,
                                **request_metadata,
                            },
                            send_json,
                        )
                    except Exception:
                        pass
                    continue

                if result_type == "refs":
                    native_refs = result.get("data")
                    if isinstance(native_refs, dict):
                        refs = merge_webchat_refs(refs, native_refs)
                    await self.send_chat_payload(
                        session, {"ct": "chat", **result}, send_json
                    )
                    continue

                outgoing = {"ct": "chat", **result}
                await self.send_chat_payload(session, outgoing, send_json)
                await self._accumulate_chat_result(
                    message_accumulator,
                    result_type,
                    result_text,
                    chain_type,
                    streaming,
                    send_attachment_saved_event,
                )
                should_save = self._should_flush_bot_message(
                    message_accumulator,
                    refs,
                    agent_stats,
                    result_type,
                    chain_type,
                    streaming,
                )

                if should_save:
                    saved_record = await flush_pending_bot_message()
                    if saved_record:
                        await self.send_chat_payload(
                            session,
                            {
                                "ct": "chat",
                                "type": "message_saved",
                                "data": {
                                    "id": saved_record.id,
                                    "created_at": to_utc_isoformat(
                                        saved_record.created_at
                                    ),
                                    "llm_checkpoint_id": llm_checkpoint_id,
                                },
                                **request_metadata,
                            },
                            send_json,
                        )

                if result_type == "end":
                    break

        except Exception as exc:
            logger.error(f"[WebChat] 处理 chat 消息失败: {exc}", exc_info=True)
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "Unable to process the message.",
                    "code": "PROCESSING_ERROR",
                    **request_metadata,
                },
                send_json,
            )
        finally:
            try:
                if pending_bot_message_flusher is not None:
                    await pending_bot_message_flusher()
            except Exception as exc:
                logger.exception(
                    f"[WebChat] Failed to persist pending chat message: {exc}",
                    exc_info=True,
                )
            session.interrupted_chat_requests.discard(message_id)
            await self.webchat_run_coordinator.close_run(run)

    async def _build_non_empty_chat_message_parts(
        self, payload: object
    ) -> tuple[list[dict] | None, str | None]:
        if not isinstance(payload, list):
            return None, "message must be list"
        message_parts = await self.build_chat_message_parts(payload)
        if not webchat_message_parts_have_content(message_parts):
            return None, "Message content is empty"
        return message_parts, None

    async def _accumulate_chat_result(
        self,
        accumulator: BotMessageAccumulator,
        result_type: str | None,
        result_text: object,
        chain_type: str | None,
        streaming: bool,
        send_attachment_saved_event: Callable[[dict | None], Awaitable[None]],
    ) -> None:
        if result_type == "plain":
            accumulator.add_plain(
                str(result_text),
                chain_type=chain_type,
                streaming=streaming,
            )
            return
        attachment = parse_webchat_attachment(result_type, result_text)
        if attachment is None:
            return
        filename, attach_type, display_name = attachment
        if display_name is None:
            part = await self.create_attachment_from_file(filename, attach_type)
        else:
            part = await self.create_attachment_from_file(
                filename,
                attach_type,
                display_name=display_name,
            )
        accumulator.add_attachment(part)
        await send_attachment_saved_event(part)

    @staticmethod
    def _should_flush_bot_message(
        accumulator: BotMessageAccumulator,
        refs: dict,
        agent_stats: dict,
        result_type: str | None,
        chain_type: str | None,
        streaming: bool,
    ) -> bool:
        if result_type == "end":
            return bool(accumulator.has_content() or refs or agent_stats)
        return (streaming and result_type == "complete") or (
            not streaming
            and chain_type not in {"tool_call", "tool_call_result", "agent_stats"}
        )

    async def _handle_chat_control_message(
        self,
        session: WebChatSession,
        message: dict,
        send_json: SendJson,
        *,
        request_metadata: dict[str, str],
    ) -> bool:
        msg_type = message.get("t")

        if msg_type == "mcp_input_response":
            await self._handle_mcp_input_response(session, message, send_json)
            return True

        if msg_type == "bind":
            chat_session_id = message.get("session_id")
            if not isinstance(chat_session_id, str) or not chat_session_id:
                await self.send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "t": "error",
                        "data": "session_id is required",
                        "code": "INVALID_MESSAGE_FORMAT",
                    },
                    send_json,
                )
                return True

            if not await self._owns_chat_session(session, chat_session_id):
                await self.send_chat_payload(
                    session,
                    {
                        "ct": "chat",
                        "t": "error",
                        "data": "Authorization denied",
                        "code": "FORBIDDEN",
                    },
                    send_json,
                )
                return True

            request_id = await self.ensure_chat_subscription(
                session, chat_session_id, send_json
            )
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "type": "session_bound",
                    "session_id": chat_session_id,
                    "message_id": request_id,
                },
                send_json,
            )
            return True

        if msg_type == "interrupt":
            message_id = message.get("message_id")
            if message_id:
                request_id = str(message_id)
                session.interrupted_chat_requests.add(request_id)
                self.webchat_run_coordinator.request_interrupt(request_id)
            else:
                session.interrupted_chat_requests.update(session.chat_request_tasks)
                for request_id in session.chat_request_tasks:
                    self.webchat_run_coordinator.request_interrupt(request_id)
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": "INTERRUPTED",
                    "code": "INTERRUPTED",
                    **request_metadata,
                },
                send_json,
            )
            return True

        if msg_type != "send":
            await self.send_chat_payload(
                session,
                {
                    "ct": "chat",
                    "t": "error",
                    "data": f"Unsupported message type: {msg_type}",
                    "code": "INVALID_MESSAGE_FORMAT",
                },
                send_json,
            )
            return True

        return False

    async def _handle_mcp_input_response(
        self,
        session: WebChatSession,
        message: dict,
        send_json: SendJson,
    ) -> None:
        """Route one elicitation response without entering follow-up capture."""
        coordinator = self.mcp_interaction_coordinator
        request_id = str(message.get("request_id") or message.get("message_id") or "")
        run_id = str(message.get("run_id") or "")
        server_name = str(message.get("server_name") or "")
        origin = str(message.get("unified_msg_origin") or session.session_id)
        action = message.get("action")
        if (
            coordinator is None
            or not request_id
            or not run_id
            or not server_name
            or origin != session.session_id
        ):
            accepted = False
        else:
            accepted = await coordinator.respond(
                MCPInteractionKey(origin, run_id, request_id, server_name),
                session.username,
                str(action),
                message.get("content")
                if isinstance(message.get("content"), dict)
                else None,
            )
        await self.send_chat_payload(
            session,
            {
                "ct": "chat",
                "type": "mcp_input_response",
                "request_id": request_id,
                "message_id": request_id,
                "accepted": accepted,
            },
            send_json,
        )

    async def build_chat_message_parts(self, message: list[dict]) -> list[dict]:
        return await build_webchat_message_parts(
            message,
            get_attachment_by_id=self.db.get_attachment_by_id,
            strict=False,
        )


__all__ = ["WebChatAuthError", "WebChatService", "WebChatSession"]
