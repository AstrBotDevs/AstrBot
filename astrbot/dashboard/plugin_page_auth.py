from urllib.parse import unquote

from quart import request

PLUGIN_PAGE_CONTENT_PREFIX = "/api/plugin/page/content/"
PLUGIN_PAGE_BRIDGE_PATH = "/api/plugin/page/bridge-sdk.js"
PLUGIN_PAGE_TOKEN_TYPE = "plugin_page_asset"


class PluginPageAuth:
    @staticmethod
    def is_protected_path(path: str) -> bool:
        return path.startswith(PLUGIN_PAGE_CONTENT_PREFIX) or path.startswith(
            PLUGIN_PAGE_BRIDGE_PATH
        )

    @staticmethod
    def is_asset_token(payload: dict) -> bool:
        return payload.get("token_type") == PLUGIN_PAGE_TOKEN_TYPE

    @staticmethod
    def extract_asset_token() -> str | None:
        query_asset_token = request.args.get("asset_token", "").strip()
        return query_asset_token or None

    @staticmethod
    def extract_plugin_name_from_path(path: str) -> str | None:
        if not path.startswith(PLUGIN_PAGE_CONTENT_PREFIX):
            return None
        remainder = path[len(PLUGIN_PAGE_CONTENT_PREFIX) :]
        plugin_part = remainder.split("/", 1)[0] if remainder else ""
        return unquote(plugin_part) if plugin_part else None

    @staticmethod
    def extract_page_name_from_path(path: str) -> str | None:
        if not path.startswith(PLUGIN_PAGE_CONTENT_PREFIX):
            return None
        remainder = path[len(PLUGIN_PAGE_CONTENT_PREFIX) :]
        parts = remainder.split("/", 2)
        page_part = parts[1] if len(parts) > 1 else ""
        return unquote(page_part) if page_part else None

    @classmethod
    def is_scope_valid(cls, payload: dict, path: str) -> bool:
        if not cls.is_protected_path(path):
            return False
        if path.startswith(PLUGIN_PAGE_BRIDGE_PATH):
            return True

        token_plugin_name = payload.get("plugin_name")
        token_page_name = payload.get("page_name")
        request_plugin_name = cls.extract_plugin_name_from_path(path)
        request_page_name = cls.extract_page_name_from_path(path)
        if (
            not isinstance(token_plugin_name, str)
            or not token_plugin_name
            or not isinstance(token_page_name, str)
            or not token_page_name
            or not request_plugin_name
            or not request_page_name
        ):
            return False
        return (
            token_plugin_name == request_plugin_name
            and token_page_name == request_page_name
        )
