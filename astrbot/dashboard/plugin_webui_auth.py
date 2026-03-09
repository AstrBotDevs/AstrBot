from urllib.parse import unquote

from quart import request

PLUGIN_WEBUI_CONTENT_PREFIX = "/api/plugin/webui/content/"
PLUGIN_WEBUI_BRIDGE_PATH = "/api/plugin/webui/bridge-sdk.js"
PLUGIN_WEBUI_TOKEN_TYPE = "plugin_webui_asset"


class PluginWebUIAuth:
    @staticmethod
    def is_protected_path(path: str) -> bool:
        return path.startswith(PLUGIN_WEBUI_CONTENT_PREFIX) or path.startswith(
            PLUGIN_WEBUI_BRIDGE_PATH
        )

    @staticmethod
    def is_asset_token(payload: dict) -> bool:
        return payload.get("token_type") == PLUGIN_WEBUI_TOKEN_TYPE

    @staticmethod
    def extract_asset_token() -> str | None:
        query_asset_token = request.args.get("asset_token", "").strip()
        return query_asset_token or None

    @staticmethod
    def extract_plugin_name_from_path(path: str) -> str | None:
        if not path.startswith(PLUGIN_WEBUI_CONTENT_PREFIX):
            return None
        remainder = path[len(PLUGIN_WEBUI_CONTENT_PREFIX) :]
        plugin_part = remainder.split("/", 1)[0] if remainder else ""
        return unquote(plugin_part) if plugin_part else None

    @classmethod
    def is_scope_valid(cls, payload: dict, path: str) -> bool:
        if not cls.is_protected_path(path):
            return False
        if path.startswith(PLUGIN_WEBUI_BRIDGE_PATH):
            return True

        token_plugin_name = payload.get("plugin_name")
        request_plugin_name = cls.extract_plugin_name_from_path(path)
        if (
            not isinstance(token_plugin_name, str)
            or not token_plugin_name
            or not request_plugin_name
        ):
            return False
        return token_plugin_name == request_plugin_name
