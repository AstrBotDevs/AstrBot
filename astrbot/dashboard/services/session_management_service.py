from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from astrbot.core import logger, sp
from astrbot.core.config_bindings import BINDING_KEY
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import ConversationV2, Preference, UmoAlias, UmoSender
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.session_overrides import (
    OVERRIDE_KEY,
    OVERRIDE_TYPES,
    update_overrides,
)
from astrbot.core.umo_alias import (
    build_umo_alias_map,
    normalize_umo_name,
    parse_umo,
    serialize_umo_alias,
)

AVAILABLE_SESSION_RULE_KEYS = [OVERRIDE_KEY]


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
        """List distinct UMOs by their latest existing record update.

        Returns:
            UMOs ordered by the newest conversation, alias or sender update,
            with the raw UMO ascending as a stable tie breaker.
        """
        sources = (
            select(
                col(ConversationV2.user_id).label("umo"),
                col(ConversationV2.updated_at).label("updated_at"),
            )
            .union_all(
                select(UmoSender.umo, UmoSender.updated_at),
                select(UmoAlias.umo, UmoAlias.updated_at),
            )
            .subquery()
        )
        async with self.db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(sources.c.umo)
                .where(sources.c.umo.is_not(None), sources.c.umo != "")
                .group_by(sources.c.umo)
                .order_by(func.max(sources.c.updated_at).desc(), sources.c.umo.asc())
            )
            return [str(row[0]) for row in result.fetchall()]

    async def get_umo_alias_map(self, umos: list[str]) -> dict:
        return build_umo_alias_map(await self.db_helper.get_umo_aliases(umos))

    def build_umo_info(self, umo: str | None, alias_map: dict) -> dict:
        umo_str = umo or ""
        return {
            "umo": umo_str,
            **parse_umo(umo_str),
            **serialize_umo_alias(alias_map.get(umo_str), umo_str),
        }

    async def list_active_umos(self, platform_id: str = "") -> dict:
        """List known sessions, optionally restricted to one platform instance.

        Args:
            platform_id: Exact platform instance ID, or empty for all instances.

        Returns:
            Raw UMOs and their display metadata.
        """
        umos = await self.list_known_umos()
        if platform_id:
            umos = [umo for umo in umos if umo.partition(":")[0] == platform_id]
        alias_map = await self.get_umo_alias_map(umos)
        return {
            "umos": umos,
            "umo_infos": [self.build_umo_info(umo, alias_map) for umo in umos],
        }

    async def list_senders(
        self,
        search: str = "",
        limit: int = 50,
        sender_ids: list[str] | None = None,
        page: int = 1,
    ) -> dict:
        """Find sender IDs with names and source session metadata.

        Args:
            search: Substring matched against sender and session names or IDs.
            limit: Maximum number of results per page.
            sender_ids: Resolve the latest record for each exact sender ID.
            page: One-based page of deduplicated results.

        Returns:
            Sender suggestions, current page, and whether another page exists.
        """
        records = await self.db_helper.get_umo_senders(
            search.strip(), limit + 1, sender_ids, offset=(page - 1) * limit
        )
        return {
            "page": page,
            "has_more": len(records) > limit,
            "senders": [
                {
                    "sender_id": sender.sender_id,
                    "sender_name": sender.sender_name,
                    **self.build_umo_info(
                        sender.umo, {sender.umo: alias} if alias else {}
                    ),
                }
                for sender, alias in records[:limit]
            ],
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

    async def get_umo_bindings(
        self,
        page: int = 1,
        page_size: int = 10,
        search: str = "",
    ) -> tuple[dict, int]:
        """List stored session bindings, including profile-only assignments.

        Args:
            page: One-based page number.
            page_size: Maximum number of bindings to return.
            search: Optional case-insensitive UMO or alias filter.

        Returns:
            A mapping of UMOs to bindings and the total matching count.
        """
        umo_rules = {}
        async with self.db_helper.get_db() as session:
            session: AsyncSession
            result = await session.execute(
                select(Preference).where(
                    col(Preference.scope) == "umo",
                    col(Preference.key) == BINDING_KEY,
                )
            )
            prefs = result.scalars().all()
            for pref in prefs:
                umo_id = pref.scope_id
                umo_rules[umo_id] = pref.value["val"]

        # Present legacy exact routes as sessions without changing their current resolution.
        acm = self.core_lifecycle.astrbot_config_mgr
        for pattern in acm.ucr.umop_to_conf_id:
            parts = pattern.split(":", 2)
            if len(parts) != 3 or any(
                not part or any(char in part for char in "*?[") for part in parts
            ):
                continue
            try:
                MessageSession.from_str(pattern)
            except (ValueError, KeyError):
                continue
            binding = umo_rules.get(pattern, {})
            if binding.get("profile_id") is None:
                umo_rules[pattern] = {
                    **binding,
                    "profile_id": acm.get_conf_info(pattern)["id"],
                }

        if search:
            alias_map = await self.get_umo_alias_map(list(umo_rules.keys()))
            search_lower = search.lower()
            filtered_rules = {}
            for umo_id, rules in umo_rules.items():
                if search_lower in umo_id.lower():
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
    ) -> dict:
        page, page_size = self._normalize_page(page, page_size, default_page_size=10)
        umo_rules, total = await self.get_umo_bindings(
            page=page,
            page_size=page_size,
            search=search,
        )

        alias_map = await self.get_umo_alias_map(list(umo_rules.keys()))
        rules_list = [
            {
                "rules": {OVERRIDE_KEY: rules.get("overrides", {})},
                "profile_id": rules.get("profile_id"),
                "profile": self.core_lifecycle.astrbot_config_mgr.get_conf_info(umo),
                **self.build_umo_info(umo, alias_map),
            }
            for umo, rules in umo_rules.items()
        ]

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

        return {
            "rules": rules_list,
            "total": total,
            "page": page,
            "page_size": page_size,
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

    async def get_session_overrides(
        self, umo: str, profile_id: str | None = None
    ) -> dict:
        """Return editable session values and their inheritance source.

        Args:
            umo: Exact unified message origin.
            profile_id: Optional preview profile; empty string previews following routing.

        Returns:
            Profile metadata, explicit overrides, inherited values and alias.

        Raises:
            SessionManagementServiceError: If the UMO is invalid.
        """
        try:
            MessageSession.from_str(umo)
        except Exception as exc:
            raise SessionManagementServiceError("Invalid session origin") from exc
        acm = self.core_lifecycle.astrbot_config_mgr
        binding = await sp.session_get(umo, BINDING_KEY, {}) or {}
        routing_profile = acm.get_conf_info(umo, follow_route=True)
        profiles = acm.get_conf_list()
        profile = acm.get_conf_info(umo)
        if profile_id is not None:
            profile = (
                routing_profile
                if profile_id == ""
                else next((item for item in profiles if item["id"] == profile_id), None)
            )
            if profile is None:
                raise SessionManagementServiceError("Unknown configuration profile")
        base = acm.confs.get(profile["id"], acm.default_conf)
        values = {}
        for path in OVERRIDE_TYPES:
            value = base
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            values[path] = value
        aliases = await self.get_umo_alias_map([umo])
        return {
            **self.build_umo_info(umo, aliases),
            "profile": profile,
            "profile_id": binding.get("profile_id"),
            "routing_profile": routing_profile,
            "profiles": profiles,
            "runtime": base.get("agent", {}).get("runtime", "astrbot"),
            "inherited": values,
            "overrides": binding.get("overrides", {}),
        }

    async def update_session_rule(self, data: object) -> dict:
        """Patch session configuration and optionally update its display alias.

        Args:
            data: UMO, config_overrides rule key, changed paths and optional alias.

        Returns:
            The updated session editor data.

        Raises:
            SessionManagementServiceError: If the payload is invalid.
        """
        payload = self._payload(data)
        umo = payload.get("umo")
        if payload.get("rule_key") != OVERRIDE_KEY:
            raise SessionManagementServiceError(
                "Use config_overrides for session settings"
            )
        changes = payload.get("rule_value")
        if not isinstance(changes, dict):
            raise SessionManagementServiceError("Overrides must be an object")
        await self.get_session_overrides(umo)
        profile_id = payload.get("profile_id")
        if (
            profile_id is not None
            and profile_id not in self.core_lifecycle.astrbot_config_mgr.confs
        ):
            raise SessionManagementServiceError("Unknown configuration profile")
        try:
            await update_overrides(
                umo,
                changes,
                profile_id=profile_id,
                update_profile="profile_id" in payload,
            )
        except ValueError as exc:
            raise SessionManagementServiceError(str(exc)) from exc
        if "profile_id" in payload:
            # An explicit edit replaces the legacy exact route with the session binding.
            await self.core_lifecycle.astrbot_config_mgr.ucr.delete_route(umo)
        if "user_alias" in payload:
            aliases = await self.db_helper.get_umo_aliases([umo])
            alias = aliases[0] if aliases else None
            await self.db_helper.upsert_umo_alias(
                umo,
                alias.creator_sender_id if alias else "",
                alias.auto_name if alias else None,
                normalize_umo_name(payload["user_alias"]) or None,
            )
        return await self.get_session_overrides(umo)

    async def delete_session_rule(self, data: object) -> dict:
        payload = self._payload(data)
        umo = payload.get("umo")
        rule_key = payload.get("rule_key")

        if not umo:
            raise SessionManagementServiceError("缺少必要参数: umo")

        if rule_key:
            if rule_key not in [*AVAILABLE_SESSION_RULE_KEYS, BINDING_KEY]:
                raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")
            if rule_key == BINDING_KEY:
                await self.core_lifecycle.astrbot_config_mgr.ucr.delete_route(umo)
            await update_overrides(
                umo, {}, clear_overrides=True, update_profile=rule_key == BINDING_KEY
            )
            return {"message": f"规则 {rule_key} 已删除", "umo": umo}

        await update_overrides(
            umo, {}, clear_overrides=True, update_profile=rule_key == BINDING_KEY
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
        if rule_key and rule_key not in [*AVAILABLE_SESSION_RULE_KEYS, BINDING_KEY]:
            raise SessionManagementServiceError(f"不支持的规则键: {rule_key}")

        success_count = 0
        failed_umos = []
        for umo in umos:
            try:
                if rule_key == BINDING_KEY:
                    await self.core_lifecycle.astrbot_config_mgr.ucr.delete_route(umo)
                await update_overrides(
                    umo,
                    {},
                    clear_overrides=True,
                    update_profile=rule_key == BINDING_KEY,
                )
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

    async def get_groups(self) -> dict:
        groups = await sp.get_async(
            "unknown",
            "unknown",
            "session_groups",
            {},
        )
        return groups if groups is not None else {}

    async def save_groups(self, groups: dict) -> None:
        await sp.put_async("unknown", "unknown", "session_groups", groups)

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
        name = str(payload.get("name", "")).strip()
        umos = payload.get("umos", [])

        if not name:
            raise SessionManagementServiceError("分组名称不能为空")

        groups = await self.get_groups()
        group_id = str(uuid.uuid4())[:8]
        groups[group_id] = {
            "name": name,
            "umos": umos,
        }
        await self.save_groups(groups)

        return {
            "message": f"分组 '{name}' 创建成功",
            "group": {
                "id": group_id,
                "name": name,
                "umos": umos,
                "umo_count": len(umos),
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
