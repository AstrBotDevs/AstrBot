import hashlib
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass
from enum import Enum

from astrbot import logger
from astrbot.core.auth.models import (
    WEBCHAT_INSTANCE_TOOL_ACTIONS,
    AuthContext,
    Resource,
    Subject,
)
from astrbot.core.command import (
    CommandEngine,
    CommandError,
    CommandResolution,
    CommandResolutionKind,
    render_diagnostic,
)
from astrbot.core.message.components import At, AtAll, Reply
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_type import MessageType
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.command_group import CommandGroupFilter
from astrbot.core.star.filter.permission import ActionPermissionFilter
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
)
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.quoted_message.onebot_client import OneBotClient

from ..context import PipelineContext
from ..stage import Stage

UNIQUE_SESSION_ID_BUILDERS: dict[str, Callable[[AstrMessageEvent], str | None]] = {
    "aiocqhttp": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "napcat": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "slack": lambda e: f"{e.get_sender_id()}_{e.get_group_id()}",
    "dingtalk": lambda e: e.get_sender_id(),
    "qq_official": lambda e: e.get_sender_id(),
    "qq_official_webhook": lambda e: e.get_sender_id(),
    "lark": lambda e: f"{e.get_sender_id()}%{e.get_group_id()}",
    "misskey": lambda e: f"{e.get_session_id()}_{e.get_sender_id()}",
    "matrix": lambda e: f"{e.get_sender_id()}_{e.get_group_id() or e.get_session_id()}",
}


class WakeReason(Enum):
    PREFIX = "prefix"
    COMMAND = "command"
    MENTION_BOT = "mention_bot"
    MENTION_ALL = "mention_all"
    REPLY_TO_BOT = "reply_to_bot"
    PRIVATE_DEFAULT = "private_default"
    ADAPTER_PRECONFIGURED = "adapter_preconfigured"
    PLUGIN_HANDLER = "plugin_handler"


@dataclass
class WakeDecision:
    should_wake: bool
    reasons: set[WakeReason]


def build_unique_session_id(event: AstrMessageEvent) -> str | None:
    platform = event.get_platform_name()
    builder = UNIQUE_SESSION_ID_BUILDERS.get(platform)
    return builder(event) if builder else None


