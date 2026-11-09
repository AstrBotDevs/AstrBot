PLUGIN_PAGE_BRIDGE_PATH = "/api/plugin/page/bridge-sdk.js"
PLUGIN_PAGE_TOKEN_TYPE = "plugin_page_asset"


class PluginPageAuth:
    """Auth helpers for plugin view requests handled by the auth middleware.

    View assets authenticate through scoped path tokens validated by the v1
    route dependency (v1 paths bypass this middleware). Only the shared
    bridge SDK script still authenticates here, via a query token.
    """

    @staticmethod
    def is_protected_path(path: str) -> bool:
        return path.startswith(PLUGIN_PAGE_BRIDGE_PATH)

    @staticmethod
    def is_asset_token(payload: dict) -> bool:
        return payload.get("token_type") == PLUGIN_PAGE_TOKEN_TYPE

    @staticmethod
    def extract_asset_token(query_params) -> str | None:
        query_asset_token = query_params.get("asset_token", "").strip()
        return query_asset_token or None

    @classmethod
    def is_scope_valid(cls, payload: dict, path: str) -> bool:
        # The bridge SDK is shared across views, so any view token may fetch
        # it; every other path rejects scoped asset tokens.
        return cls.is_protected_path(path)
