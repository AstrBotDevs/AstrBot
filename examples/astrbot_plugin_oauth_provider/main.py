"""Example: one OAuth account shared by an OpenAI-compatible supplier's models."""

import hashlib
import json
import os
from contextlib import AsyncExitStack
from dataclasses import asdict

import httpx
from cryptography.fernet import Fernet

from astrbot.api import AstrBotConfig
from astrbot.api.provider import register_provider_adapter, unregister_provider_adapter
from astrbot.api.provider.oauth import OAuth2Error, OAuth2Session, OAuth2Token
from astrbot.api.star import Context, Star
from astrbot.api.web import error_response, json_response, request
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

PLUGIN_NAME = "astrbot_plugin_oauth_provider"
PROVIDER_TYPE = "plugin_oauth_example"


class OAuthProviderPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
        self.oauth: OAuth2Session | None = None
        self.http: httpx.AsyncClient | None = None
        self.provider_class: type | None = None

    async def initialize(self) -> None:
        """Register the adapter only after validating its OAuth configuration."""
        try:
            self.cipher = Fernet(os.environ["ASTRBOT_OAUTH_STORAGE_KEY"].encode())
        except (KeyError, ValueError):
            raise ValueError("Set a valid ASTRBOT_OAUTH_STORAGE_KEY first.") from None
        settings = {
            key: self.config[key]
            for key in (
                "client_id",
                "authorization_endpoint",
                "token_endpoint",
                "redirect_uri",
                "api_base",
            )
        }
        settings["scopes"] = tuple(self.config.get("scopes", []))
        # Changing the supplier/client must never reuse another account's token.
        self.storage_key = (
            "oauth:"
            + hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        )
        self.http = httpx.AsyncClient(proxy=self.config.get("proxy") or None)
        try:
            self.oauth = OAuth2Session(
                **settings,
                http_client=self.http,
                load_token=self.load_token,
                save_token=self.save_token,
            )
            session = self.oauth
            api_base = settings["api_base"]

            class OAuthProvider(ProviderOpenAIOfficial):
                def __init__(self, provider_config, provider_settings) -> None:
                    config = {
                        **provider_config,
                        "api_base": api_base,
                        # Only satisfies SDK construction; never a real credential.
                        "key": ["oauth-managed"],
                    }
                    config.pop("api_version", None)
                    super().__init__(config, provider_settings)

                def _create_http_client(self, provider_config):
                    client = super()._create_http_client(provider_config)
                    client.event_hooks["request"].append(session.authorize_request)
                    client.follow_redirects = False
                    return client

            self.provider_class = register_provider_adapter(
                PROVIDER_TYPE,
                "OAuth example plugin provider",
                provider_display_name="Plugin OAuth Example",
                default_config_tmpl={
                    "provider": PROVIDER_TYPE,
                    "provider_type": "chat_completion",
                    "api_base": api_base,
                    "key": [],
                },
            )(OAuthProvider)
            self.context.register_web_api(
                f"/{PLUGIN_NAME}/oauth/<action>",
                self.handle_oauth,
                ["POST"],
                "Manage the plugin provider's OAuth account",
            )
        except BaseException:
            await self.terminate()
            raise

    async def load_token(self) -> OAuth2Token | None:
        """Load encrypted credentials from this plugin/account's private KV store.

        Returns:
            Validated credentials, or None when no account is connected.
        """
        encrypted = await self.get_kv_data(self.storage_key, None)
        if encrypted is None:
            return None
        payload = json.loads(self.cipher.decrypt(encrypted.encode()))
        return OAuth2Token(**payload)

    async def save_token(self, token: OAuth2Token | None) -> None:
        """Persist encrypted credentials; the encryption key stays outside KV.

        Args:
            token: Credentials to encrypt, or None to delete them.
        """
        if token is None:
            await self.delete_kv_data(self.storage_key)
        else:
            encrypted = self.cipher.encrypt(json.dumps(asdict(token)).encode())
            await self.put_kv_data(self.storage_key, encrypted.decode())

    async def handle_oauth(self, action: str):
        """Handle explicit Dashboard actions; never accept an owner from JSON.

        Args:
            action: One of start, complete, cancel, disconnect or activate.

        Returns:
            Non-secret business JSON or a sanitized error response.
        """
        if not request.username:
            return error_response("Dashboard authentication required.", status_code=401)
        if self.oauth is None:
            return error_response("Configure and reload the plugin first.")
        try:
            if action == "start":
                url = await self.oauth.begin_authorization(owner=request.username)
                return json_response({"authorization_url": url})
            if action == "complete":
                payload = await request.json(default={})
                if not isinstance(payload, dict):
                    return error_response("Expected a JSON object.")
                await self.oauth.complete_authorization(
                    payload.get("callback_url"), owner=request.username
                )
            elif action == "cancel":
                await self.oauth.cancel_authorization(owner=request.username)
            elif action == "disconnect":
                await self.oauth.disconnect()
            elif action == "activate":
                # Explicitly reload after hot-loading the plugin. Startup already
                # loads configured providers after plugin initialization.
                manager = self.context.provider_manager
                for config in list(manager.providers_config):
                    if (
                        manager.get_merged_provider_config(config).get("type")
                        == PROVIDER_TYPE
                    ):
                        await manager.reload(config)
            else:
                return error_response("Unknown OAuth action.", status_code=404)
            return json_response({"ok": True})
        except OAuth2Error as exc:
            return error_response(str(exc))
        except Exception:
            return error_response("Provider operation failed; check the configuration.")

    async def terminate(self) -> None:
        """Close all owned resources, even if an earlier cleanup fails."""
        async with AsyncExitStack() as cleanup:
            # Always attempt instance, registration and HTTP cleanup after auth.
            if self.http is not None:
                cleanup.push_async_callback(self.http.aclose)
            if self.provider_class is not None:
                cleanup.callback(
                    unregister_provider_adapter, PROVIDER_TYPE, self.provider_class
                )
            try:
                if self.oauth is not None:
                    await self.oauth.close()
            finally:
                manager = self.context.provider_manager
                for provider_id, provider in reversed(list(manager.inst_map.items())):
                    if type(provider) is self.provider_class:
                        cleanup.push_async_callback(
                            manager.terminate_provider, provider_id
                        )
