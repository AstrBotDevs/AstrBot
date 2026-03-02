from __future__ import annotations
from astrbot.core.lang import t

import os
from typing import Any

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.string_utils import normalize_and_dedupe_strings

from .image_refs import IMAGE_EXTENSIONS, get_existing_local_path, normalize_image_ref
from .onebot_client import OneBotClient


def _build_image_id_candidates(image_ref: str) -> list[str]:
    candidates: list[str] = [image_ref]
    base_name, ext = os.path.splitext(image_ref)
    if ext and base_name and base_name not in candidates:
        if ext.lower() in IMAGE_EXTENSIONS:
            candidates.append(base_name)
    return candidates


def _build_image_resolve_actions(
    event: AstrMessageEvent,
    image_ref: str,
) -> list[tuple[str, dict[str, Any]]]:
    actions: list[tuple[str, dict[str, Any]]] = []
    candidates = _build_image_id_candidates(image_ref)

    for candidate in candidates:
        actions.extend(
            [
                ("get_image", {"file": candidate}),
                ("get_image", {"file_id": candidate}),
                ("get_image", {"id": candidate}),
                ("get_image", {"image": candidate}),
                ("get_file", {"file_id": candidate}),
                ("get_file", {"file": candidate}),
            ]
        )

    try:
        group_id = event.get_group_id()
    except Exception:
        group_id = None
    group_id_value = group_id
    if isinstance(group_id, str) and group_id.isdigit():
        group_id_value = int(group_id)

    if group_id_value:
        for candidate in candidates:
            actions.append(
                (
                    "get_group_file_url",
                    {"group_id": group_id_value, "file_id": candidate},
                )
            )
    for candidate in candidates:
        actions.append(("get_private_file_url", {"file_id": candidate}))

    return actions


class ImageResolver:
    def __init__(
        self,
        event: AstrMessageEvent,
        onebot_client: OneBotClient | None = None,
    ):
        self._event = event
        self._client = onebot_client or OneBotClient(event)

    async def resolve_for_llm(self, image_refs: list[str]) -> list[str]:
        resolved: list[str] = []
        unresolved: list[str] = []

        for image_ref in normalize_and_dedupe_strings(image_refs):
            normalized = normalize_image_ref(image_ref)
            if normalized:
                resolved.append(normalized)
            elif get_existing_local_path(image_ref):
                # Drop non-image local paths instead of treating them as remote IDs.
                logger.debug(
                    t("msg-6dfa6994", res=image_ref[:128]),
                )
            else:
                unresolved.append(image_ref)

        for image_ref in unresolved:
            resolved_ref = await self._resolve_one(image_ref)
            if resolved_ref:
                resolved.append(resolved_ref)

        return normalize_and_dedupe_strings(resolved)

    async def _resolve_one(self, image_ref: str) -> str | None:
        resolved = normalize_image_ref(image_ref)
        if resolved:
            return resolved

        actions = _build_image_resolve_actions(self._event, image_ref)
        for action, params in actions:
            data = await self._client.call(
                action,
                params,
                warn_on_all_failed=False,
                unwrap_data=True,
            )
            if not isinstance(data, dict):
                continue

            url = data.get("url")
            if isinstance(url, str):
                normalized = normalize_image_ref(url)
                if normalized:
                    return normalized

            file_value = data.get("file")
            if isinstance(file_value, str):
                normalized = normalize_image_ref(file_value)
                if normalized:
                    return normalized

        logger.warning(
            t("msg-9326ec62", res=image_ref[:128], res_2=len(actions)),
        )
        return None
