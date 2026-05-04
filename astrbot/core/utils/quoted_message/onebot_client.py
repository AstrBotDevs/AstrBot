from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Protocol

from astrbot import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .settings import SETTINGS, QuotedMessageParserSettings


def _unwrap_action_response(ret: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(ret, dict):
        return {}
    data = ret.get("data")
    if isinstance(data, dict):
        return data
    return ret


class CallAction(Protocol):
    def __call__(self, action: str, **params: Any) -> Awaitable[Any] | Any: ...


class OneBotClient:
    def __init__(
        self,
        event: AstrMessageEvent,
        settings: QuotedMessageParserSettings = SETTINGS,
    ):
        self._call_action = self._resolve_call_action(event)
        self._settings = settings

    @staticmethod
    def _resolve_call_action(event: AstrMessageEvent) -> CallAction | None:
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            return None
        return call_action

    async def _call_action_try_params(
        self,
        action: str,
        params_list: list[dict[str, Any]],
        *,
        warn_on_all_failed: bool | None = None,
    ) -> dict[str, Any] | None:
        if self._call_action is None:
            return None
        if warn_on_all_failed is None:
            warn_on_all_failed = self._settings.warn_on_action_failure

        last_error: Exception | None = None
        last_params: dict[str, Any] | None = None
        for params in params_list:
            try:
                result = await self._call_action(action, **params)
                if isinstance(result, dict):
                    return result
            except Exception as exc:
                last_error = exc
                last_params = params
                logger.debug(
                    "quoted_message_parser: action %s failed with params %s: %s",
                    action,
                    {k: str(v)[:64] for k, v in params.items()},
                    exc,
                )
        if warn_on_all_failed and last_error is not None:
            logger.warning(
                "quoted_message_parser: all attempts failed for action %s, "
                "last_params=%s, error=%s",
                action,
                (
                    {k: str(v)[:64] for k, v in last_params.items()}
                    if isinstance(last_params, dict)
                    else None
                ),
                last_error,
            )
        return None

    async def call(
        self,
        action: str,
        params: dict[str, Any],
        *,
        warn_on_all_failed: bool = False,
        unwrap_data: bool = True,
    ) -> dict[str, Any] | None:
        ret = await self._call_action_try_params(
            action,
            [params],
            warn_on_all_failed=warn_on_all_failed,
        )
        if not unwrap_data:
            return ret
        return _unwrap_action_response(ret)

    async def _call_action_compat(
        self,
        action: str,
        message_id: str | int,
    ) -> dict[str, Any] | None:
        message_id_str = str(message_id).strip()
        if not message_id_str:
            return None

        params_list: list[dict[str, Any]] = [
            {"message_id": message_id_str},
            {"id": message_id_str},
        ]
        if message_id_str.isdigit():
            int_id = int(message_id_str)
            params_list.extend([{"message_id": int_id}, {"id": int_id}])
        return await self._call_action_try_params(action, params_list)

    async def get_msg(self, message_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_msg", message_id)

    async def get_forward_msg(self, forward_id: str | int) -> dict[str, Any] | None:
        return await self._call_action_compat("get_forward_msg", forward_id)
