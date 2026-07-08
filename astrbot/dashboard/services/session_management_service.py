from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core import logger, sp
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ConversationV2, Preference
from astrbot.core.provider.entities import ProviderType
from astrbot.core.umo_alias import build_umo_alias_map, parse_umo, serialize_umo_alias

AVAILABLE_SESSION_RULE_KEYS = [
    "session_service_config",
    "session_plugin_config",
    "kb_config",
    f"provider_perf_{ProviderType.CHAT_COMPLETION.value}",
    f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}",
    f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}",
]


class SessionManagementServiceError(Exception):
    pass


class SessionManagementService:
    def __init__(
        self,
        core_lifecycle: AstrBotCoreLifecycle,
        db_helper: BaseDatabase,
    ) -> None:
        self.core_lifecycle = core_lifecycle
        self.db_helper = db_helper

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
            groups = self.get_groups()
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
        umo: str = "",
    ) -> tuple[dict, int]:
        umo_rules = {}
        config_mgr = self.core_lifecycle.astrbot_config_mgr
        async with self.db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(Preference).where(
                    col(Preference.scope) == "umo",
                    col(Preference.key) == config_mgr.core_config_override_key,
                )
            )
            prefs = result.scalars().all()
            for pref in prefs:
                umo_id = pref.scope_id
                paths = config_mgr.normalize_conf_override_payload(
                    pref.value.get("val") if isinstance(pref.value, dict) else None
                )
                rules = {}
                service_config = {}
                if "provider_settings.enable" in paths:
                    service_config["llm_enabled"] = bool(
                        paths["provider_settings.enable"]
                    )
                if "provider_tts_settings.enable" in paths:
                    service_config["tts_enabled"] = bool(
                        paths["provider_tts_settings.enable"]
                    )
                if "provider_settings.default_personality" in paths:
                    service_config["persona_id"] = paths[
                        "provider_settings.default_personality"
                    ]
                if "platform_settings.id_blacklist" in paths:
                    blacklist = [
                        str(item).strip()
                        for item in paths["platform_settings.id_blacklist"]
                        if str(item).strip()
                    ]
                    service_config["session_enabled"] = umo_id not in blacklist
                if service_config:
                    rules["session_service_config"] = service_config

                if isinstance(paths.get("plugin_disabled_set"), list):
                    rules["session_plugin_config"] = {
                        "disabled_plugins": paths["plugin_disabled_set"]
                    }

                kb_config = {}
                if "kb_names" in paths:
                    kb_config["kb_names"] = paths["kb_names"]
                if "kb_final_top_k" in paths:
                    kb_config["top_k"] = paths["kb_final_top_k"]
                if kb_config:
                    rules["kb_config"] = kb_config

                provider_rule_map = {
                    "provider_settings.default_provider_id": (
                        f"provider_perf_{ProviderType.CHAT_COMPLETION.value}"
                    ),
                    "provider_stt_settings.provider_id": (
                        f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}"
                    ),
                    "provider_tts_settings.provider_id": (
                        f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}"
                    ),
                }
                for config_path, rule_key in provider_rule_map.items():
                    if config_path in paths:
                        rules[rule_key] = paths[config_path]

                if rules:
                    umo_rules[umo_id] = rules

        aliases = await self.db_helper.get_umo_aliases()
        alias_map = build_umo_alias_map(aliases)
        for alias in aliases:
            alias_info = serialize_umo_alias(alias, alias.umo)
            if alias_info.get("user_alias"):
                umo_rules.setdefault(alias.umo, {}).setdefault(
                    "session_service_config", {}
                )["custom_name"] = alias_info["user_alias"]

        if search:
            search_lower = search.lower()
            filtered_rules = {}
            for umo_id, rules in umo_rules.items():
                if search_lower in umo_id.lower():
                    filtered_rules[umo_id] = rules
                    continue

                svc_config = rules.get("session_service_config", {})
                custom_name = svc_config.get("custom_name", "") if svc_config else ""
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

        if umo:
            umo_rules = {
                umo_id: rules for umo_id, rules in umo_rules.items() if umo_id == umo
            }

        total = len(umo_rules)
        all_umo_ids = list(umo_rules.keys())
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
        include_available_options: bool = True,
        umo: str = "",
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size, default_page_size=10)
        umo_rules, total = await self.get_umo_rules(
            page=page,
            page_size=page_size,
            search=search,
            umo=umo,
        )

        alias_map = await self.get_umo_alias_map(list(umo_rules.keys()))
        rules_list = [
            {
                "rules": rules,
                **self.build_umo_info(umo, alias_map),
            }
            for umo, rules in umo_rules.items()
        ]

        result = {
            "rules": rules_list,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
        if not include_available_options:
            return result

        provider_manager = self.core_lifecycle.provider_manager
        persona_mgr = getattr(self.core_lifecycle, "persona_mgr", None)
        plugin_manager = getattr(self.core_lifecycle, "plugin_manager", None)
        kb_manager = getattr(self.core_lifecycle, "kb_manager", None)

        available_personas = [
            {"name": p["name"], "prompt": p.get("prompt", "")}
            for p in getattr(persona_mgr, "personas_v3", [])
        ]
        available_plugins = []
        if plugin_manager and getattr(plugin_manager, "context", None):
            available_plugins = [
                {
                    "name": p.name,
                    "display_name": p.display_name or p.name,
                    "desc": p.desc,
                }
                for p in plugin_manager.context.get_all_stars()
                if not p.reserved and p.name
            ]

        available_kbs = []
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
            except Exception as exc:
                logger.warning(f"获取知识库列表失败: {exc!s}")

        kb_name_to_id = {
            kb["kb_name"]: kb["kb_id"]
            for kb in available_kbs
            if kb.get("kb_name") and kb.get("kb_id")
        }
        kb_id_set = {kb["kb_id"] for kb in available_kbs if kb.get("kb_id")}
        for item in rules_list:
            kb_config = item.get("rules", {}).get("kb_config")
            if isinstance(kb_config, dict) and "kb_names" in kb_config:
                kb_config["kb_ids"] = [
                    str(kb_ref)
                    if str(kb_ref) in kb_id_set
                    else kb_name_to_id[str(kb_ref)]
                    for kb_ref in kb_config["kb_names"]
                    if str(kb_ref) in kb_id_set or str(kb_ref) in kb_name_to_id
                ]

        result.update(
            {
                "available_personas": available_personas,
                "available_chat_providers": self._serialize_provider_insts(
                    getattr(provider_manager, "provider_insts", [])
                ),
                "available_stt_providers": self._serialize_provider_insts(
                    getattr(provider_manager, "stt_provider_insts", [])
                ),
                "available_tts_providers": self._serialize_provider_insts(
                    getattr(provider_manager, "tts_provider_insts", [])
                ),
                "available_plugins": available_plugins,
                "available_kbs": available_kbs,
                "available_rule_keys": AVAILABLE_SESSION_RULE_KEYS,
            }
        )
        return result

    async def list_session_config_overrides(
        self,
        *,
        page: int,
        page_size: int,
        search: str,
        umo: str = "",
    ) -> dict:
        """List UMO config overrides without editor option payloads.

        Args:
            page: Page number.
            page_size: Number of items per page.
            search: Search keyword.

        Returns:
            Paginated config override rows.
        """
        return await self.list_session_rules(
            page=page,
            page_size=page_size,
            search=search,
            umo=umo,
            include_available_options=False,
        )

    async def update_session_config_override(self, data: object) -> dict:
        """Update one core config override path for a UMO.

        Args:
            data: Request payload containing umo, path, and value.

        Returns:
            Operation result with the updated UMO and config path.

        Raises:
            SessionManagementServiceError: If required payload fields are missing.
        """
        payload = self._payload(data)
        umo = str(payload.get("umo") or "").strip()
        path = str(payload.get("path") or "").strip()

        if not umo:
            raise SessionManagementServiceError("缺少必要参数: umo")
        if not path:
            raise SessionManagementServiceError("缺少必要参数: path")
        if "value" not in payload:
            raise SessionManagementServiceError("缺少必要参数: value")

        await self.core_lifecycle.astrbot_config_mgr.update_conf_overrides(
            umo,
            {path: payload.get("value")},
        )
        return {"message": f"配置覆盖项 {path} 已更新", "umo": umo, "path": path}

    async def delete_session_config_override(self, data: object) -> dict:
        """Delete one or more core config override paths for a UMO.

        Args:
            data: Request payload containing UMO selection and path or paths.

        Returns:
            Operation result with updated UMOs and removed paths.

        Raises:
            SessionManagementServiceError: If required payload fields are missing.
        """
        payload = self._payload(data)
        umos = [
            str(umo).strip()
            for umo in (
                payload.get("umos") if isinstance(payload.get("umos"), list) else []
            )
            if str(umo).strip()
        ]
        umo = str(payload.get("umo") or "").strip()
        if umo:
            umos.append(umo)

        scope = str(payload.get("scope") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        if scope and not umos:
            umos = await self.get_umos_by_scope(scope, group_id)
        umos = list(dict.fromkeys(umos))

        raw_paths = payload.get("paths")
        paths = [
            str(path).strip()
            for path in (raw_paths if isinstance(raw_paths, list) else [])
            if str(path).strip()
        ]
        path = str(payload.get("path") or "").strip()
        if path:
            paths.append(path)
        paths = list(dict.fromkeys(paths))

        if not umos:
            raise SessionManagementServiceError(
                "缺少必要参数: umo、umos 或有效的 scope"
            )
        if not paths:
            raise SessionManagementServiceError("缺少必要参数: path 或 paths")

        success_count = 0
        failed_umos = []
        for target_umo in umos:
            try:
                await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                    target_umo,
                    paths,
                )
                success_count += 1
            except Exception as exc:
                logger.error(
                    f"Failed to delete config override for {target_umo}: {exc!s}"
                )
                failed_umos.append(target_umo)

        return {
            "message": f"已删除 {success_count} 个会话的配置覆盖项",
            "success_count": success_count,
            "failed_count": len(failed_umos),
            "failed_umos": failed_umos,
            "paths": paths,
        }

    async def update_session_alias(self, data: object) -> dict:
        """Update UMO user aliases used as session remarks.

        Args:
            data: Request payload containing UMO selection and custom_name.

        Returns:
            Operation result with updated UMO count.

        Raises:
            SessionManagementServiceError: If required payload fields are missing.
        """
        payload = self._payload(data)
        if "custom_name" not in payload:
            raise SessionManagementServiceError("缺少必要参数: custom_name")

        umos = [
            str(umo).strip()
            for umo in (
                payload.get("umos") if isinstance(payload.get("umos"), list) else []
            )
            if str(umo).strip()
        ]
        umo = str(payload.get("umo") or "").strip()
        if umo:
            umos.append(umo)

        scope = str(payload.get("scope") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        if scope and not umos:
            umos = await self.get_umos_by_scope(scope, group_id)
        umos = list(dict.fromkeys(umos))

        if not umos:
            raise SessionManagementServiceError(
                "缺少必要参数: umo、umos 或有效的 scope"
            )

        custom_name = str(payload.get("custom_name") or "").strip()
        success_count = 0
        failed_umos = []
        for target_umo in umos:
            try:
                alias = await self.db_helper.get_umo_alias(target_umo)
                if alias or custom_name:
                    await self.db_helper.upsert_umo_alias(
                        target_umo,
                        alias.creator_sender_id if alias else "",
                        alias.auto_name if alias else None,
                        custom_name or None,
                    )
                success_count += 1
            except Exception as exc:
                logger.error(f"Failed to update alias for {target_umo}: {exc!s}")
                failed_umos.append(target_umo)

        return {
            "message": f"已更新 {success_count} 个会话备注",
            "success_count": success_count,
            "failed_count": len(failed_umos),
            "failed_umos": failed_umos,
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

        override_paths = {}
        remove_override_paths = []
        if rule_key == "session_service_config" and isinstance(rule_value, dict):
            if "llm_enabled" in rule_value:
                override_paths["provider_settings.enable"] = bool(
                    rule_value["llm_enabled"]
                )
            if "tts_enabled" in rule_value:
                override_paths["provider_tts_settings.enable"] = bool(
                    rule_value["tts_enabled"]
                )
            if "persona_id" in rule_value:
                override_paths["provider_settings.default_personality"] = (
                    rule_value.get("persona_id") or ""
                )
            if "session_enabled" in rule_value:
                if rule_value["session_enabled"] is False:
                    override_paths["platform_settings.id_blacklist"] = [umo]
                else:
                    remove_override_paths.append("platform_settings.id_blacklist")
            if "custom_name" in rule_value:
                custom_name = str(rule_value.get("custom_name") or "").strip()
                alias = await self.db_helper.get_umo_alias(umo)
                await self.db_helper.upsert_umo_alias(
                    umo,
                    alias.creator_sender_id if alias else "",
                    alias.auto_name if alias else None,
                    custom_name or None,
                )
        elif rule_key == "session_plugin_config" and isinstance(rule_value, dict):
            disabled_plugins = rule_value.get("disabled_plugins")
            if isinstance(disabled_plugins, list):
                override_paths["plugin_disabled_set"] = disabled_plugins
        elif rule_key == "kb_config" and isinstance(rule_value, dict):
            if "top_k" in rule_value:
                override_paths["kb_final_top_k"] = rule_value["top_k"]
            kb_ids = rule_value.get("kb_ids")
            if isinstance(kb_ids, list):
                override_paths["kb_names"] = [
                    str(kb_id) for kb_id in kb_ids if str(kb_id).strip()
                ]
        else:
            provider_path_map = {
                f"provider_perf_{ProviderType.CHAT_COMPLETION.value}": (
                    "provider_settings.default_provider_id"
                ),
                f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}": (
                    "provider_stt_settings.provider_id"
                ),
                f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}": (
                    "provider_tts_settings.provider_id"
                ),
            }
            if rule_key in provider_path_map and rule_value:
                override_paths[provider_path_map[rule_key]] = rule_value

        if override_paths:
            await self.core_lifecycle.astrbot_config_mgr.update_conf_overrides(
                umo,
                override_paths,
            )
        if remove_override_paths:
            await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                umo,
                remove_override_paths,
            )
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
            if rule_key == "session_service_config":
                await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                    umo,
                    [
                        "provider_settings.enable",
                        "provider_tts_settings.enable",
                        "provider_settings.default_personality",
                        "platform_settings.id_blacklist",
                    ],
                )
                alias = await self.db_helper.get_umo_alias(umo)
                if alias:
                    await self.db_helper.upsert_umo_alias(
                        umo,
                        alias.creator_sender_id,
                        alias.auto_name,
                        None,
                    )
            elif rule_key == "session_plugin_config":
                await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                    umo,
                    ["plugin_disabled_set"],
                )
            elif rule_key == "kb_config":
                await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                    umo,
                    ["kb_names", "kb_final_top_k"],
                )
            else:
                provider_path_map = {
                    f"provider_perf_{ProviderType.CHAT_COMPLETION.value}": (
                        "provider_settings.default_provider_id"
                    ),
                    f"provider_perf_{ProviderType.SPEECH_TO_TEXT.value}": (
                        "provider_stt_settings.provider_id"
                    ),
                    f"provider_perf_{ProviderType.TEXT_TO_SPEECH.value}": (
                        "provider_tts_settings.provider_id"
                    ),
                }
                if rule_key in provider_path_map:
                    await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                        umo,
                        [provider_path_map[rule_key]],
                    )
            return {"message": f"规则 {rule_key} 已删除", "umo": umo}

        await sp.clear_async("umo", umo)
        alias = await self.db_helper.get_umo_alias(umo)
        if alias:
            await self.db_helper.upsert_umo_alias(
                umo,
                alias.creator_sender_id,
                alias.auto_name,
                None,
            )
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
        if rule_key and rule_key not in AVAILABLE_SESSION_RULE_KEYS:
            raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")

        success_count = 0
        failed_umos = []
        for umo in umos:
            try:
                if rule_key:
                    await self.delete_session_rule({"umo": umo, "rule_key": rule_key})
                else:
                    await self.delete_session_rule({"umo": umo})
                success_count += 1
            except Exception as exc:
                logger.error(f"删除 umo {umo} 的规则失败: {exc!s}")
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

            custom_name = svc_config.get("custom_name", "") if svc_config else ""
            session_enabled = (
                svc_config.get("session_enabled", True) if svc_config else True
            )
            llm_enabled = svc_config.get("llm_enabled", True) if svc_config else True
            tts_enabled = svc_config.get("tts_enabled", True) if svc_config else True

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
        platforms = list({u["platform"] for u in umos_with_status})
        provider_manager = self.core_lifecycle.provider_manager

        return {
            "sessions": paginated,
            "total": total,
            "page": page,
            "page_size": page_size,
            "platforms": platforms,
            "available_chat_providers": self._serialize_provider_insts(
                getattr(provider_manager, "provider_insts", [])
            ),
            "available_tts_providers": self._serialize_provider_insts(
                getattr(provider_manager, "tts_provider_insts", [])
            ),
            "available_stt_providers": self._serialize_provider_insts(
                getattr(provider_manager, "stt_provider_insts", [])
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

        success_count = 0
        failed_umos = []

        for umo in umos:
            try:
                override_paths = {}
                if llm_enabled is not None:
                    override_paths["provider_settings.enable"] = bool(llm_enabled)
                if tts_enabled is not None:
                    override_paths["provider_tts_settings.enable"] = bool(tts_enabled)
                if session_enabled is not None:
                    if session_enabled is False:
                        override_paths["platform_settings.id_blacklist"] = [umo]
                    else:
                        await self.core_lifecycle.astrbot_config_mgr.remove_conf_overrides(
                            umo,
                            ["platform_settings.id_blacklist"],
                        )
                if override_paths:
                    await self.core_lifecycle.astrbot_config_mgr.update_conf_overrides(
                        umo,
                        override_paths,
                    )
                success_count += 1
            except Exception as exc:
                logger.error(f"更新 {umo} 服务状态失败: {exc!s}")
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

        success_count = 0
        failed_umos = []
        provider_manager = self.core_lifecycle.provider_manager

        for umo in umos:
            try:
                await provider_manager.set_provider(
                    provider_id=provider_id,
                    provider_type=provider_type_map[provider_type],
                    umo=umo,
                )
                success_count += 1
            except Exception as exc:
                logger.error(f"更新 {umo} Provider 失败: {exc!s}")
                failed_umos.append(umo)

        return {
            "message": f"已更新 {success_count} 个会话的 {provider_type} 为 {provider_id}",
            "success_count": success_count,
            "failed_count": len(failed_umos),
            "failed_umos": failed_umos,
        }

    def get_groups(self) -> dict:
        return sp.get("session_groups", {})

    def save_groups(self, groups: dict) -> None:
        sp.put("session_groups", groups)

    def list_groups(self) -> dict:
        groups = self.get_groups()
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

    def create_group(self, data: object) -> dict:
        payload = self._payload(data)
        name = str(payload.get("name", "")).strip()
        umos = payload.get("umos", [])

        if not name:
            raise SessionManagementServiceError("分组名称不能为空")

        groups = self.get_groups()
        group_id = str(uuid.uuid4())[:8]
        groups[group_id] = {
            "name": name,
            "umos": umos,
        }
        self.save_groups(groups)

        return {
            "message": f"分组 '{name}' 创建成功",
            "group": {
                "id": group_id,
                "name": name,
                "umos": umos,
                "umo_count": len(umos),
            },
        }

    def update_group(self, data: object) -> dict:
        payload = self._payload(data)
        group_id = payload.get("id") or payload.get("group_id")
        name = payload.get("name")
        umos = payload.get("umos")
        add_umos = payload.get("add_umos", [])
        remove_umos = payload.get("remove_umos", [])

        if not group_id:
            raise SessionManagementServiceError("分组 ID 不能为空")

        groups = self.get_groups()
        if group_id not in groups:
            raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")

        group = groups[group_id]
        if name is not None:
            group["name"] = name.strip()

        if umos is not None:
            group["umos"] = umos
        else:
            current_umos = set(group.get("umos", []))
            if add_umos:
                current_umos.update(add_umos)
            if remove_umos:
                current_umos.difference_update(remove_umos)
            group["umos"] = list(current_umos)

        self.save_groups(groups)

        return {
            "message": f"分组 '{group['name']}' 更新成功",
            "group": {
                "id": group_id,
                "name": group["name"],
                "umos": group["umos"],
                "umo_count": len(group["umos"]),
            },
        }

    def delete_group(self, data: object) -> dict:
        payload = self._payload(data)
        group_id = payload.get("id") or payload.get("group_id")

        if not group_id:
            raise SessionManagementServiceError("分组 ID 不能为空")

        groups = self.get_groups()
        if group_id not in groups:
            raise SessionManagementServiceError(f"分组 '{group_id}' 不存在")

        group_name = groups[group_id].get("name", group_id)
        del groups[group_id]
        self.save_groups(groups)
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
