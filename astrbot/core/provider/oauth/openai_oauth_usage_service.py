"""Profile-aware access to the read-only Codex OAuth usage reader."""

from collections.abc import Mapping

_BUILTIN_OAUTH_PROVIDER_TYPE = "openai_oauth_chat_completion"


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
        target = str(settings.get("provider_id") or "").strip()
        if expected_target is not None and target != expected_target:
            return "authorization_changed", ""
        return None, target

    async def run(self, event):
        try:
            origin = event.unified_msg_origin
            status, target = self._check(event, origin)
            if status:
                return {"status": status}

            if target:
                provider = self.context.get_provider_by_id(target)
            else:
                provider = await self.context.get_using_provider_async(origin)
            status, _ = self._check(event, origin, target)
            if status:
                return {"status": status}
            if provider is None:
                return {"status": "provider_not_found"}
            provider_config = getattr(provider, "provider_config", None)
            if (
                not isinstance(provider_config, Mapping)
                or provider_config.get("type") != _BUILTIN_OAUTH_PROVIDER_TYPE
            ):
                return {"status": "not_oauth_provider"}

            result = await self.reader.read(provider)
            status, _ = self._check(event, origin, target)
            if status:
                return {"status": status}
            return result
        except Exception:
            # Never expose account identifiers or upstream response bodies.
            return {"status": "unavailable"}

    async def close(self):
        self.closed = True
        await self.reader.close()
