from quart import request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core import logger, sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ConversationV2, Preference
from astrbot.core.provider.entities import ProviderType

from .route import Response, Route, RouteContext

AVAILABLE_SESSION_RULE_KEYS = [
    "session_service_config",
    "session_plugin_config",
    "kb_config",
    f"provider_perf_{ProviderType.CHAT_COMPLETION.value}",
    f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}",
    f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}",
]


class SessionManagementRoute(Route):
    def __init__(
        self,
        context: RouteContext,
        db_helper: BaseDatabase,
        core_lifecycle: AstrBotCoreLifecycle,
    ) -> None:
        super().__init__(context)
        self.db_helper = db_helper
        self.routes = {
            "/session/list-rule": ("GET", self.list_session_rule),
            "/session/update-rule": ("POST", self.update_session_rule),
            "/session/delete-rule": ("POST", self.delete_session_rule),
            "/session/batch-delete-rule": ("POST", self.batch_delete_session_rule),
            "/session/active-umos": ("GET", self.list_umos),
            "/session/list-all-with-status": ("GET", self.list_all_umos_with_status),
            "/session/batch-update-service": ("POST", self.batch_update_service),
            "/session/batch-update-provider": ("POST", self.batch_update_provider),
            # 分组管理 API
            "/session/groups": ("GET", self.list_groups),
            "/session/group/create": ("POST", self.create_group),
            "/session/group/update": ("POST", self.update_group),
            "/session/group/delete": ("POST", self.delete_group),
        }
        self.conv_mgr = core_lifecycle.conversation_manager
        self.core_lifecycle = core_lifecycle
        self.register_routes()

    async def _get_umo_rules(
        self, page: int = 1, page_size: int = 10, search: str = ""
    ) -> tuple[dict, int]:
        """获取所有带有自定义规则的 umo 及其规则内容（支持分页和搜索）。

        如果某个 umo 在 preference 中有以下字段，则表示有自定义规则：

        1. session_service_config (包含了 是否启用这个umo, 这个umo是否启用 llm, 这个umo是否启用tts, umo自定义名称。)
        2. session_plugin_config (包含了 这个 umo 的 plugin set)
        3. provider_perf_{ProviderType.value} (包含了这个 umo 所选择使用的 provider 信息)
        4. kb_config (包含了这个 umo 的知识库相关配置)

        Args:
            page: 页码，从 1 开始
            page_size: 每页数量
            search: 搜索关键词，匹配 umo 或 custom_name

        Returns:
            tuple[dict, int]: (umo_rules, total) - 分页后的 umo 规则和总数
        """
        umo_rules = {}
        async with self.db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(Preference).where(
                    col(Preference.scope) == "umo",
                    col(Preference.key).in_(AVAILABLE_SESSION_RULE_KEYS),
                )
            )
            prefs = result.scalars().all()
            for pref in prefs:
                umo_id = pref.scope_id
                if umo_id not in umo_rules:
                    umo_rules[umo_id] = {}
                if pref.key == "session_plugin_config" and umo_id in pref.value["val"]:
                    umo_rules[umo_id][pref.key] = pref.value["val"][umo_id]
                else:
                    umo_rules[umo_id][pref.key] = pref.value["val"]

        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_rules = {}
            for umo_id, rules in umo_rules.items():
                # 匹配 umo
                if search_lower in umo_id.lower():
                    filtered_rules[umo_id] = rules
                    continue
                # 匹配 custom_name
                svc_config = rules.get("session_service_config", {})
                custom_name = svc_config.get("custom_name", "") if svc_config else ""
                if custom_name and search_lower in custom_name.lower():
                    filtered_rules[umo_id] = rules
            umo_rules = filtered_rules

        # 获取总数
        total = len(umo_rules)

        # 分页处理
        all_umo_ids = list(umo_rules.keys())
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_umo_ids = all_umo_ids[start_idx:end_idx]

        # 只返回分页后的数据
        paginated_rules = {umo_id: umo_rules[umo_id] for umo_id in paginated_umo_ids}

        return paginated_rules, total

    async def list_session_rule(self):
        """获取所有自定义的规则（支持分页和搜索）

        返回已配置规则的 umo 列表及其规则内容，以及可用的 personas 和 providers

        Query 参数:
            page: 页码，默认为 1
            page_size: 每页数量，默认为 10
            search: 搜索关键词，匹配 umo 或 custom_name
        """
        try:
            # 获取分页和搜索参数
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 10, type=int)
            search = request.args.get("search", "", type=str).strip()

            # 参数校验
            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 10
            if page_size > 100:
                page_size = 100

            umo_rules, total = await self._get_umo_rules(
                page=page, page_size=page_size, search=search
            )

            # 构建规则列表
            rules_list = []
            for umo, rules in umo_rules.items():
                rule_info = {
                    "umo": umo,
                    "rules": rules,
                }
                # 解析 umo 格式: 平台:消息类型:会话ID
                parts = umo.split(":")
                if len(parts) >= 3:
                    rule_info["platform"] = parts[0]
                    rule_info["message_type"] = parts[1]
                    rule_info["session_id"] = parts[2]
                rules_list.append(rule_info)

            # 获取可用的 providers 和 personas
            provider_manager = self.core_lifecycle.provider_manager
            persona_mgr = self.core_lifecycle.persona_mgr

            available_personas = [
                {"name": p["name"], "prompt": p.get("prompt", "")}
                for p in persona_mgr.personas_v3
            ]

            available_chat_providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                }
                for p in provider_manager.provider_insts
            ]

            available_stt_providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                }
                for p in provider_manager.stt_provider_insts
            ]

            available_tts_providers = [
                {
                    "id": p.meta().id,
                    "name": p.meta().id,
                    "model": p.meta().model,
                }
                for p in provider_manager.tts_provider_insts
            ]

            # 获取可用的插件列表（排除 reserved 的系统插件）
            plugin_manager = self.core_lifecycle.plugin_manager
            available_plugins = [
                {
                    "name": p.name,
                    "display_name": p.display_name or p.name,
                    "desc": p.desc,
                }
                for p in plugin_manager.context.get_all_stars()
                if not p.reserved and p.name
            ]

            # 获取可用的知识库列表
            available_kbs = []
            kb_manager = self.core_lifecycle.kb_manager
            if kb_manager:
                try:
                    kbs = await kb_manager.list_kbs()
                    available_kbs = [
                        {
                            "kb_id": kb.kb_id,
                            "kb_name": kb.kb_name,
                            "emoji": kb.emoji,
                        }
                        for kb in kbs
                    ]
                except Exception as e:
                    logger.warning(f"获取知识库列表失败: {e!s}")

            return (
                Response()
                .ok(
                    {
                        "rules": rules_list,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "available_personas": available_personas,
                        "available_chat_providers": available_chat_providers,
                        "available_stt_providers": available_stt_providers,
                        "available_tts_providers": available_tts_providers,
                        "available_plugins": available_plugins,
                        "available_kbs": available_kbs,
                        "available_rule_keys": AVAILABLE_SESSION_RULE_KEYS,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取规则列表失败: {e!s}")
            return Response().error(f"获取规则列表失败: {e!s}").__dict__

    async def update_session_rule(self):
        """更新某个 umo 的自定义规则

        请求体:
        {
            "umo": "平台:消息类型:会话ID",
            "rule_key": "session_service_config" | "session_plugin_config" | "kb_config" | "provider_perf_xxx",
            "rule_value": {...}  // 规则值，具体结构根据 rule_key 不同而不同
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo")
            rule_key = data.get("rule_key")
            rule_value = data.get("rule_value")

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__
            if not rule_key:
                return Response().error("缺少必要参数: rule_key").__dict__
            if rule_key not in AVAILABLE_SESSION_RULE_KEYS:
                return Response().error(f"不支持的规则键: {rule_key}").__dict__

            if rule_key == "session_plugin_config":
                rule_value = {
                    umo: rule_value,
                }

            # 使用 shared preferences 更新规则
            await sp.session_put(umo, rule_key, rule_value)

            return (
                Response()
                .ok({"message": f"规则 {rule_key} 已更新", "umo": umo})
                .__dict__
            )
        except Exception as e:
            logger.error(f"更新会话规则失败: {e!s}")
            return Response().error(f"更新会话规则失败: {e!s}").__dict__

    async def delete_session_rule(self):
        """删除某个 umo 的自定义规则

        请求体:
        {
            "umo": "平台:消息类型:会话ID",
            "rule_key": "session_service_config" | "session_plugin_config" | ... (可选，不传则删除所有规则)
        }
        """
        try:
            data = await request.get_json()
            umo = data.get("umo")
            rule_key = data.get("rule_key")

            if not umo:
                return Response().error("缺少必要参数: umo").__dict__

            if rule_key:
                # 删除单个规则
                if rule_key not in AVAILABLE_SESSION_RULE_KEYS:
                    return Response().error(f"不支持的规则键: {rule_key}").__dict__
                await sp.session_remove(umo, rule_key)
                return (
                    Response()
                    .ok({"message": f"规则 {rule_key} 已删除", "umo": umo})
                    .__dict__
                )
            else:
                # 删除该 umo 的所有规则
                await sp.clear_async("umo", umo)
                return Response().ok({"message": "所有规则已删除", "umo": umo}).__dict__
        except Exception as e:
            logger.error(f"删除会话规则失败: {e!s}")
            return Response().error(f"删除会话规则失败: {e!s}").__dict__

    async def batch_delete_session_rule(self):
        """批量删除多个 umo 的自定义规则

        请求体:
        {
            "umos": ["平台:消息类型:会话ID", ...]  // umo 列表
        }
        """
        try:
            data = await request.get_json()
            umos = data.get("umos", [])

            if not umos:
                return Response().error("缺少必要参数: umos").__dict__

            if not isinstance(umos, list):
                return Response().error("参数 umos 必须是数组").__dict__

            # 批量删除
            deleted_count = 0
            failed_umos = []
            for umo in umos:
                try:
                    await sp.clear_async("umo", umo)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"删除 umo {umo} 的规则失败: {e!s}")
                    failed_umos.append(umo)

            if failed_umos:
                return (
                    Response()
                    .ok(
                        {
                            "message": f"已删除 {deleted_count} 条规则，{len(failed_umos)} 条删除失败",
                            "deleted_count": deleted_count,
                            "failed_umos": failed_umos,
                        }
                    )
                    .__dict__
                )
            else:
                return (
                    Response()
                    .ok(
                        {
                            "message": f"已删除 {deleted_count} 条规则",
                            "deleted_count": deleted_count,
                        }
                    )
                    .__dict__
                )
        except Exception as e:
            logger.error(f"批量删除会话规则失败: {e!s}")
            return Response().error(f"批量删除会话规则失败: {e!s}").__dict__

    async def list_umos(self):
        """列出所有有对话记录的 umo，从 Conversations 表中找

        仅返回 umo 字符串列表，用于用户在创建规则时选择 umo
        """
        try:
            # 从 Conversation 表获取所有 distinct user_id (即 umo)
            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(ConversationV2.user_id)
                    .distinct()
                    .order_by(ConversationV2.user_id)
                )
                umos = [row[0] for row in result.fetchall()]

            return Response().ok({"umos": umos}).__dict__
        except Exception as e:
            logger.error(f"获取 UMO 列表失败: {e!s}")
            return Response().error(f"获取 UMO 列表失败: {e!s}").__dict__

    async def list_all_umos_with_status(self):
        """获取所有有对话记录的 UMO 及其服务状态（支持分页、搜索、筛选）

        Query 参数:
            page: 页码，默认为 1
            page_size: 每页数量，默认为 20
            search: 搜索关键词
            message_type: 筛选消息类型 (group/private/all)
            platform: 筛选平台
        """
        try:
            page = request.args.get("page", 1, type=int)
            page_size = request.args.get("page_size", 20, type=int)
            search = request.args.get("search", "", type=str).strip()
            message_type = request.args.get("message_type", "all", type=str)
            platform = request.args.get("platform", "", type=str)

            if page < 1:
                page = 1
            if page_size < 1:
                page_size = 20
            if page_size > 100:
                page_size = 100

            # 从 Conversation 表获取所有 distinct user_id (即 umo)
            async with self.db_helper.get_db() as session:
                session: AsyncSession
                result = await session.execute(
                    select(ConversationV2.user_id)
                    .distinct()
                    .order_by(ConversationV2.user_id)
                )
                all_umos = [row[0] for row in result.fetchall()]

            # 获取所有 umo 的规则配置
            umo_rules, _ = await self._get_umo_rules(page=1, page_size=99999, search="")

            # 构建带状态的 umo 列表
            umos_with_status = []
            for umo in all_umos:
                parts = umo.split(":")
                umo_platform = parts[0] if len(parts) >= 1 else "unknown"
                umo_message_type = parts[1] if len(parts) >= 2 else "unknown"
                umo_session_id = parts[2] if len(parts) >= 3 else umo

                # 筛选消息类型
                if message_type != "all":
                    if message_type == "group" and umo_message_type not in [
                        "group",
                        "GroupMessage",
                    ]:
                        continue
                    if message_type == "private" and umo_message_type not in [
                        "private",
                        "FriendMessage",
                        "friend",
                    ]:
                        continue

                # 筛选平台
                if platform and umo_platform != platform:
                    continue

                # 获取服务配置
                rules = umo_rules.get(umo, {})
                svc_config = rules.get("session_service_config", {})

                custom_name = svc_config.get("custom_name", "") if svc_config else ""
                session_enabled = (
                    svc_config.get("session_enabled", True) if svc_config else True
                )
                llm_enabled = (
                    svc_config.get("llm_enabled", True) if svc_config else True
                )
                tts_enabled = (
                    svc_config.get("tts_enabled", True) if svc_config else True
                )

                # 搜索过滤
                if search:
                    search_lower = search.lower()
                    if (
                        search_lower not in umo.lower()
                        and search_lower not in custom_name.lower()
                    ):
                        continue

                # 获取 provider 配置
                chat_provider_key = (
                    f"provider_perf_{ProviderType.CHAT_COMPLETION.value}"
                )
                tts_provider_key = f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}"
                stt_provider_key = f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}"

                umos_with_status.append(
                    {
                        "umo": umo,
                        "platform": umo_platform,
                        "message_type": umo_message_type,
                        "session_id": umo_session_id,
                        "custom_name": custom_name,
                        "session_enabled": session_enabled,
                        "llm_enabled": llm_enabled,
                        "tts_enabled": tts_enabled,
                        "has_rules": umo in umo_rules,
                        "chat_provider": rules.get(chat_provider_key),
                        "tts_provider": rules.get(tts_provider_key),
                        "stt_provider": rules.get(stt_provider_key),
                    }
                )

            # 分页
            total = len(umos_with_status)
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated = umos_with_status[start_idx:end_idx]

            # 获取可用的平台列表
            platforms = list({u["platform"] for u in umos_with_status})

            # 获取可用的 providers
            provider_manager = self.core_lifecycle.provider_manager
            available_chat_providers = [
                {"id": p.meta().id, "name": p.meta().id, "model": p.meta().model}
                for p in provider_manager.provider_insts
            ]
            available_tts_providers = [
                {"id": p.meta().id, "name": p.meta().id, "model": p.meta().model}
                for p in provider_manager.tts_provider_insts
            ]
            available_stt_providers = [
                {"id": p.meta().id, "name": p.meta().id, "model": p.meta().model}
                for p in provider_manager.stt_provider_insts
            ]

            return (
                Response()
                .ok(
                    {
                        "sessions": paginated,
                        "total": total,
                        "page": page,
                        "page_size": page_size,
                        "platforms": platforms,
                        "available_chat_providers": available_chat_providers,
                        "available_tts_providers": available_tts_providers,
                        "available_stt_providers": available_stt_providers,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"获取会话状态列表失败: {e!s}")
            return Response().error(f"获取会话状态列表失败: {e!s}").__dict__

    async def batch_update_service(self):
        """批量更新多个 UMO 的服务状态 (LLM/TTS/Session)

        请求体:
        {
            "umos": ["平台:消息类型:会话ID", ...],  // 可选，如果不传则根据 scope 筛选
            "scope": "all" | "group" | "private" | "custom_group",  // 可选，批量范围
            "group_id": "分组ID",  // 当 scope 为 custom_group 时必填
            "llm_enabled": true/false/null,  // 可选，null表示不修改
            "tts_enabled": true/false/null,  // 可选
            "session_enabled": true/false/null  // 可选
        }
        """
        try:
            data = await request.get_json()
            umos = data.get("umos", [])
            scope = data.get("scope", "")
            group_id = data.get("group_id", "")
            llm_enabled = data.get("llm_enabled")
            tts_enabled = data.get("tts_enabled")
            session_enabled = data.get("session_enabled")

            # 如果没有任何修改
            if llm_enabled is None and tts_enabled is None and session_enabled is None:
                return Response().error("至少需要指定一个要修改的状态").__dict__

            # 如果指定了 scope，获取符合条件的所有 umo
            if scope and not umos:
                # 如果是自定义分组
                if scope == "custom_group":
                    if not group_id:
                        return Response().error("请指定分组 ID").__dict__
                    groups = self._get_groups()
                    if group_id not in groups:
                        return Response().error(f"分组 '{group_id}' 不存在").__dict__
                    umos = groups[group_id].get("umos", [])
                else:
                    async with self.db_helper.get_db() as session:
                        session: AsyncSession
                        result = await session.execute(
                            select(ConversationV2.user_id).distinct()
                        )
                        all_umos = [row[0] for row in result.fetchall()]

                    if scope == "group":
                        umos = [
                            u
                            for u in all_umos
                            if ":group:" in u.lower() or ":groupmessage:" in u.lower()
                        ]
                    elif scope == "private":
                        umos = [
                            u
                            for u in all_umos
                            if ":private:" in u.lower() or ":friend" in u.lower()
                        ]
                    elif scope == "all":
                        umos = all_umos

            if not umos:
                return Response().error("没有找到符合条件的会话").__dict__

            # 批量更新
            success_count = 0
            failed_umos = []

            for umo in umos:
                try:
                    # 获取现有配置
                    session_config = (
                        sp.get("session_service_config", {}, scope="umo", scope_id=umo)
                        or {}
                    )

                    # 更新状态
                    if llm_enabled is not None:
                        session_config["llm_enabled"] = llm_enabled
                    if tts_enabled is not None:
                        session_config["tts_enabled"] = tts_enabled
                    if session_enabled is not None:
                        session_config["session_enabled"] = session_enabled

                    # 保存
                    sp.put(
                        "session_service_config",
                        session_config,
                        scope="umo",
                        scope_id=umo,
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"更新 {umo} 服务状态失败: {e!s}")
                    failed_umos.append(umo)

            status_changes = []
            if llm_enabled is not None:
                status_changes.append(f"LLM={'启用' if llm_enabled else '禁用'}")
            if tts_enabled is not None:
                status_changes.append(f"TTS={'启用' if tts_enabled else '禁用'}")
            if session_enabled is not None:
                status_changes.append(f"会话={'启用' if session_enabled else '禁用'}")

            return (
                Response()
                .ok(
                    {
                        "message": f"已更新 {success_count} 个会话 ({', '.join(status_changes)})",
                        "success_count": success_count,
                        "failed_count": len(failed_umos),
                        "failed_umos": failed_umos,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"批量更新服务状态失败: {e!s}")
            return Response().error(f"批量更新服务状态失败: {e!s}").__dict__

    async def batch_update_provider(self):
        """批量更新多个 UMO 的 Provider 配置

        请求体:
        {
            "umos": ["平台:消息类型:会话ID", ...],  // 可选
            "scope": "all" | "group" | "private",  // 可选
            "provider_type": "chat_completion" | "text_to_speech" | "speech_to_text",
            "provider_id": "provider_id"
        }
        """
        try:
            data = await request.get_json()
            umos = data.get("umos", [])
            scope = data.get("scope", "")
            provider_type = data.get("provider_type")
            provider_id = data.get("provider_id")

            if not provider_type or not provider_id:
                return (
                    Response()
                    .error("缺少必要参数: provider_type, provider_id")
                    .__dict__
                )

            # 转换 provider_type
            provider_type_map = {
                "chat_completion": ProviderType.CHAT_COMPLETION,
                "text_to_speech": ProviderType.TEXT_TO_SPEECH,
                "speech_to_text": ProviderType.SPEECH_TO_TEXT,
            }
            if provider_type not in provider_type_map:
                return (
                    Response()
                    .error(f"不支持的 provider_type: {provider_type}")
                    .__dict__
                )

            provider_type_enum = provider_type_map[provider_type]

            # 如果指定了 scope，获取符合条件的所有 umo
            group_id = data.get("group_id", "")
            if scope and not umos:
                # 如果是自定义分组
                if scope == "custom_group":
                    if not group_id:
                        return Response().error("请指定分组 ID").__dict__
                    groups = self._get_groups()
                    if group_id not in groups:
                        return Response().error(f"分组 '{group_id}' 不存在").__dict__
                    umos = groups[group_id].get("umos", [])
                else:
                    async with self.db_helper.get_db() as session:
                        session: AsyncSession
                        result = await session.execute(
                            select(ConversationV2.user_id).distinct()
                        )
                        all_umos = [row[0] for row in result.fetchall()]

                    if scope == "group":
                        umos = [
                            u
                            for u in all_umos
                            if ":group:" in u.lower() or ":groupmessage:" in u.lower()
                        ]
                    elif scope == "private":
                        umos = [
                            u
                            for u in all_umos
                            if ":private:" in u.lower() or ":friend" in u.lower()
                        ]
                    elif scope == "all":
                        umos = all_umos

            if not umos:
                return Response().error("没有找到符合条件的会话").__dict__

            # 批量更新
            success_count = 0
            failed_umos = []
            provider_manager = self.core_lifecycle.provider_manager

            for umo in umos:
                try:
                    await provider_manager.set_provider(
                        provider_id=provider_id,
                        provider_type=provider_type_enum,
                        umo=umo,
                    )
                    success_count += 1
                except Exception as e:
                    logger.error(f"更新 {umo} Provider 失败: {e!s}")
                    failed_umos.append(umo)

            return (
                Response()
                .ok(
                    {
                        "message": f"已更新 {success_count} 个会话的 {provider_type} 为 {provider_id}",
                        "success_count": success_count,
                        "failed_count": len(failed_umos),
                        "failed_umos": failed_umos,
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"批量更新 Provider 失败: {e!s}")
            return Response().error(f"批量更新 Provider 失败: {e!s}").__dict__

    # ==================== 分组管理 API ====================

    def _get_groups(self) -> dict:
        """获取所有分组"""
        return sp.get("session_groups", {})

    def _save_groups(self, groups: dict) -> None:
        """保存分组"""
        sp.put("session_groups", groups)

    async def list_groups(self):
        """获取所有分组列表"""
        try:
            groups = self._get_groups()
            # 转换为列表格式，方便前端使用
            groups_list = []
            for group_id, group_data in groups.items():
                groups_list.append(
                    {
                        "id": group_id,
                        "name": group_data.get("name", ""),
                        "umos": group_data.get("umos", []),
                        "umo_count": len(group_data.get("umos", [])),
                    }
                )
            return Response().ok({"groups": groups_list}).__dict__
        except Exception as e:
            logger.error(f"获取分组列表失败: {e!s}")
            return Response().error(f"获取分组列表失败: {e!s}").__dict__

    async def create_group(self):
        """创建新分组"""
        try:
            data = await request.json
            name = data.get("name", "").strip()
            umos = data.get("umos", [])

            if not name:
                return Response().error("分组名称不能为空").__dict__

            groups = self._get_groups()

            # 生成唯一 ID
            import uuid

            group_id = str(uuid.uuid4())[:8]

            groups[group_id] = {
                "name": name,
                "umos": umos,
            }

            self._save_groups(groups)

            return (
                Response()
                .ok(
                    {
                        "message": f"分组 '{name}' 创建成功",
                        "group": {
                            "id": group_id,
                            "name": name,
                            "umos": umos,
                            "umo_count": len(umos),
                        },
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"创建分组失败: {e!s}")
            return Response().error(f"创建分组失败: {e!s}").__dict__

    async def update_group(self):
        """更新分组（改名、增删成员）"""
        try:
            data = await request.json
            group_id = data.get("id")
            name = data.get("name")
            umos = data.get("umos")
            add_umos = data.get("add_umos", [])
            remove_umos = data.get("remove_umos", [])

            if not group_id:
                return Response().error("分组 ID 不能为空").__dict__

            groups = self._get_groups()

            if group_id not in groups:
                return Response().error(f"分组 '{group_id}' 不存在").__dict__

            group = groups[group_id]

            # 更新名称
            if name is not None:
                group["name"] = name.strip()

            # 直接设置 umos 列表
            if umos is not None:
                group["umos"] = umos
            else:
                # 增量更新
                current_umos = set(group.get("umos", []))
                if add_umos:
                    current_umos.update(add_umos)
                if remove_umos:
                    current_umos.difference_update(remove_umos)
                group["umos"] = list(current_umos)

            self._save_groups(groups)

            return (
                Response()
                .ok(
                    {
                        "message": f"分组 '{group['name']}' 更新成功",
                        "group": {
                            "id": group_id,
                            "name": group["name"],
                            "umos": group["umos"],
                            "umo_count": len(group["umos"]),
                        },
                    }
                )
                .__dict__
            )
        except Exception as e:
            logger.error(f"更新分组失败: {e!s}")
            return Response().error(f"更新分组失败: {e!s}").__dict__

    async def delete_group(self):
        """删除分组"""
        try:
            data = await request.json
            group_id = data.get("id")

            if not group_id:
                return Response().error("分组 ID 不能为空").__dict__

            groups = self._get_groups()

            if group_id not in groups:
                return Response().error(f"分组 '{group_id}' 不存在").__dict__

            group_name = groups[group_id].get("name", group_id)
            del groups[group_id]

            self._save_groups(groups)

            return Response().ok({"message": f"分组 '{group_name}' 已删除"}).__dict__
        except Exception as e:
            logger.error(f"删除分组失败: {e!s}")
            return Response().error(f"删除分组失败: {e!s}").__dict__
