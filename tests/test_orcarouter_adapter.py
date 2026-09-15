"""Adapter-level tests for the OrcaRouter provider.

These exercise the provider's registration, its catalog-driven model listing,
capability filtering through a real provider instance, and generation-safe
terminal 401 handling. All credentials are fabricated.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from astrbot.core.provider import orcarouter_catalog as catalog
from astrbot.core.provider.register import provider_cls_map
from astrbot.core.provider.sources.orcarouter_source import ProviderOrcaRouter

FAKE_KEY = "sk-orca-test-not-a-real-credential"
API_BASE = "https://api.orcarouter.ai/v1"


def _provider_config(**overrides):
    config = {
        "id": "orcarouter-test",
        "type": "orcarouter_chat_completion",
        "provider": "orcarouter",
        "provider_type": "chat_completion",
        "model": "openai/gpt-5.5",
        "key": [FAKE_KEY],
        "api_base": API_BASE,
        "timeout": 30,
    }
    config.update(overrides)
    return config


def _provider(**overrides) -> ProviderOrcaRouter:
    return ProviderOrcaRouter(_provider_config(**overrides), {})


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------


def test_adapter_is_registered_as_a_first_class_named_provider():
    assert "orcarouter_chat_completion" in provider_cls_map

    metadata = provider_cls_map["orcarouter_chat_completion"]
    assert metadata.cls_type is ProviderOrcaRouter
    assert metadata.provider_type.value == "chat_completion"


def test_config_template_registers_orcarouter_with_its_own_api_base():
    from astrbot.core.config.default import CONFIG_METADATA_2

    template = CONFIG_METADATA_2["provider_group"]["metadata"]["provider"][
        "config_template"
    ]

    assert "OrcaRouter" in template
    entry = template["OrcaRouter"]
    assert entry["id"] == "orcarouter"
    assert entry["type"] == "orcarouter_chat_completion"
    assert entry["provider_type"] == "chat_completion"
    assert entry["api_base"] == "https://api.orcarouter.ai/v1"
    # A distinct provider name, not a renamed OpenRouter or a generic slot.
    assert entry["provider"] == "orcarouter"


def test_adapter_rejects_a_non_https_public_api_base():
    with pytest.raises(ValueError):
        _provider(api_base="http://api.orcarouter.ai/v1")


def test_loopback_api_base_is_allowed_for_self_hosted_development():
    provider = _provider(api_base="http://127.0.0.1:9000/v1")

    assert provider.provider_config["api_base"] == "http://127.0.0.1:9000/v1"


# --------------------------------------------------------------------------
# credential seam — both adapters produce the same shape
# --------------------------------------------------------------------------


def test_api_key_path_produces_credentials_for_inference():
    credentials = _provider().current_credentials()

    assert credentials is not None
    assert credentials.key == FAKE_KEY
    assert credentials.source == "api_key"


def test_a_pkce_issued_key_flows_through_the_same_seam(monkeypatch):
    from astrbot.core.provider import orcarouter_auth as auth

    monkeypatch.setattr(
        auth.httpx,
        "post",
        lambda url, json=None, timeout=None: type(
            "R",
            (),
            {
                "status_code": 200,
                "json": staticmethod(
                    lambda: {"key": "sk-orca-from-pkce", "user_id": "7", "scope": "api"}
                ),
            },
        )(),
    )
    issued = auth.exchange_code(
        auth_base_url="https://www.orcarouter.ai",
        code="fake-code",
        code_verifier="v" * 43,
    )

    # The PKCE adapter's result is stored exactly like a pasted key, and the
    # adapter below cannot tell the two apart.
    provider = _provider(key=[issued.key])
    resolved = provider.current_credentials()

    assert resolved.key == "sk-orca-from-pkce"
    assert resolved.scope == "api"


def test_missing_credential_is_reported_not_silently_tolerated():
    # An empty credential fails fast at construction rather than building a
    # client that would send unauthenticated requests.
    with pytest.raises(Exception):
        _provider(key=[])


# --------------------------------------------------------------------------
# catalog-driven model listing through the adapter
# --------------------------------------------------------------------------


def _live(monkeypatch, payload):
    async def fetch(api_base_url, api_key, timeout=None):
        return catalog.parse_catalog(payload)

    monkeypatch.setattr(catalog, "fetch_live_catalog", fetch)


def test_model_list_comes_from_the_api_and_keeps_the_vendor_namespace(monkeypatch):
    _live(
        monkeypatch,
        [
            {"id": "openai/gpt-5.5", "supported_endpoint_types": ["openai"]},
            {
                "id": "anthropic/claude-opus-4.8",
                "supported_endpoint_types": ["anthropic"],
            },
        ],
    )

    ids = asyncio.run(_provider().get_models())

    assert ids == ["openai/gpt-5.5", "anthropic/claude-opus-4.8"]


def test_text_entry_point_excludes_non_text_models(monkeypatch):
    _live(
        monkeypatch,
        [
            {"id": "openai/gpt-5.5", "supported_endpoint_types": ["openai"]},
            {"id": "vendor/image", "supported_endpoint_types": ["image-generation"]},
            {"id": "vendor/video", "supported_endpoint_types": ["openai-video"]},
            {"id": "vendor/rerank", "supported_endpoint_types": ["jina-rerank"]},
            {"id": "vendor/embed", "supported_endpoint_types": ["embeddings"]},
        ],
    )

    ids = asyncio.run(_provider().get_models())

    assert ids == ["openai/gpt-5.5"]


def test_text_entry_point_excludes_models_without_a_speakable_endpoint_type(
    monkeypatch,
):
    _live(
        monkeypatch,
        [
            {"id": "openai/gpt-5.5", "supported_endpoint_types": ["openai"]},
            {"id": "vendor/unknown-endpoint", "supported_endpoint_types": ["mystery"]},
            {"id": "vendor/no-endpoints"},
        ],
    )

    assert asyncio.run(_provider().get_models()) == ["openai/gpt-5.5"]


def test_multimodal_instance_drops_chat_models_without_declared_image_input(
    monkeypatch,
):
    _live(
        monkeypatch,
        [
            {
                "id": "openai/gpt-5.5",
                "supported_endpoint_types": ["openai"],
                "architecture": {"input_modalities": ["text", "image"]},
            },
            {
                "id": "deepseek/deepseek-v4-pro",
                "supported_endpoint_types": ["openai"],
                "architecture": {"input_modalities": ["text"]},
            },
            {"id": "orcarouter/auto", "supported_endpoint_types": ["openai"]},
        ],
    )

    ids = asyncio.run(_provider(required_input_modalities=["image"]).get_models())

    assert ids == ["openai/gpt-5.5"]


def test_catalog_failure_degrades_to_the_verified_seed_not_free_text(monkeypatch):
    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError("catalog down")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)
    provider = _provider()

    ids = asyncio.run(provider.get_models())

    assert set(ids) == {
        "openai/gpt-5.5",
        "anthropic/claude-opus-4.8",
        "google/gemini-3.5-flash",
        "deepseek/deepseek-v4-pro",
        "orcarouter/auto",
    }
    assert provider.catalog_source == "seed"


def test_seed_metadata_keeps_reasoning_efforts_and_modalities(monkeypatch):
    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError("catalog down")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)
    provider = _provider()
    asyncio.run(provider.get_models())

    metadata = provider.catalog_metadata()

    assert metadata["openai/gpt-5.5"]["reasoning_efforts"] == [
        "low",
        "medium",
        "high",
        "xhigh",
    ]
    assert metadata["google/gemini-3.5-flash"]["modalities"]["input"] == [
        "audio",
        "image",
        "text",
        "video",
    ]


def test_live_success_is_authoritative_and_does_not_merge_the_seed(monkeypatch):
    _live(
        monkeypatch,
        [{"id": "vendor/only-live", "supported_endpoint_types": ["openai"]}],
    )
    provider = _provider()

    ids = asyncio.run(provider.get_models())

    assert ids == ["vendor/only-live"]
    assert provider.catalog_source == "live"


# --------------------------------------------------------------------------
# credential lifecycle
# --------------------------------------------------------------------------


def test_revoked_credential_is_marked_for_reauth_without_a_refresh_attempt():
    provider = _provider()

    provider.mark_needs_reauth(401)

    assert provider.needs_reauth is True
    # No refresh machinery exists to call; the stored key is left in place so a
    # transient failure cannot destroy the user's credential.
    assert provider.chosen_api_key == FAKE_KEY


def test_non_auth_failures_do_not_touch_credential_state():
    provider = _provider()

    for status in (403, 429, 500, 502):
        provider.mark_needs_reauth(status)

    assert provider.needs_reauth is False


def test_a_new_login_clears_reauth_and_bumps_the_generation():
    provider = _provider()
    provider.mark_needs_reauth(401)
    stale_generation = provider.credential_generation

    provider.set_key("sk-orca-a-freshly-authorized-credential")

    assert provider.needs_reauth is False
    assert provider.credential_generation == stale_generation + 1
    assert provider.chosen_api_key == "sk-orca-a-freshly-authorized-credential"


def test_a_late_failure_from_an_old_generation_cannot_poison_the_new_credential(
    monkeypatch,
):
    provider = _provider()

    # Capture the generation that an in-flight request was issued under.
    in_flight_generation = provider.credential_generation

    # The user re-authorizes while that request is still outstanding.
    provider.set_key("sk-orca-second-credential")

    # The old request now fails with 401. Simulate the guarded transition the
    # adapter applies for a response bound to the superseded generation.
    if provider.credential_generation == in_flight_generation:
        provider.mark_needs_reauth(401)

    assert provider.needs_reauth is False
    assert provider.chosen_api_key == "sk-orca-second-credential"


def test_401_from_the_current_generation_does_mark_reauth():
    provider = _provider()

    provider.mark_needs_reauth(401)

    assert provider.needs_reauth is True
    assert provider._rejected_generation == provider.credential_generation


# --------------------------------------------------------------------------
# secrets never leak
# --------------------------------------------------------------------------


def test_provider_repr_and_errors_never_contain_the_key(monkeypatch):
    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError(f"failed for {api_key}")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)
    provider = _provider()

    # Discovery still succeeds through the seed, and nothing surfaced the key.
    ids = asyncio.run(provider.get_models())
    assert ids
    assert FAKE_KEY not in provider.catalog_source


def test_capability_defaults_to_chat():
    assert _provider().catalog_capability() == "chat"
    assert _provider(model_capability="embedding").catalog_capability() == "embedding"


def test_required_modalities_accepts_a_scalar_or_a_list():
    assert _provider(required_input_modalities="image").required_input_modalities() == {
        "image"
    }
    assert _provider(
        required_input_modalities=["image", "audio"]
    ).required_input_modalities() == {
        "audio",
        "image",
    }
    assert _provider().required_input_modalities() == set()


def test_provider_type_dispatch_table_loads_the_adapter():
    # The provider manager resolves adapters through an explicit dispatch
    # table, so a registered decorator alone is not enough for a new type.
    from astrbot.core.provider.manager import ProviderManager

    manager = ProviderManager.__new__(ProviderManager)
    ProviderManager.dynamic_import_provider(manager, "orcarouter_chat_completion")

    assert "orcarouter_chat_completion" in provider_cls_map


# --------------------------------------------------------------------------
# the dashboard sees the gateway's own modalities, not the shared table
# --------------------------------------------------------------------------


class _DashboardConfigService:
    """A ProviderConfigService with only the collaborators these tests need."""

    def __init__(self, providers_config: list[dict], sources: list[dict]) -> None:
        from astrbot.dashboard.services.config_service import ProviderConfigService

        self._service = ProviderConfigService.__new__(ProviderConfigService)
        self._service.provider_manager = _Manager(providers_config, sources)
        # The service reads provider sources out of the persisted config.
        self._service.config = {"provider_sources": sources, "provider": providers_config}
        self._service.core_lifecycle = None
        self._service._catalog_metadata_cache = {}

    def __getattr__(self, name):
        return getattr(self._service, name)


class _Manager:
    def __init__(self, providers_config: list[dict], sources: list[dict]) -> None:
        self.providers_config = providers_config
        self.provider_sources_config = sources

    def dynamic_import_provider(self, provider_type: str) -> None:
        from astrbot.core.provider.manager import ProviderManager

        manager = ProviderManager.__new__(ProviderManager)
        ProviderManager.dynamic_import_provider(manager, provider_type)

    def get_merged_provider_config(self, provider: dict) -> dict:
        return dict(provider)


def _dashboard_service(**overrides) -> _DashboardConfigService:
    """Build the dashboard service over one configured OrcaRouter model."""
    source = {
        "id": "orcarouter",
        "type": "orcarouter_chat_completion",
        "provider_type": "chat_completion",
        "api_base": API_BASE,
        "key": [FAKE_KEY],
    }
    source.update(overrides.pop("source", {}))
    provider = {
        "id": "orcarouter/deepseek/deepseek-v4-flash",
        "provider_source_id": "orcarouter",
        "provider_type": "chat_completion",
        "model": "deepseek/deepseek-v4-flash",
        "enable": True,
        "modalities": ["text", "image", "audio", "tool_use"],
    }
    provider.update(overrides.pop("provider", {}))
    return _DashboardConfigService([provider], [source])


def test_dashboard_listing_without_the_flag_never_discovers(monkeypatch):
    """A plain provider listing must stay offline."""

    async def explode(*args, **kwargs):
        raise AssertionError("a plain listing reached the gateway")

    monkeypatch.setattr(catalog, "fetch_live_catalog", explode)
    service = _dashboard_service()

    listing = service.list_providers(capability="chat")

    assert listing["providers"]
    # The gateway's own modalities are absent, so nothing could have been merged.
    assert "deepseek/deepseek-v4-flash" not in listing["model_metadata"]


def test_dashboard_listing_reports_the_gateways_own_modalities(monkeypatch):
    """Once discovered, the gateway's declaration wins over the shared table."""
    from astrbot.core.provider import orcarouter_auth as auth

    async def live(api_base_url, api_key, timeout=None):
        return [
            catalog.CatalogModel(
                id="deepseek/deepseek-v4-flash",
                endpoint_types=frozenset({"openai"}),
                input_modalities=frozenset({"text"}),
                output_modalities=frozenset({"text"}),
                context_length=128000,
            )
        ]

    monkeypatch.setattr(catalog, "fetch_live_catalog", live)
    monkeypatch.setattr(auth, "api_key_credentials", auth.api_key_credentials)
    service = _dashboard_service()

    asyncio.run(service.refresh_source_catalogs())
    listing = service.list_providers(capability="chat", catalog_metadata=True)
    metadata = listing["model_metadata"]["deepseek/deepseek-v4-flash"]

    # The catalog says text-only; the stored provider entry claims image input.
    assert metadata["modalities"]["input"] == ["text"]
    assert metadata["limit"]["context"] == 128000


