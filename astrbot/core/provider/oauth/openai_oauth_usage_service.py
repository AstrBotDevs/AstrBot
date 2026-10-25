"""Profile-aware access to the read-only Codex OAuth usage reader."""

from collections.abc import Mapping
from copy import deepcopy

_BUILTIN_OAUTH_PROVIDER_TYPE = "openai_oauth_chat_completion"
_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
_CREDENTIAL_FIELDS = {
    "oauth_access_token",
    "oauth_refresh_token",
    "oauth_expires_at",
    "oauth_account_email",
}


class OpenAIOAuthUsageService:
    def __init__(self, context, reader):
        self.context = context
        self.reader = reader
        self.closed = False

    def _check(self, event, origin, expected_target=None):
        if self.closed:
            return "closed", ""
        if event.unified_msg_origin != origin:
            return "authorization_changed", ""
        config = self.context.get_config(umo=origin)
        provider_settings = config.get("provider_settings", {})
        if not isinstance(provider_settings, Mapping):
            provider_settings = {}
        settings = provider_settings.get("codex_oauth_usage", {})
        if (
            not isinstance(settings, Mapping)
            or settings.get("enabled", True) is not True
        ):
            return "disabled", ""
        admin_ids = config.get("admins_id")
        sender_id = str(event.get_sender_id() or "")
        if (
            not event.is_admin()
            or not isinstance(admin_ids, list)
            or not sender_id
            or sender_id not in admin_ids
        ):
            return "not_admin", ""
        source_id = settings.get("source_id", "")
        legacy_provider_id = settings.get("provider_id", "")
        if source_id is None:
            source_id = ""
        if legacy_provider_id is None:
            legacy_provider_id = ""
        if not isinstance(source_id, str):
            return "source_unavailable", ""
        source_id = source_id.strip()
        if source_id:
            legacy_provider_id = ""
        elif not isinstance(legacy_provider_id, str):
            return "source_unavailable", ""
        target = (source_id, "" if source_id else legacy_provider_id.strip())
        if expected_target is not None and target != expected_target:
            return "authorization_changed", ""
        return None, target

    @staticmethod
    def _source_snapshot(source: Mapping) -> dict:
        return deepcopy(
            {
                key: value
                for key, value in source.items()
                if key not in _CREDENTIAL_FIELDS
            }
        )

    def _resolve_source(
        self, target: tuple[str, str]
    ) -> tuple[str | None, Mapping | None]:
        """Resolve a source ID from the current manager configuration.

        Args:
            target: Explicit source ID and optional legacy model ID.

        Returns:
            A sanitized failure status and source, or ``(None, source)``.
        """
        manager = self.context.provider_manager
        sources = manager.provider_sources_config
        if not isinstance(sources, list):
            return "source_unavailable", None
        source_id, legacy_provider_id = target
        if not source_id and legacy_provider_id:
            providers = manager.providers_config
            if not isinstance(providers, list):
                return "source_not_found", None
            matches = [
                item
                for item in providers
                if isinstance(item, Mapping) and item.get("id") == legacy_provider_id
            ]
            if len(matches) > 1:
                return "source_ambiguous", None
            if not matches:
                return "source_not_found", None
            source_id = matches[0].get("provider_source_id")
            if not isinstance(source_id, str) or not source_id.strip():
                return "source_not_found", None
        if not source_id:
            eligible = [
                item
                for item in sources
                if isinstance(item, Mapping)
                and item.get("type") == _BUILTIN_OAUTH_PROVIDER_TYPE
                and item.get("auth_mode") == "openai_oauth"
                and item.get("enable", True) is True
            ]
            if not eligible:
                return "source_not_found", None
            if len(eligible) > 1:
                return "source_ambiguous", None
            source_id = eligible[0].get("id")
            if not isinstance(source_id, str) or not source_id.strip():
                return "source_unavailable", None
        matches = [
            item
            for item in sources
            if isinstance(item, Mapping) and item.get("id") == source_id
        ]
        if not matches:
            return "source_not_found", None
        if len(matches) > 1:
            return "source_ambiguous", None
        source = matches[0]
        if (
            source.get("type") != _BUILTIN_OAUTH_PROVIDER_TYPE
            or source.get("auth_mode") != "openai_oauth"
            or source.get("enable", True) is not True
        ):
            return "source_unavailable", None
        if (
            str(source.get("api_base") or _CODEX_BASE_URL).rstrip("/")
            != _CODEX_BASE_URL
        ):
            return "unsupported_endpoint", None
        return None, source

    def _source_still_authorized(
        self,
        target: tuple[str, str],
        source: Mapping,
        state,
        source_snapshot: dict,
        account_id: str,
    ) -> bool:
        """Check source identity, configuration, and account after an await.

        Args:
            target: Initial source selection settings.
            source: Initially selected source object.
            state: Initially selected shared credential state.
            source_snapshot: Non-token source configuration before the request.
            account_id: Account ID before the request.

        Returns:
            Whether the original source and account remain authorized.
        """
        status, current = self._resolve_source(target)
        if (
            status
            or current is not source
            or self._source_snapshot(current) != source_snapshot
        ):
            return False
        current_state = self.context.provider_manager.get_openai_oauth_shared_state(
            source["id"], current
        )
        return (
            current_state is state
            and str(current_state.snapshot().get("oauth_account_id") or "")
            == account_id
            and str(current.get("oauth_account_id") or "") == account_id
        )

    async def run(self, event):
        try:
            origin = event.unified_msg_origin
            status, target = self._check(event, origin)
            if status:
                return {"status": status}

            status, source = self._resolve_source(target)
            if status:
                return {"status": status}
            assert source is not None
            state = self.context.provider_manager.get_openai_oauth_shared_state(
                source["id"], source
            )
            source_snapshot = self._source_snapshot(source)
            account_id = str(state.snapshot().get("oauth_account_id") or "")
            if str(source.get("oauth_account_id") or "") != account_id:
                return {"status": "authorization_changed"}
            status, _ = self._check(event, origin, target)
            if status:
                return {"status": status}
            if not self._source_still_authorized(
                target, source, state, source_snapshot, account_id
            ):
                return {"status": "authorization_changed"}

            result = await self.reader.read_source(source, state)
            status, _ = self._check(event, origin, target)
            if status:
                return {"status": status}
            if not self._source_still_authorized(
                target, source, state, source_snapshot, account_id
            ):
                return {"status": "authorization_changed"}
            return result
        except Exception:
            # Never expose account identifiers or upstream response bodies.
            return {"status": "unavailable"}

    async def close(self):
        self.closed = True
        await self.reader.close()
