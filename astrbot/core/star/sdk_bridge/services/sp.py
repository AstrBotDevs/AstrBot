from __future__ import annotations

from typing import Any

from astrbot_sdk.errors import InvalidRequest, NotFound

from astrbot.core import sp


class SpStoreService:
    """Raw SharedPreferences access for legacy plugins (parity facade)."""

    capability_id = "sp.store"

    @staticmethod
    def _entry(pref: Any) -> dict[str, Any]:
        """Serialize one Preference row to a JSON-safe dict."""
        value = pref.value
        return {
            "scope": pref.scope,
            "scope_id": pref.scope_id,
            "key": pref.key,
            "value": value.get("val") if isinstance(value, dict) else value,
        }

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve get/range_get/put/remove/clear against host preferences."""
        scope = payload.get("scope")
        scope_id = payload.get("scope_id")
        key = payload.get("key")
        if operation == "get":
            if not isinstance(scope, str) or not isinstance(scope_id, str) or not key:
                raise InvalidRequest("sp get requires scope, scope_id and key")
            return {
                "value": await sp.get_async(
                    scope, scope_id, str(key), payload.get("default")
                ),
            }
        if operation == "range_get":
            if scope is not None and not isinstance(scope, str):
                raise InvalidRequest("sp range_get scope must be a string or null")
            prefs = await sp.range_get_async(scope, scope_id, key)
            return {"entries": [self._entry(pref) for pref in prefs]}
        if operation == "put":
            if not isinstance(scope, str) or not isinstance(scope_id, str) or not key:
                raise InvalidRequest("sp put requires scope, scope_id and key")
            await sp.put_async(scope, scope_id, str(key), payload.get("value"))
            return {}
        if operation == "remove":
            if not isinstance(scope, str) or not isinstance(scope_id, str) or not key:
                raise InvalidRequest("sp remove requires scope, scope_id and key")
            await sp.remove_async(scope, scope_id, str(key))
            return {}
        if operation == "clear":
            if not isinstance(scope, str) or not isinstance(scope_id, str):
                raise InvalidRequest("sp clear requires scope and scope_id")
            await sp.clear_async(scope, scope_id)
            return {}
        raise NotFound(f"unknown sp operation: {operation}")