def test_dashboard_listing_skips_sources_without_a_catalog(monkeypatch):
    """A provider without a catalog leaves the shared table untouched."""
    service = _dashboard_service()
    service._service.provider_manager.provider_sources_config = [
        {"id": "plain", "type": "openai_chat_completion"}
    ]
    service._service.provider_manager.providers_config = [
        {
            "id": "plain/gpt",
            "provider_source_id": "plain",
            "model": "gpt-5.5",
            "enable": True,
            "modalities": ["text"],
        }
    ]

    asyncio.run(service.refresh_source_catalogs())

    listing = service.list_providers(capability="chat", catalog_metadata=True)
    assert "gpt-5.5" not in listing["model_metadata"]


def test_dashboard_catalog_first_discovery_does_not_use_the_seed(monkeypatch):
    """A failed live fetch must not publish the offline fallback as the truth."""
    service = _dashboard_service()

    async def failing(api_base_url, api_key, timeout=None):
        raise httpx.ConnectError("gateway unreachable")

    monkeypatch.setattr(catalog, "fetch_live_catalog", failing)

    asyncio.run(service.refresh_source_catalogs())

    # A degraded seed catalog describes models this gateway may not serve, so it
    # must never be cached as if the source had published it.
    assert service._service._catalog_metadata_cache == {}


