"""OrcaRouter chat completion provider.

OrcaRouter is an OpenAI-compatible AI gateway. This adapter is a thin,
first-class provider entry: it reuses the project's OpenAI-compatible transport
and adds OrcaRouter's attribution headers, its own credential seam, and
catalog-driven model discovery.
"""

from __future__ import annotations

from typing import Any

from astrbot import logger

from ..orcarouter_auth import (
    OrcaRouterAuthError,
    api_key_credentials,
    classify_terminal_status,
    resolve_api_base_url,
)
from ..orcarouter_catalog import (
    VERIFIED_REASONING_EFFORTS,
    discover_catalog,
    filter_models,
)
from ..register import register_provider_adapter
from .openai_source import ProviderOpenAIOfficial


@register_provider_adapter(
    "orcarouter_chat_completion",
    "OrcaRouter Chat Completion Provider Adapter",
)
class ProviderOrcaRouter(ProviderOpenAIOfficial):
    """OrcaRouter provider using its OpenAI-compatible inference endpoint."""

    def __init__(self, provider_config: dict, provider_settings: dict) -> None:
        """Initialise the client and resolve the inference origin.

        The API key and a PKCE-issued key are interchangeable here: both arrive
        through the project's existing provider ``key`` list, so this adapter
        never learns which authentication path produced the credential.

        Args:
            provider_config: AstrBot provider source configuration.
            provider_settings: Global provider settings.

        Raises:
            ValueError: The configured inference origin is not acceptable.
        """
        provider_config = dict(provider_config or {})
        configured_base = provider_config.get("api_base") or None
        provider_config["api_base"] = resolve_api_base_url(configured_base)
        super().__init__(provider_config, provider_settings)

        self._last_known_good: list[Any] | None = None
        self._active_catalog: list[Any] = []
        self._catalog_source: str = "unknown"
        self.needs_reauth = False
        # A credential rejected mid-flight must not invalidate a newer one.
        self.credential_generation = 0
        self._rejected_generation: int | None = None

    def mark_needs_reauth(self, status_code: int) -> None:
        """Record a terminal authentication failure for this credential.

        Only the exact credential generation that made the rejected request is
        marked, so a late failure from an old request cannot poison a freshly
        authorized credential.

        Args:
            status_code: The HTTP status returned by the relay.
        """
        error_type = classify_terminal_status(status_code)
        if error_type is None:
            return
        self._rejected_generation = self.credential_generation
        self.needs_reauth = True
        logger.warning(
            "OrcaRouter credential for provider %s was rejected with HTTP %s; "
            "re-authorization is required. No refresh is attempted because a "
            "PKCE-issued key is durable, not refreshable.",
            self.provider_config.get("id", "orcarouter"),
            status_code,
        )

    def set_key(self, key: str) -> None:
        """Replace the stored credential and clear any reauth state.

        Args:
            key: The new OrcaRouter API key.
        """
        super().set_key(key)
        self.chosen_api_key = key
        self.credential_generation += 1
        self._rejected_generation = None
        self.needs_reauth = False

    async def _handle_api_error(
        self,
        e: Exception,
        payloads: dict,
        context_query: list,
        func_tool: Any,
        chosen_key: str,
        available_api_keys: list[str],
        retry_cnt: int,
        max_retries: int,
        image_fallback_used: bool = False,
    ) -> tuple:
        """Record terminal authentication failures before normal recovery.

        A ``401`` from the relay means the credential was revoked or is
        otherwise dead. A PKCE-issued key is durable rather than refreshable,
        so there is no refresh to attempt: the exact credential generation
        that made this request is marked for reauthorization and the error is
        surfaced unchanged.

        Args:
            e: The exception raised by the client.
            payloads: Request payloads being retried.
            context_query: Conversation context being retried.
            func_tool: Tool set for the request.
            chosen_key: The credential that produced this error.
            available_api_keys: Remaining credentials to try.
            retry_cnt: Current retry attempt index.
            max_retries: Configured retry ceiling.
            image_fallback_used: Whether a text-only retry already happened.

        Returns:
            The same recovery tuple the parent produces.

        Raises:
            Exception: The original error, after marking credential state.
        """
        if getattr(e, "status_code", None) == 401:
            self.mark_needs_reauth(401)
        return await super()._handle_api_error(
            e,
            payloads,
            context_query,
            func_tool,
            chosen_key,
            available_api_keys,
            retry_cnt,
            max_retries,
            image_fallback_used,
        )

    def current_credentials(self):
        """Adapt the configured key into the shared credential shape.

        Returns:
            Credentials marked ``source="api_key"``, or None when unconfigured.

        Raises:
            OrcaRouterAuthError: The configured key is empty.
        """
        if not self.chosen_api_key:
            return None
        return api_key_credentials(self.chosen_api_key)

    def catalog_capability(self) -> str:
        """Return the capability this provider instance is configured for.

        Returns:
            One of the catalog capability names; defaults to ``chat``.
        """
        capability = str(self.provider_config.get("model_capability") or "chat")
        return capability if capability else "chat"

    def required_input_modalities(self) -> set[str]:
        """Return the non-text input modalities this instance must support.

        Returns:
            A set such as ``{"image"}``; empty for text-only usage.
        """
        configured = self.provider_config.get("required_input_modalities")
        if isinstance(configured, str):
            configured = [configured]
        if not isinstance(configured, list):
            return set()
        return {
            item
            for item in configured
            if isinstance(item, str) and item in {"image", "audio", "video"}
        }

    async def get_models(self) -> list[str]:
        """Return the capability-filtered model IDs from the live catalog.

        When live discovery fails this degrades to the last known-good catalog
        or the small verified seed, and never to free-text entry.

        Returns:
            Model IDs exactly as the catalog names them.

        Raises:
            OrcaRouterAuthError: No usable credential is configured.
        """
        credentials = self.current_credentials()
        if credentials is None:
            raise OrcaRouterAuthError(
                "OrcaRouter provider has no API key configured; add one or use "
                "Connect with OrcaRouter"
            )

        result = await discover_catalog(
            self.provider_config["api_base"],
            credentials.key,
            last_known_good=self._last_known_good,
        )
        self._catalog_source = result.source
        if result.source == "live":
            self._last_known_good = result.models
        # Cache whatever catalog was actually used so the capability-filtered
        # list and its metadata always describe the same models.
        self._active_catalog = result.models

        capability = self.catalog_capability()
        selected = filter_models(result.models, capability)  # type: ignore[arg-type]

        modalities = self.required_input_modalities()
        if modalities:
            required = {modality for modality in modalities if modality != "text"}
            selected = [
                model
                for model in selected
                if all(model.supports_input(modality) for modality in required)
            ]

        return [model.id for model in selected]

    def catalog_metadata(self) -> dict[str, dict[str, Any]]:
        """Return capability-relevant metadata for the models just listed.

        The dashboard merges this over its generic metadata table so context
        windows, input modalities and the verified reasoning-effort ladder
        survive discovery — including when discovery degraded to the seed.

        Returns:
            A mapping of model ID to metadata dict.
        """
        metadata: dict[str, dict[str, Any]] = {}
        for model in self._active_catalog:
            entry = model.to_metadata()
            efforts = VERIFIED_REASONING_EFFORTS.get(model.id)
            if efforts:
                entry["reasoning_efforts"] = list(efforts)
                entry["reasoning"] = True
            entry["catalog_source"] = self._catalog_source
            metadata[model.id] = entry
        return metadata

    @property
    def catalog_source(self) -> str:
        """Return how the current model list was obtained.

        Returns:
            ``live``, ``last_known_good``, ``seed``, or ``unknown``.
        """
        return self._catalog_source