class WakingCheckStage(Stage):
    """检查是否需要唤醒。唤醒机器人有如下几点条件：

    1. 机器人被 @ 了
    2. 机器人的消息被提到了
    3. 以 wake_prefix 前缀开头，并且消息没有以 At 消息段开头
    4. 插件（Star）的 handler filter 通过
    5. 私聊消息的唤醒由当前平台和会话策略决定，不读取旧管理员配置
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化唤醒检查阶段

        Args:
            ctx (PipelineContext): Message pipeline configuration and catalogs.

        """
        self.ctx = ctx
        if ctx.preferences is None:
            raise RuntimeError("WakingCheckStage requires shared preferences")
        self.session_plugins = SessionPluginManager(ctx.preferences, ctx.plugins)
        self.no_permission_reply = self.ctx.astrbot_config["platform_settings"].get(
            "no_permission_reply",
            True,
        )
        # 私聊是否需要 wake_prefix 才能唤醒机器人
        self.friend_message_needs_wake_prefix = self.ctx.astrbot_config[
            "platform_settings"
        ].get("friend_message_needs_wake_prefix", False)
        # 是否忽略机器人自己发送的消息
        self.ignore_bot_self_message = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_bot_self_message",
            False,
        )
        self.ignore_at_all = self.ctx.astrbot_config["platform_settings"].get(
            "ignore_at_all",
            False,
        )
        platform_settings = self.ctx.astrbot_config.get("platform_settings", {})
        self.unique_session = platform_settings.get("unique_session", False)
        group_wake_policy = platform_settings.get("group_wake_policy", {})
        self.group_wake_mention_bot = bool(group_wake_policy.get("mention_bot", False))
        self.group_wake_reply_to_bot = bool(
            group_wake_policy.get("reply_to_bot", False)
        )
        enabled_plugins = self.ctx.astrbot_config.get("plugin_set", ["*"])
        plugin_names = None if enabled_plugins == ["*"] else enabled_plugins
        self.command_catalog = ctx.plugin_catalog.get_command_catalog(
            ctx.astrbot_config_id,
            plugin_names,
        )

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> None | AsyncGenerator[None]:
        self._apply_unique_session(event)
        await self._attach_authorization(event)
        if self._is_bot_self_message(event):
            event.stop_event()
            return

        event.message_str = event.message_str.strip(" \t")
        wake_decision = await self._detect_wake(event)
        event.set_extra(
            "wake_reasons", {reason.value for reason in wake_decision.reasons}
        )
        (
            activated_handlers,
            handlers_parsed_params,
            permission_denied,
        ) = await self._collect_activated_handlers(event)
        if permission_denied:
            return

        activated_handlers = await self.session_plugins.filter_handlers_by_session(
            event,
            activated_handlers,
        )
        event.set_extra("activated_handlers", activated_handlers)
        event.set_extra("handlers_parsed_params", handlers_parsed_params)
        if not (wake_decision.should_wake or event.is_wake):
            event.stop_event()

    def _apply_unique_session(self, event: AstrMessageEvent) -> None:
        onebot_post_type = event.get_extra("onebot_post_type")
        should_keep_group_session = onebot_post_type in {"notice", "request"}
        if (
            self.unique_session
            and event.message_obj.type == MessageType.GROUP_MESSAGE
            and not should_keep_group_session
        ):
            sid = build_unique_session_id(event)
            if sid:
                event.session_id = sid

    def _is_bot_self_message(self, event: AstrMessageEvent) -> bool:
        return self.ignore_bot_self_message and (
            event.get_self_id() == event.get_sender_id()
        )

    async def _attach_authorization(self, event: AstrMessageEvent) -> None:
        """Normalize the inbound actor and explicit config-scoped resource."""

        config_id = self.ctx.astrbot_config_id
        scopes: tuple[str, ...] = ()
        principal_subject_id: str | None = None
        dashboard_session_id: str | None = None
        auth_strength = "none"
        webchat_step_up_tokens: dict[str, str] = {}
        api_key_principal = event.get_extra("_api_key_principal")
        dashboard_principal = event.get_extra("_dashboard_principal")
        if event.get_platform_name() == "webchat" and isinstance(
            api_key_principal, dict
        ):
            key_id = api_key_principal.get("key_id")
            scopes = api_key_principal.get("scopes", ())
            if isinstance(key_id, str) and isinstance(scopes, list | tuple):
                subject = Subject.api_key(key_id)
                authenticated = True
                source = "api_key"
                principal_subject_id = subject.id
            else:
                subject = Subject.guest(
                    f"webchat-{hashlib.sha256(event.get_sender_id().encode()).hexdigest()[:24]}"
                )
                authenticated = False
                source = "webchat"
                scopes = ()
        elif event.get_platform_name() == "webchat" and isinstance(
            dashboard_principal, dict
        ):
            account_id = dashboard_principal.get("account_id")
            session_id = dashboard_principal.get("sid")
            principal_username = dashboard_principal.get("username")
            if (
                isinstance(account_id, str)
                and isinstance(session_id, str)
                and isinstance(principal_username, str)
                and principal_username == event.get_sender_id()
            ):
                principal_auth_strength = dashboard_principal.get("auth_strength")
                if principal_auth_strength in {"none", "password", "totp", "step_up"}:
                    auth_strength = principal_auth_strength
                subject = Subject.dashboard_account(account_id, principal_username)
                authenticated = True
                source = "webchat"
                principal_subject_id = subject.id
                dashboard_session_id = session_id
                raw_step_up_tokens = dashboard_principal.get("step_up_tokens")
                if isinstance(raw_step_up_tokens, dict):
                    webchat_step_up_tokens = {
                        action: token
                        for action, token in raw_step_up_tokens.items()
                        if action in WEBCHAT_INSTANCE_TOOL_ACTIONS
                        and isinstance(token, str)
                        and 0 < len(token) <= 512
                    }
                logger.debug(
                    "WebChat Dashboard principal attached: account=%s sid_present=%s proof_actions=%s",
                    account_id,
                    bool(session_id),
                    tuple(sorted(webchat_step_up_tokens)),
                )
            else:
                subject = Subject.guest(
                    f"webchat-{hashlib.sha256(event.get_sender_id().encode()).hexdigest()[:24]}"
                )
                authenticated = False
                source = "webchat"
        elif event.get_platform_name() == "webchat":
            # WebChat's username is caller-declared compatibility data, not a
            # principal. A trusted Dashboard/API principal is attached later.
            subject = Subject.guest(
                f"webchat-{hashlib.sha256(event.get_sender_id().encode()).hexdigest()[:24]}"
            )
            authenticated = False
            source = "webchat"
            scopes = ()
        else:
            platform_instance = getattr(event, "get_platform_id", None)
            platform_instance = (
                platform_instance()
                if callable(platform_instance)
                else event.get_platform_name()
            )
            subject = Subject.im(
                platform_instance=platform_instance,
                bot_account_id=event.get_self_id() or "default",
                sender_id=event.get_sender_id() or "unknown",
                display_name=(
                    event.get_sender_name()
                    if hasattr(event, "get_sender_name")
                    else None
                )
                or None,
            )
            authenticated = True
            source = "im"
        umo = getattr(event, "unified_msg_origin", None)
        if not isinstance(umo, str) or not umo:
            umo = str(getattr(event, "get_session_id", lambda: "unknown")())
            if ":" not in umo:
                umo = f"{event.get_platform_name()}:FriendMessage:{umo or 'unknown'}"
        parent_session_id = event.get_extra("webchat_parent_session_id")
        if (
            event.get_platform_name() == "webchat"
            and isinstance(parent_session_id, str)
            and parent_session_id
        ):
            # Thread runs keep their own history/session id, but a WebChat
            # step-up proof is bound to the parent conversation that enabled
            # the tools.  This value is injected by ChatService from the
            # verified thread row and is never accepted from the client.
            umo = f"webchat:FriendMessage:webchat!{event.get_sender_id()}!{parent_session_id}"
        resource = Resource.session(config_id, umo)
        message_type = getattr(event, "get_message_type", None)
        message_type = message_type().value if callable(message_type) else "friend"
        context = AuthContext(
            subject=subject,
            source=source,
            config_id=config_id,
            platform=event.get_platform_name(),
            message_type=message_type,
            platform_member_role=getattr(event, "platform_member_role", "unknown"),
            platform_role_source=getattr(event, "platform_role_source", "none"),
            platform_role_expires_at=getattr(event, "platform_role_expires_at", None),
            authenticated=authenticated,
            auth_strength=auth_strength,
            origin_session_resource_id=resource.id,
            caller_declared_username=(
                event.get_sender_id() if source == "webchat" else None
            ),
            api_scopes=tuple(scopes) if isinstance(scopes, (list, tuple)) else (),
            principal_subject_id=principal_subject_id,
            metadata=(
                {
                    "dashboard_session_id": dashboard_session_id,
                    "webchat_step_up_tokens": webchat_step_up_tokens,
                }
                if dashboard_session_id is not None
                else {}
            ),
        )
        attach_authorization = getattr(event, "attach_authorization", None)
        if callable(attach_authorization):
            attach_authorization(subject=subject, resource=resource, context=context)
        else:
            # Lightweight test/adaptor events may not expose the full event API;
            # retain the normalized values as extras without restoring legacy
            # role-based authorization semantics.
            event.set_extra("auth_subject", subject)
            event.set_extra("auth_resource", resource)
            event.set_extra("auth_context", context)
        event.set_extra("config_id", config_id)
        authorization = getattr(self.ctx, "authorization", None)
        platform_member_role = getattr(event, "platform_member_role", "unknown")
        if authorization is not None and platform_member_role in {
            "owner",
            "admin",
            "member",
        }:
            try:
                await authorization.record_platform_membership(
                    subject=subject,
                    resource=resource,
                    platform_instance=getattr(
                        event, "get_platform_id", event.get_platform_name
                    )(),
                    platform_role=platform_member_role,
                    source=getattr(event, "platform_role_source", "none"),
                    metadata={
                        "message_type": (
                            event.get_message_type().value
                            if callable(getattr(event, "get_message_type", None))
                            else "friend"
                        )
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Platform membership fact was not persisted: %s",
                    safe_error("", exc),
                )

    async def _detect_wake(self, event: AstrMessageEvent) -> WakeDecision:
        if event.is_wake:
            return WakeDecision(True, {WakeReason.ADAPTER_PRECONFIGURED})

        wake_prefixes = self.ctx.astrbot_config["wake_prefix"]
        messages = event.get_messages()
        skip_private_wake = bool(event.get_extra("skip_private_wake", False))
        for wake_prefix in wake_prefixes:
            if event.message_str.startswith(wake_prefix):
                if (
                    not event.is_private_chat()
                    and messages
                    and isinstance(messages[0], At)
                    and str(messages[0].qq) != str(event.get_self_id())
                    and str(messages[0].qq) != "all"
                ):
                    # 如果是群聊，且第一个消息段是 At 消息，但不是 At 机器人或 At 全体成员，则不唤醒
                    break
                event.is_at_or_wake_command = True
                event.is_wake = True
                event.message_str = event.message_str[len(wake_prefix) :].strip(" \t")
                return WakeDecision(True, {WakeReason.PREFIX})

        unresolved_replies: list[Reply] = []
        for message in messages:
            reply_sender_id = self._reply_sender_id(message)
            if reason := self._message_wakes_event(message, event, reply_sender_id):
                event.is_wake = True
                event.is_at_or_wake_command = True
                return WakeDecision(True, {reason})
            if isinstance(message, Reply) and not reply_sender_id:
                unresolved_replies.append(message)
        if await self._unresolved_reply_wakes_event(event, unresolved_replies):
            return WakeDecision(True, {WakeReason.REPLY_TO_BOT})
        if (
            event.is_private_chat()
            and not skip_private_wake
            and (
                not self.friend_message_needs_wake_prefix
                or event.get_platform_name() == "webchat"
            )
        ):
            event.is_wake = True
            event.is_at_or_wake_command = True
            return WakeDecision(True, {WakeReason.PRIVATE_DEFAULT})
        return WakeDecision(False, set())

    @staticmethod
    def _reply_sender_id(message: object) -> str:
        if isinstance(message, Reply) and message.sender_id not in (None, "", 0, "0"):
            return str(message.sender_id)
        return ""

    def _message_wakes_event(
        self, message: object, event: AstrMessageEvent, reply_sender_id: str
    ) -> WakeReason | None:
        if (
            isinstance(message, At)
            and str(message.qq) == str(event.get_self_id())
            and self.group_wake_mention_bot
        ):
            return WakeReason.MENTION_BOT
        if isinstance(message, AtAll) and not self.ignore_at_all:
            return WakeReason.MENTION_ALL
        if (
            isinstance(message, Reply)
            and reply_sender_id == str(event.get_self_id())
            and self.group_wake_reply_to_bot
        ):
            return WakeReason.REPLY_TO_BOT
        return None

    async def _unresolved_reply_wakes_event(
        self, event: AstrMessageEvent, replies: list[Reply]
    ) -> bool:
        if not replies:
            return False
        onebot_client = OneBotClient(event)
        for reply in replies:
            resolved_sender_id = await onebot_client.get_msg_sender_id(reply.id)
            if not resolved_sender_id:
                continue
            reply.sender_id = resolved_sender_id
            if (
                resolved_sender_id == str(event.get_self_id())
                and self.group_wake_reply_to_bot
            ):
                event.is_wake = True
                event.is_at_or_wake_command = True
                return True
        return False

    async def _collect_activated_handlers(
        self, event: AstrMessageEvent
    ) -> tuple[list, dict, bool]:
        activated_handlers = []
        handlers_parsed_params = {}

        enabled_plugins_name = self.ctx.astrbot_config.get("plugin_set", ["*"])
        event.plugins_name = (
            None if enabled_plugins_name == ["*"] else enabled_plugins_name
        )
        logger.debug(f"enabled_plugins_name: {enabled_plugins_name}")

        handlers = self.ctx.handlers.get_handlers_by_event_type(
            EventType.AdapterMessageEvent,
            plugins_name=event.plugins_name,
        )
        engine = self._command_engine()
        group_handlers = {
            id(filter_ref): (filter_ref, handler)
            for handler in handlers
            for filter_ref in handler.event_filters
            if isinstance(filter_ref, CommandGroupFilter)
        }
        group_gate_cache: dict[int, tuple[bool, bool]] = {}
        catalog_resolution = (
            engine.catalog.resolve(event.message_str)
            if event.is_at_or_wake_command
            else None
        )
        if catalog_resolution and catalog_resolution.kind in {
            CommandResolutionKind.INCOMPLETE_GROUP,
            CommandResolutionKind.UNKNOWN_SUBCOMMAND,
        }:
            relevant_groups = self._groups_for_resolution(
                group_handlers,
                catalog_resolution,
            )
            any_allowed = not relevant_groups
            for group_filter in relevant_groups:
                allowed, fatal = await self._check_group_filter_chain(
                    event,
                    group_filter,
                    group_handlers,
                    group_gate_cache,
                )
                if fatal:
                    return activated_handlers, handlers_parsed_params, True
                any_allowed = any_allowed or allowed
            if not any_allowed:
                return activated_handlers, handlers_parsed_params, False
        try:
            resolved_command = (
                engine.resolve(event.message_str)
                if event.is_at_or_wake_command
                else None
            )
        except CommandError as exc:
            logger.info("Command input rejected: %s", exc.diagnostic.code.value)
            await event.send(
                MessageEventResult()
                .message(render_diagnostic(exc.diagnostic, event.message_str, "zh-CN"))
                .use_markdown(False)
            )
            event.stop_event()
            return activated_handlers, handlers_parsed_params, True

        matched_entries = (
            resolved_command.resolution.entries
            if resolved_command
            and resolved_command.resolution.kind is CommandResolutionKind.MATCHED
            else ()
        )
        matched_filter_ids = {
            id(entry.filter_ref) for entry in matched_entries if entry.filter_ref
        }
        event.set_extra(
            "command_handler_ids",
            tuple(entry.handler_id for entry in matched_entries),
        )
        entries_by_filter = {
            id(entry.filter_ref): entry
            for entry in matched_entries
            if entry.filter_ref is not None
        }

        for handler in handlers:
            # filter 需满足 AND 逻辑关系
            passed = True
            bound_params: dict | None = None
            permission_not_pass = False
            permission_filter_raise_error = False
            if len(handler.event_filters) == 0:
                continue

            for filter in handler.event_filters:
                try:
                    if isinstance(filter, CommandGroupFilter):
                        passed = False
                        break
                    if isinstance(filter, CommandFilter):
                        if id(filter) not in matched_filter_ids:
                            passed = False
                            break
                        group_allowed, fatal = await self._check_parent_group_filters(
                            event,
                            filter,
                            group_handlers,
                            group_gate_cache,
                        )
                        if fatal:
                            return activated_handlers, handlers_parsed_params, True
                        if not group_allowed:
                            passed = False
                            break
                        if not filter.filter(event, self.ctx.astrbot_config):
                            passed = False
                            break
                        assert resolved_command is not None
                        bound = engine.bind(
                            entries_by_filter[id(filter)], resolved_command
                        )
                        bound_params = dict(bound.values)
                    elif isinstance(filter, ActionPermissionFilter):
                        if not await self._permission_filter_allowed(event, filter):
                            permission_not_pass = True
                            permission_filter_raise_error = filter.raise_error
                    elif not filter.filter(event, self.ctx.astrbot_config):
                        passed = False
                        break
                except CommandError as exc:
                    logger.info("Command input rejected: %s", exc.diagnostic.code.value)
                    await event.send(
                        MessageEventResult()
                        .message(
                            render_diagnostic(
                                exc.diagnostic, event.message_str, "zh-CN"
                            )
                        )
                        .use_markdown(False)
                    )
                    event.stop_event()
                    return activated_handlers, handlers_parsed_params, True
                except Exception as exc:
                    logger.error(
                        "Command handler filter failed: %s", safe_error("", exc)
                    )
                    await event.send(
                        MessageEventResult()
                        .message("指令处理失败，请稍后重试。")
                        .use_markdown(False),
                    )
                    event.stop_event()
                    passed = False
                    break
            if passed:
                if permission_not_pass:
                    if not permission_filter_raise_error:
                        # 跳过
                        continue
                    if self.no_permission_reply:
                        await event.send(
                            MessageChain().message(
                                f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。通过 /session info 获取 ID 并请管理员添加。",
                            ),
                        )
                    plugin = self.ctx.plugins.get_by_module(handler.handler_module_path)
                    logger.info(
                        "触发 %s 时, 用户(ID=%s) 权限不足。",
                        plugin.name if plugin else "unknown plugin",
                        event.get_sender_id(),
                    )
                    event.stop_event()
                    return activated_handlers, handlers_parsed_params, True

                event.is_wake = True
                wake_reasons = event.get_extra("wake_reasons", default=set())
                if not isinstance(wake_reasons, set):
                    wake_reasons = set(wake_reasons)
                wake_reasons.add(WakeReason.PLUGIN_HANDLER.value)
                event.set_extra("wake_reasons", wake_reasons)

                activated_handlers.append(handler)
                if bound_params is not None:
                    handlers_parsed_params[handler.handler_full_name] = bound_params
        return activated_handlers, handlers_parsed_params, False

    @staticmethod
    def _groups_for_resolution(
        group_handlers: dict[int, tuple[CommandGroupFilter, StarHandlerMetadata]],
        resolution: CommandResolution,
    ) -> list[CommandGroupFilter]:
        group_path = resolution.group_path
        return [
            group_filter
            for group_filter, _handler in group_handlers.values()
            if group_path
            in {
                tuple(name.split(" "))
                for name in group_filter.get_complete_command_names()
            }
        ]

    async def _check_parent_group_filters(
        self,
        event: AstrMessageEvent,
        command_filter: CommandFilter,
        group_handlers: dict[int, tuple[CommandGroupFilter, StarHandlerMetadata]],
        cache: dict[int, tuple[bool, bool]],
    ) -> tuple[bool, bool]:
        groups: list[CommandGroupFilter] = []
        group = command_filter.parent_group
        while group is not None:
            groups.append(group)
            group = group.parent_group

        for group_filter in reversed(groups):
            allowed, fatal = await self._check_group_filter(
                event,
                group_filter,
                group_handlers,
                cache,
            )
            if fatal or not allowed:
                return allowed, fatal
        return True, False

    async def _check_group_filter_chain(
        self,
        event: AstrMessageEvent,
        group_filter: CommandGroupFilter,
        group_handlers: dict[int, tuple[CommandGroupFilter, StarHandlerMetadata]],
        cache: dict[int, tuple[bool, bool]],
    ) -> tuple[bool, bool]:
        groups: list[CommandGroupFilter] = []
        group: CommandGroupFilter | None = group_filter
        while group is not None:
            groups.append(group)
            group = group.parent_group

        for current in reversed(groups):
            allowed, fatal = await self._check_group_filter(
                event,
                current,
                group_handlers,
                cache,
            )
            if fatal or not allowed:
                return allowed, fatal
        return True, False

    async def _check_group_filter(
        self,
        event: AstrMessageEvent,
        group_filter: CommandGroupFilter,
        group_handlers: dict[int, tuple[CommandGroupFilter, StarHandlerMetadata]],
        cache: dict[int, tuple[bool, bool]],
    ) -> tuple[bool, bool]:
        cached = cache.get(id(group_filter))
        if cached is not None:
            return cached

        handler_entry = group_handlers.get(id(group_filter))
        handler = handler_entry[1] if handler_entry else None
        try:
            if not group_filter.custom_filter_ok(event, self.ctx.astrbot_config):
                cache[id(group_filter)] = (False, False)
                return False, False

            permission_not_pass = False
            permission_filter_raise_error = False
            if handler is not None:
                for filter_ref in handler.event_filters:
                    if isinstance(filter_ref, CommandGroupFilter):
                        continue
                    if isinstance(filter_ref, ActionPermissionFilter):
                        if not await self._permission_filter_allowed(event, filter_ref):
                            permission_not_pass = True
                            permission_filter_raise_error = filter_ref.raise_error
                    elif not filter_ref.filter(event, self.ctx.astrbot_config):
                        cache[id(group_filter)] = (False, False)
                        return False, False

            if permission_not_pass:
                if not permission_filter_raise_error:
                    cache[id(group_filter)] = (False, False)
                    return False, False
                await self._send_permission_denied(event, handler)
                cache[id(group_filter)] = (False, True)
                return False, True
        except Exception as exc:
            await self._send_filter_error(event, handler, exc)
            cache[id(group_filter)] = (False, True)
            return False, True

        cache[id(group_filter)] = (True, False)
        return True, False

    async def _permission_filter_allowed(
        self,
        event: AstrMessageEvent,
        filter_ref: ActionPermissionFilter,
    ) -> bool:
        authorization = getattr(self.ctx, "authorization", None)
        if (
            authorization is None
            or event.subject is None
            or event.resource is None
            or event.auth_context is None
        ):
            return False
        return (
            await authorization.authorize(
                event.subject,
                filter_ref.action,
                event.resource,
                event.auth_context,
            )
        ).allowed

    async def _send_permission_denied(
        self,
        event: AstrMessageEvent,
        handler: StarHandlerMetadata | None,
    ) -> None:
        if self.no_permission_reply:
            await event.send(
                MessageChain().message(
                    f"您(ID: {event.get_sender_id()})的权限不足以使用此指令。"
                    "通过 /session info 获取 ID 并请管理员添加。",
                ),
            )
        plugin = (
            self.ctx.plugins.get_by_module(handler.handler_module_path)
            if handler
            else None
        )
        logger.info(
            "触发 %s 时, 用户(ID=%s) 权限不足。",
            plugin.name if plugin else "unknown plugin",
            event.get_sender_id(),
        )
        event.stop_event()

    async def _send_filter_error(
        self,
        event: AstrMessageEvent,
        handler: StarHandlerMetadata | None,
        exc: Exception,
    ) -> None:
        plugin = (
            self.ctx.plugins.get_by_module(handler.handler_module_path)
            if handler
            else None
        )
        plugin_name = plugin.name if plugin else "unknown plugin"
        logger.error(
            "Command group filter failed for %s: %s",
            plugin_name,
            safe_error("", exc),
        )
        await event.send(
            MessageEventResult()
            .message("指令处理失败，请稍后重试。")
            .use_markdown(False),
        )
        event.stop_event()

    def _command_engine(self) -> CommandEngine:
        return CommandEngine(self.command_catalog.snapshot)