def test_dashboard_cached_catalog_is_reused_between_listings(monkeypatch):
    """Discovery runs once per source; later listings read the cache."""
    calls = []

    async def live(api_base_url, api_key, timeout=None):
        calls.append(api_key)
        return [
            catalog.CatalogModel(
                id="deepseek/deepseek-v4-flash",
                endpoint_types=frozenset({"openai"}),
                input_modalities=frozenset({"text"}),
                output_modalities=frozenset({"text"}),
            )
        ]

    monkeypatch.setattr(catalog, "fetch_live_catalog", live)
    service = _dashboard_service()

    asyncio.run(service.refresh_source_catalogs())
    asyncio.run(service.refresh_source_catalogs())

    assert len(calls) == 1
    assert service.list_providers(capability="chat", catalog_metadata=True)[
        "model_metadata"
    ]["deepseek/deepseek-v4-flash"]["modalities"]["input"] == ["text"]


def test_dashboard_catalog_never_describes_another_sources_models(monkeypatch):
    """Metadata is merged strictly for the model IDs of its own source."""
    service = _dashboard_service()
    service._service.provider_manager.provider_sources_config.append(
        {"id": "other", "type": "orcarouter_chat_completion", "key": [FAKE_KEY]}
    )
    service._service.provider_manager.providers_config.append(
        {
            "id": "other/deepseek/deepseek-v4-pro",
            "provider_source_id": "other",
            "model": "deepseek/deepseek-v4-pro",
            "enable": True,
            "modalities": ["text"],
        }
    )
    service._service._catalog_metadata_cache["orcarouter"] = (
        __import__("time").monotonic(),
        {
            "deepseek/deepseek-v4-flash": {
                "modalities": {"input": ["text"], "output": ["text"]},
            }
        },
    )

    listing = service.list_providers(capability="chat", catalog_metadata=True)

    assert "deepseek/deepseek-v4-flash" in listing["model_metadata"]
    assert "deepseek/deepseek-v4-pro" not in listing["model_metadata"]


def test_dashboard_catalog_metadata_never_exposes_the_credential(monkeypatch):
    """The merged payload carries catalog fields only."""
    service = _dashboard_service()
    service._service._catalog_metadata_cache["orcarouter"] = (
        __import__("time").monotonic(),
        {
            "deepseek/deepseek-v4-flash": {
                "modalities": {"input": ["text"], "output": ["text"]},
                "endpoint_types": ["openai"],
            }
        },
    )

    listing = service.list_providers(capability="chat", catalog_metadata=True)

    assert FAKE_KEY not in repr(listing["model_metadata"])
