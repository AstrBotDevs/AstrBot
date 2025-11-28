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
