import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot import logger
from astrbot.core.db.po import ConversationV2, Preference
from astrbot.core.db.protocols import SessionManagementStore
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.star.star import PluginRegistry
from astrbot.core.umo_alias import build_umo_alias_map, parse_umo, serialize_umo_alias
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.shared_preferences import SharedPreferences

AVAILABLE_SESSION_RULE_KEYS = [
    "session_service_config",
    "session_plugin_config",
    "kb_config",
    f"provider_perf_{ProviderType.CHAT_COMPLETION.value}",
    f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}",
    f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}",
]
_SESSION_CONFIG_RULE_KEYS = frozenset(
    {"session_service_config", "session_plugin_config", "kb_config"}
)


class SessionManagementServiceError(Exception):
    pass


class SessionManagementService:
    def __init__(
        self,
        db_helper: SessionManagementStore,
        preferences: SharedPreferences,
        provider_manager: ProviderManager,
        persona_manager: PersonaManager,
        plugin_catalog: PluginRegistry,
        knowledge_base_manager: KnowledgeBaseManager,
        config_router: UmopConfigRouter | None = None,
    ) -> None:
        self.db_helper = db_helper
        self.preferences = preferences
        self.provider_manager = provider_manager
        self.persona_manager = persona_manager
        self.plugin_catalog = plugin_catalog
        self.knowledge_base_manager = knowledge_base_manager
        self.config_router = config_router

    @staticmethod
    def _payload(data: object) -> dict[str, Any]:
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _is_group_umo(umo: str) -> bool:
        umo_lower = umo.lower()
        return ":group:" in umo_lower or ":groupmessage:" in umo_lower

    @staticmethod
    def _is_private_umo(umo: str) -> bool:
        umo_lower = umo.lower()
        return (
            ":private:" in umo_lower
            or ":friend:" in umo_lower
            or ":friendmessage:" in umo_lower
        )

    @staticmethod
    def _provider_type_from_rule_key(rule_key: str) -> ProviderType | None:
        prefix = "provider_perf_"
        if not rule_key.startswith(prefix):
            return None
        try:
            return ProviderType(rule_key.removeprefix(prefix))
        except ValueError:
            return None

    @staticmethod
    def _validate_umo_list(umos: object) -> list[str]:
        if not isinstance(umos, list) or not all(
            isinstance(umo, str) and umo for umo in umos
        ):
            raise SessionManagementServiceError("参数 umos 必须是非空字符串数组")
        return umos

    def resolve_umo_config_id(self, umo: str) -> str:
        """Resolve a UMO's configuration from runtime-owned routing state.

        Dashboard clients may select a view configuration, but that value must
        never define the authorization target for a session write. The router
        is the single source of truth and falls back to the default profile in
        the same way inbound event routing does.
        """

        if not isinstance(umo, str) or not umo:
            raise SessionManagementServiceError("参数 umo 必须是非空字符串")
        if self.config_router is None:
            return "default"
        return self.config_router.get_conf_id_for_umop(umo) or "default"

    @staticmethod
    def _normalize_group_umos(umos: object) -> list[str]:
        if not isinstance(umos, list):
            return []

        normalized = []
        seen = set()
        for umo in umos:
            if not isinstance(umo, str) or not umo or umo in seen:
                continue
            normalized.append(umo)
            seen.add(umo)
        return normalized

    @staticmethod
    def _session_config_name(config: dict) -> str:
        custom_name = config.get("custom_name", "")
        return custom_name if isinstance(custom_name, str) else ""

    @staticmethod
    def _session_config_enabled(config: dict, key: str) -> bool:
        value = config.get(key, True)
        return value if isinstance(value, bool) else True

    async def list_known_umos(self) -> list[str]:
        async with self.db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(select(ConversationV2.user_id).distinct())
            umos = {str(row[0]) for row in result.fetchall() if row[0]}

        aliases = await self.db_helper.get_umo_aliases()
        umos.update(str(alias.umo) for alias in aliases if alias.umo)
        return sorted(umos)

    async def get_umo_alias_map(self, umos: list[str]) -> dict:
        return build_umo_alias_map(await self.db_helper.get_umo_aliases(umos))

    def build_umo_info(self, umo: str | None, alias_map: dict) -> dict:
        umo_str = umo or ""
        return {
            "umo": umo_str,
            **parse_umo(umo_str),
            **serialize_umo_alias(alias_map.get(umo_str), umo_str),
        }

    async def list_active_umos(self) -> dict:
        umos = await self.list_known_umos()
        alias_map = await self.get_umo_alias_map(umos)
        return {
            "umos": umos,
            "umo_infos": [self.build_umo_info(umo, alias_map) for umo in umos],
        }

    async def get_umos_by_scope(
        self,
        scope: str,
        group_id: str = "",
    ) -> list[str]:
        if scope == "custom_group":
            if not group_id:
                raise SessionManagementServiceError("请指定分组 ID")
            groups = await self.get_groups()
            if group_id not in groups:
                raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")
            return groups[group_id].get("umos", [])

        all_umos = await self.list_known_umos()
        if scope == "group":
            return [umo for umo in all_umos if self._is_group_umo(umo)]
        if scope == "private":
            return [umo for umo in all_umos if self._is_private_umo(umo)]
        if scope == "all":
            return all_umos
        return []

    async def get_umo_rules(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str = "",
    ) -> tuple[dict, int]:
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
                raw_value = pref.value
                if not isinstance(raw_value, dict) or "val" not in raw_value:
                    logger.warning(
                        "忽略格式错误的会话规则: umo=%s, key=%s",
                        umo_id,
                        pref.key,
                    )
                    continue

                rule_value = raw_value["val"]
                if pref.key == "session_plugin_config":
                    if not isinstance(rule_value, dict):
                        logger.warning("忽略格式错误的会话插件规则: umo=%s", umo_id)
                        continue
                    rule_value = rule_value.get(umo_id)

                if pref.key in _SESSION_CONFIG_RULE_KEYS:
                    if not isinstance(rule_value, dict):
                        logger.warning(
                            "忽略格式错误的会话配置规则: umo=%s, key=%s",
                            umo_id,
                            pref.key,
                        )
                        continue
                elif self._provider_type_from_rule_key(pref.key) is not None and (
                    not isinstance(rule_value, str) or not rule_value
                ):
                    logger.warning(
                        "忽略格式错误的会话 Provider 规则: umo=%s, key=%s",
                        umo_id,
                        pref.key,
                    )
                    continue

                umo_rules.setdefault(umo_id, {})[pref.key] = rule_value

        alias_map = await self.get_umo_alias_map(list(umo_rules.keys()))

        if search:
            search_lower = search.lower()
            filtered_rules = {}
            for umo_id, rules in umo_rules.items():
                if search_lower in umo_id.lower():
                    filtered_rules[umo_id] = rules
                    continue

                svc_config = rules.get("session_service_config", {})
                custom_name = (
                    self._session_config_name(svc_config)
                    if isinstance(svc_config, dict)
                    else ""
                )
                if custom_name and search_lower in custom_name.lower():
                    filtered_rules[umo_id] = rules
                    continue

                alias_info = serialize_umo_alias(alias_map.get(umo_id), umo_id)
                if any(
                    search_lower in alias_info[key].lower()
                    for key in ("auto_name", "user_alias", "display_name")
                    if alias_info.get(key)
                ):
                    filtered_rules[umo_id] = rules
            umo_rules = filtered_rules

        total = len(umo_rules)
        all_umo_ids = sorted(umo_rules)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_umo_ids = all_umo_ids[start_idx:end_idx]

        return {umo_id: umo_rules[umo_id] for umo_id in paginated_umo_ids}, total

    async def list_session_rules(
        self,
        *,
        page: int,
        page_size: int,
        search: str,
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size, default_page_size=10)
        umo_rules, total = await self.get_umo_rules(
            page=page,
            page_size=page_size,
            search=search,
        )

        alias_map = await self.get_umo_alias_map(list(umo_rules.keys()))
        rules_list = [
            {
                "rules": rules,
                **self.build_umo_info(umo, alias_map),
            }
            for umo, rules in umo_rules.items()
        ]

        available_personas = [
            {"name": p.persona_id, "prompt": p.system_prompt}
            for p in self.persona_manager.personas
        ]
        available_plugins = [
            {
                "name": p.name,
                "display_name": p.display_name or p.name,
                "desc": p.desc,
            }
            for p in self.plugin_catalog.all()
            if not p.reserved and p.name
        ]

        available_kbs = []
        try:
            kbs = await self.knowledge_base_manager.list_kbs()
            available_kbs = [
                {
                    "kb_id": kb.kb_id,
                    "kb_name": kb.kb_name,
                    "emoji": kb.emoji,
                }
                for kb in kbs
            ]
        except Exception as exc:
            logger.warning("获取知识库列表失败: %s", safe_error("", exc))

        return {
            "rules": rules_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "available_personas": available_personas,
            "available_chat_providers": self._serialize_provider_insts(
                self.provider_manager.provider_insts
            ),
            "available_stt_providers": self._serialize_provider_insts(
                self.provider_manager.stt_provider_insts
            ),
            "available_tts_providers": self._serialize_provider_insts(
                self.provider_manager.tts_provider_insts
            ),
            "available_plugins": available_plugins,
            "available_kbs": available_kbs,
            "available_rule_keys": AVAILABLE_SESSION_RULE_KEYS,
        }

    async def update_session_rule(self, data: object) -> dict:
        payload = self._payload(data)
        umo = payload.get("umo")
        rule_key = payload.get("rule_key")
        rule_value = payload.get("rule_value")

        if not umo:
            raise SessionManagementServiceError("缺少必要参数: umo")
        if not rule_key:
            raise SessionManagementServiceError("缺少必要参数: rule_key")
        if rule_key not in AVAILABLE_SESSION_RULE_KEYS:
            raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")

        if rule_key in _SESSION_CONFIG_RULE_KEYS and not isinstance(rule_value, dict):
            raise SessionManagementServiceError(
                f"规则 {rule_key} 需要对象类型的 rule_value"
            )

        if rule_key == "session_plugin_config":
            rule_value = {umo: rule_value}

        provider_type = self._provider_type_from_rule_key(rule_key)
        if provider_type is not None:
            if not isinstance(rule_value, str) or not rule_value:
                raise SessionManagementServiceError(
                    f"规则 {rule_key} 需要非空 provider_id"
                )
            await self.provider_manager.set_provider(
                provider_id=rule_value,
                provider_type=provider_type,
                umo=umo,
            )
        else:
            await self.preferences.session_put(umo, rule_key, rule_value)
        return {"message": f"规则 {rule_key} 已更新", "umo": umo}

    async def delete_session_rule(self, data: object) -> dict:
        payload = self._payload(data)
        umo = payload.get("umo")
        rule_key = payload.get("rule_key")

        if not umo:
            raise SessionManagementServiceError("缺少必要参数: umo")

        if rule_key:
            if rule_key not in AVAILABLE_SESSION_RULE_KEYS:
                raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")
            provider_type = self._provider_type_from_rule_key(rule_key)
            if provider_type is not None:
                await self.provider_manager.clear_provider_override(
                    umo,
                    provider_type,
                )
            else:
                await self.preferences.session_remove(umo, rule_key)
            return {"message": f"规则 {rule_key} 已删除", "umo": umo}

        await self.provider_manager.clear_all_provider_overrides(umo)
        await self.preferences.clear_async("umo", umo)
        return {"message": "所有规则已删除", "umo": umo}

    async def delete_session_rules(self, data: object) -> dict:
        payload = self._payload(data)
        if payload.get("umo") and not payload.get("umos") and not payload.get("scope"):
            return await self.delete_session_rule(payload)
        return await self.batch_delete_session_rule(payload)

    async def batch_delete_session_rule(self, data: object) -> dict:
        payload = self._payload(data)
        umos = payload.get("umos", [])
        scope = payload.get("scope", "")
        group_id = payload.get("group_id", "")
        rule_key = payload.get("rule_key")

        if scope and not umos:
            umos = await self.get_umos_by_scope(scope, group_id)

        if not umos:
            raise SessionManagementServiceError("缺少必要参数: umos 或有效的 scope")
        if not isinstance(umos, list):
            raise SessionManagementServiceError("参数 umos 必须是数组")
        self._validate_umo_list(umos)
        if rule_key and rule_key not in AVAILABLE_SESSION_RULE_KEYS:
            raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")

        success_count = 0
        failed_umos = []
        for umo in umos:
            try:
                if rule_key:
                    provider_type = self._provider_type_from_rule_key(rule_key)
                    if provider_type is not None:
                        await self.provider_manager.clear_provider_override(
                            umo,
                            provider_type,
                        )
                    else:
                        await self.preferences.session_remove(umo, rule_key)
                else:
                    await self.provider_manager.clear_all_provider_overrides(umo)
                    await self.preferences.clear_async("umo", umo)
                success_count += 1
            except Exception as exc:
                logger.error("删除会话规则失败: %s", safe_error("", exc))
                failed_umos.append(umo)

        message = f"已删除 {success_count} 条规则"
        if rule_key:
            message = f"已删除 {success_count} 条 {rule_key} 规则"

        result = {
            "message": message,
            "success_count": success_count,
        }
        if failed_umos:
            result.update(
                {
                    "message": f"{message}，{len(failed_umos)} 条删除失败",
                    "failed_umos": failed_umos,
                }
            )
        return result

    async def list_all_umos_with_status(
        self,
        *,
        page: int,
        page_size: int,
        search: str,
        message_type: str,
        platform: str,
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size, default_page_size=20)
        all_umos = await self.list_known_umos()
        alias_map = await self.get_umo_alias_map(all_umos)
        umo_rules, _ = await self.get_umo_rules(page=1, page_size=99999, search="")

        umos_with_status = []
        for umo in all_umos:
            umo_info = self.build_umo_info(umo, alias_map)
            umo_platform = umo_info["platform"]
            umo_message_type = umo_info["message_type"]

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

            if platform and umo_platform != platform:
                continue

            rules = umo_rules.get(umo, {})
            svc_config = rules.get("session_service_config", {})
            if not isinstance(svc_config, dict):
                svc_config = {}

            custom_name = self._session_config_name(svc_config)
            session_enabled = self._session_config_enabled(
                svc_config, "session_enabled"
            )
            llm_enabled = self._session_config_enabled(svc_config, "llm_enabled")
            tts_enabled = self._session_config_enabled(svc_config, "tts_enabled")

            if search:
                search_lower = search.lower()
                search_targets = [
                    umo,
                    custom_name,
                    umo_info["auto_name"],
                    umo_info["user_alias"],
                    umo_info["display_name"],
                ]
                if not any(
                    search_lower in target.lower()
                    for target in search_targets
                    if target
                ):
                    continue

            chat_provider_key = f"provider_perf_{ProviderType.CHAT_COMPLETION.value}"
            tts_provider_key = f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}"
            stt_provider_key = f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}"

            umos_with_status.append(
                {
                    **umo_info,
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

        total = len(umos_with_status)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated = umos_with_status[start_idx:end_idx]
        platforms = sorted({u["platform"] for u in umos_with_status})
        return {
            "sessions": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
            "platforms": platforms,
            "available_chat_providers": self._serialize_provider_insts(
                self.provider_manager.provider_insts
            ),
            "available_tts_providers": self._serialize_provider_insts(
                self.provider_manager.tts_provider_insts
            ),
            "available_stt_providers": self._serialize_provider_insts(
                self.provider_manager.stt_provider_insts
            ),
        }

    async def batch_update_service(self, data: object) -> dict:
        payload = self._payload(data)
        umos = payload.get("umos", [])
        scope = payload.get("scope", "")
        group_id = payload.get("group_id", "")
        llm_enabled = payload.get("llm_enabled")
        tts_enabled = payload.get("tts_enabled")
        session_enabled = payload.get("session_enabled")

        if llm_enabled is None and tts_enabled is None and session_enabled is None:
            raise SessionManagementServiceError("至少需要指定一个要修改的状态")

        if scope and not umos:
            umos = await self.get_umos_by_scope(scope, group_id)

        if not umos:
            raise SessionManagementServiceError("没有找到符合条件的会话")
        umos = self._validate_umo_list(umos)

        success_count = 0
        failed_umos = []

        for umo in umos:
            try:
                session_config = await self.preferences.session_get(
                    umo, "session_service_config", {}
                )
                if not isinstance(session_config, dict):
                    session_config = {}

                if llm_enabled is not None:
                    session_config["llm_enabled"] = llm_enabled
                if tts_enabled is not None:
                    session_config["tts_enabled"] = tts_enabled
                if session_enabled is not None:
                    session_config["session_enabled"] = session_enabled

                await self.preferences.session_put(
                    umo, "session_service_config", session_config
                )
                success_count += 1
            except Exception as exc:
                logger.error("更新会话服务状态失败: %s", safe_error("", exc))
                failed_umos.append(umo)

        status_changes = []
        if llm_enabled is not None:
            status_changes.append(f"LLM={'启用' if llm_enabled else '禁用'}")
        if tts_enabled is not None:
            status_changes.append(f"TTS={'启用' if tts_enabled else '禁用'}")
        if session_enabled is not None:
            status_changes.append(f"会话={'启用' if session_enabled else '禁用'}")

        return {
            "message": f"已更新 {success_count} 个会话 ({', '.join(status_changes)})",
            "success_count": success_count,
            "failed_count": len(failed_umos),
            "failed_umos": failed_umos,
        }

    async def batch_update_provider(self, data: object) -> dict:
        payload = self._payload(data)
        umos = payload.get("umos", [])
        scope = payload.get("scope", "")
        provider_type = payload.get("provider_type")
        provider_id = payload.get("provider_id")

        if not provider_type or not provider_id:
            raise SessionManagementServiceError(
                "缺少必要参数: provider_type, provider_id"
            )

        provider_type_map = {
            "chat_completion": ProviderType.CHAT_COMPLETION,
            "text_to_speech": ProviderType.TEXT_TO_SPEECH,
            "speech_to_text": ProviderType.SPEECH_TO_TEXT,
        }
        if provider_type not in provider_type_map:
            raise SessionManagementServiceError(
                f"不支持的 provider_type: {provider_type}"
            )

        group_id = payload.get("group_id", "")
        if scope and not umos:
            umos = await self.get_umos_by_scope(scope, group_id)

        if not umos:
            raise SessionManagementServiceError("没有找到符合条件的会话")
        umos = self._validate_umo_list(umos)

        success_count = 0
        failed_umos = []
        for umo in umos:
            try:
                await self.provider_manager.set_provider(
                    provider_id=provider_id,
                    provider_type=provider_type_map[provider_type],
                    umo=umo,
                )
                success_count += 1
            except Exception as exc:
                logger.error("更新会话 Provider 失败: %s", safe_error("", exc))
                failed_umos.append(umo)

        return {
            "message": f"已更新 {success_count} 个会话的 {provider_type} 为 {provider_id}",
            "success_count": success_count,
            "failed_count": len(failed_umos),
            "failed_umos": failed_umos,
        }

    async def get_groups(self) -> dict:
        try:
            groups = await self.preferences.global_get("session_groups", {})
        except (AttributeError, KeyError, TypeError) as exc:
            logger.warning("忽略格式错误的会话分组偏好: %s", safe_error("", exc))
            return {}
        if not isinstance(groups, dict):
            return {}

        normalized_groups = {}
        for group_id, group_data in groups.items():
            if not isinstance(group_id, str) or not group_id:
                continue
            if not isinstance(group_data, dict):
                logger.warning("忽略格式错误的会话分组: id=%s", group_id)
                continue
            name = group_data.get("name", "")
            normalized_groups[group_id] = {
                "name": name.strip() if isinstance(name, str) else "",
                "umos": self._normalize_group_umos(group_data.get("umos", [])),
            }
        return normalized_groups

    async def save_groups(self, groups: dict) -> None:
        await self.preferences.global_put("session_groups", groups)

    async def list_groups(self) -> dict:
        groups = await self.get_groups()
        return {
            "groups": [
                {
                    "id": group_id,
                    "name": group_data.get("name", ""),
                    "umos": group_data.get("umos", []),
                    "umo_count": len(group_data.get("umos", [])),
                }
                for group_id, group_data in groups.items()
            ]
        }

    async def create_group(self, data: object) -> dict:
        payload = self._payload(data)
        raw_name = payload.get("name", "")
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        umos = payload.get("umos", [])

        if not name:
            raise SessionManagementServiceError("分组名称不能为空")
        umos = self._validate_umo_list(umos)

        groups = await self.get_groups()
        group_id = str(uuid.uuid4())[:8]
        groups[group_id] = {
            "name": name,
            "umos": self._normalize_group_umos(umos),
        }
        await self.save_groups(groups)

        return {
            "message": f"分组 '{name}' 创建成功",
            "group": {
                "id": group_id,
                "name": name,
                "umos": self._normalize_group_umos(umos),
                "umo_count": len(self._normalize_group_umos(umos)),
            },
        }

    async def update_group(self, data: object) -> dict:
        payload = self._payload(data)
        group_id = payload.get("id") or payload.get("group_id")
        name = payload.get("name")
        umos = payload.get("umos")
        add_umos = payload.get("add_umos", [])
        remove_umos = payload.get("remove_umos", [])

        if not group_id:
            raise SessionManagementServiceError("分组 ID 不能为空")

        groups = await self.get_groups()
        if group_id not in groups:
            raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")

        group = groups[group_id]
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise SessionManagementServiceError("分组名称不能为空")
            group["name"] = name.strip()

        if umos is not None:
            group["umos"] = self._normalize_group_umos(self._validate_umo_list(umos))
        else:
            add_umos = self._validate_umo_list(add_umos)
            remove_umos = self._validate_umo_list(remove_umos)
            current_umos = self._normalize_group_umos(group.get("umos", []))
            if add_umos:
                current_umos.extend(umo for umo in add_umos if umo not in current_umos)
            if remove_umos:
                remove_set = set(remove_umos)
                current_umos = [umo for umo in current_umos if umo not in remove_set]
            group["umos"] = current_umos

        await self.save_groups(groups)

        return {
            "message": f"分组 '{group['name']}' 更新成功",
            "group": {
                "id": group_id,
                "name": group["name"],
                "umos": group["umos"],
                "umo_count": len(group["umos"]),
            },
        }

    async def delete_group(self, data: object) -> dict:
        payload = self._payload(data)
        group_id = payload.get("id") or payload.get("group_id")

        if not group_id:
            raise SessionManagementServiceError("分组 ID 不能为空")

        groups = await self.get_groups()
        if group_id not in groups:
            raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")

        group_name = groups[group_id].get("name", group_id)
        del groups[group_id]
        await self.save_groups(groups)
        return {"message": f"分组 '{group_name}' 已删除"}

    @staticmethod
    def _normalize_page(
        page: int,
        page_size: int,
        *,
        default_page_size: int,
    ) -> tuple[int, int]:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = default_page_size
        if page_size > 100:
            page_size = 100
        return page, page_size

    @staticmethod
    def _serialize_provider_insts(provider_insts: list) -> list[dict]:
        return [
            {
                "id": provider.meta().id,
                "name": provider.meta().id,
                "model": provider.meta().model,
            }
            for provider in provider_insts
        ]
