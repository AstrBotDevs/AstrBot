import asyncio
from typing import Any

OPENAI_OAUTH_CREDENTIAL_FIELDS = (
    "auth_mode",
    "oauth_provider",
    "oauth_access_token",
    "oauth_refresh_token",
    "oauth_expires_at",
    "oauth_account_email",
    "oauth_account_id",
)

_VERSION_FIELDS = {
    "oauth_access_token",
    "oauth_refresh_token",
    "oauth_expires_at",
    "oauth_account_id",
}


class OpenAIOAuthSharedState:
    """Runtime credentials shared by models from one OpenAI OAuth source."""

    def __init__(self, source_id: str, source_config: dict[str, Any]) -> None:
        self.source_id = source_id
        self.refresh_lock = asyncio.Lock()
        self.version = 0
        self._credentials: dict[str, Any] = dict.fromkeys(
            OPENAI_OAUTH_CREDENTIAL_FIELDS,
            "",
        )
        self.replace(source_config)

    def apply(self, patch: dict[str, Any]) -> int:
        version_changed = False
        for key in OPENAI_OAUTH_CREDENTIAL_FIELDS:
            if key not in patch:
                continue
            value = patch[key]
            if key in _VERSION_FIELDS and self._credentials.get(key) != value:
                version_changed = True
            self._credentials[key] = value
        if version_changed:
            self.version += 1
        return self.version

    def replace(self, source_config: dict[str, Any]) -> int:
        next_credentials = {
            key: source_config.get(key, "") for key in OPENAI_OAUTH_CREDENTIAL_FIELDS
        }
        if any(
            self._credentials.get(key) != next_credentials[key]
            for key in _VERSION_FIELDS
        ):
            self.version += 1
        self._credentials = next_credentials
        return self.version

    def snapshot(self) -> dict[str, Any]:
        return dict(self._credentials)

    def versioned_snapshot(self) -> tuple[int, dict[str, Any]]:
        return self.version, dict(self._credentials)
