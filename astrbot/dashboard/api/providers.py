from fastapi import APIRouter, Depends, Query, Request

from astrbot.core.auth.models import Resource
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import (
    EnabledPatch,
    ProviderConfigRequest,
    ProviderEmbeddingDimensionRequest,
    ProviderSourceRequest,
)
from astrbot.dashboard.services.config_service import (
    REDACTED_SECRET_PLACEHOLDER,
    ProviderConfigService,
    sensitive_config_changed,
)

from .auth import AuthContext, require_resource_action, require_scope

router = APIRouter(tags=["Providers"])


async def require_provider_scope(request: Request) -> AuthContext:
    return await require_scope(request, "provider", authorize_action=False)


def get_service(request: Request) -> ProviderConfigService:
    return request.app.state.services.providers


def _reject_legacy_provider_query_params(
    request: Request,
    *forbidden: str,
) -> None:
    legacy_fields = [key for key in forbidden if key in request.query_params]
    if legacy_fields:
        fields = ", ".join(sorted(legacy_fields))
        raise ApiError(f"Legacy provider query parameters are not supported: {fields}")


def _model_dict(payload) -> dict:
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=True)
    return payload if isinstance(payload, dict) else {}


def _provider_config_for_dimension(
    service: ProviderConfigService,
    provider_id: str,
    body: dict,
) -> dict:
    provider = service.get_provider(provider_id, merged=True, redact=False)
    base_config = provider.get("provider") if isinstance(provider, dict) else {}
    if not isinstance(base_config, dict):
        base_config = {}
    provider_config = body.get("config")
    if isinstance(provider_config, dict):
        return {**base_config, **provider_config}
    return base_config


def _contains_provider_credentials(value: object) -> bool:
    """Return whether a provider write carries a credential-like field."""

    sensitive_names = {
        "access_token",
        "api_key",
        "app_secret",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "key",
        "access_key",
        "password",
        "refresh_token",
        "secret",
        "secret_key",
        "signing_secret",
        "token",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            key_is_sensitive = (
                normalized_key in sensitive_names
                or normalized_key.endswith(
                    ("_token", "_secret", "_password", "_api_key")
                )
            )
            if key_is_sensitive and item != REDACTED_SECRET_PLACEHOLDER:
                return True
            if _contains_provider_credentials(item):
                return True
        return False
    if isinstance(value, list | tuple):
        return any(_contains_provider_credentials(item) for item in value)
    if value == REDACTED_SECRET_PLACEHOLDER:
        return False
    return False


async def _authorize_provider_resource(
    request: Request,
    auth: AuthContext,
    *,
    resource_type: str,
    resource_id: str,
    config: dict | None = None,
    write: bool = False,
) -> None:
    service = request.app.state.services.providers
    config_id = (
        request.query_params.get("config_id")
        or request.headers.get("X-AstrBot-Config-Id")
        or "default"
    )
    credentials_changed = write and _contains_provider_credentials(config or {})
    if write and isinstance(config, dict) and not credentials_changed:
        # A full provider/source replacement can delete an existing credential
        # simply by omitting its field. Treat that as a credential write too.
        try:
            current = (
                service.get_provider(resource_id, redact=False)["provider"]
                if resource_type == "provider"
                else service.get_provider_source(resource_id, redact=False)[
                    "provider_source"
                ]
            )
        except Exception:
            current = None
        if isinstance(current, dict):
            credentials_changed = sensitive_config_changed(current, config)
    action = (
        "provider.credentials.write"
        if credentials_changed
        else "provider.manage"
        if write
        else "provider.read"
    )
    await require_resource_action(
        request,
        auth,
        action=action,
        resource=Resource.named(resource_type, resource_id, config_id=config_id),
    )


@router.get("/providers/schema")
async def get_provider_schema(
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request, auth, resource_type="provider", resource_id="schema"
    )
    return ok(service.get_provider_schema())


@router.get("/provider-sources")
async def list_provider_sources(
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request, auth, resource_type="provider-source", resource_id="collection"
    )
    return ok(service.list_provider_sources())


@router.post("/provider-sources")
async def create_provider_source(
    payload: ProviderSourceRequest,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    source_id = config.get("id")
    if not source_id:
        raise ApiError("Provider source config must have an 'id' field")
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider-source",
        resource_id=str(source_id),
        config=config,
        write=True,
    )
    await service.upsert_provider_source(source_id, config)
    return ok(message="更新 provider source 成功")


@router.get("/provider-sources/{source_id:path}/models")
async def list_provider_source_models(
    source_id: str,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request, auth, resource_type="provider-source", resource_id=source_id
    )
    return ok(await service.list_provider_source_models(source_id))


@router.get("/provider-sources/{source_id:path}/providers")
async def list_providers_by_source(
    source_id: str,
    request: Request,
    provider_type: str | None = Query(default=None),
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    _reject_legacy_provider_query_params(request, "capability")
    await _authorize_provider_resource(
        request, auth, resource_type="provider-source", resource_id=source_id
    )
    return ok(
        service.list_providers(
            provider_type=provider_type,
            provider_source_id=source_id,
        )
    )


@router.post("/provider-sources/{source_id:path}/providers")
async def create_provider_in_source(
    source_id: str,
    payload: ProviderConfigRequest,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    config["provider_source_id"] = source_id
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=str(config.get("id") or source_id),
        config=config,
        write=True,
    )
    await service.create_provider(config, source_id)
    return ok(message="新增服务提供商配置成功")


@router.get("/provider-sources/{source_id:path}")
async def get_provider_source(
    source_id: str,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request, auth, resource_type="provider-source", resource_id=source_id
    )
    return ok(service.get_provider_source(source_id))


@router.put("/provider-sources/{source_id:path}")
async def upsert_provider_source(
    source_id: str,
    payload: ProviderSourceRequest,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider-source",
        resource_id=source_id,
        config=dict(payload.config),
        write=True,
    )
    await service.upsert_provider_source(
        source_id,
        dict(payload.config),
    )
    return ok(message="更新 provider source 成功")


@router.delete("/provider-sources/{source_id:path}")
async def delete_provider_source(
    source_id: str,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider-source",
        resource_id=source_id,
        write=True,
    )
    await service.delete_provider_source(source_id)
    return ok(message="删除 provider source 成功")


@router.get("/providers")
async def list_providers(
    request: Request,
    provider_type: str | None = Query(default=None),
    provider_source_id: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    _reject_legacy_provider_query_params(request, "capability", "source_id")
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=provider_source_id or "collection",
    )
    return ok(
        service.list_providers(
            provider_type=provider_type,
            provider_source_id=provider_source_id,
            enabled=enabled,
        )
    )


@router.post("/providers")
async def create_provider(
    payload: ProviderConfigRequest,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    config.setdefault("enable", True)
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=str(config.get("id") or "new"),
        config=config,
        write=True,
    )
    await service.create_provider(config)
    return ok(message="新增服务提供商配置成功")


@router.patch("/providers/{provider_id:path}/enabled")
async def set_provider_enabled(
    provider_id: str,
    payload: EnabledPatch,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=provider_id,
        write=True,
    )
    await service.set_provider_enabled(provider_id, payload.enabled)
    return ok(message="更新成功，已经实时生效~")


@router.post("/providers/{provider_id:path}/test")
async def test_provider(
    provider_id: str,
    request: Request = None,  # type: ignore[assignment]
    auth: AuthContext = Depends(require_provider_scope),
    _auth: AuthContext | None = None,
    service: ProviderConfigService = Depends(get_service),
):
    if request is not None and isinstance(auth, AuthContext):
        await _authorize_provider_resource(
            request, auth, resource_type="provider", resource_id=provider_id
        )
    return ok(await service.test_provider(provider_id))


@router.post("/providers/{provider_id:path}/embedding-dimension")
async def get_embedding_dimension(
    provider_id: str,
    request: Request,
    payload: ProviderEmbeddingDimensionRequest | None = None,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    body = _model_dict(payload)
    await _authorize_provider_resource(
        request, auth, resource_type="provider", resource_id=provider_id
    )
    return ok(
        await service.get_embedding_dimension(
            _provider_config_for_dimension(service, provider_id, body)
        )
    )


@router.get("/providers/{provider_id:path}")
async def get_provider(
    provider_id: str,
    request: Request,
    merged: bool = Query(default=False),
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request, auth, resource_type="provider", resource_id=provider_id
    )
    return ok(service.get_provider(provider_id, merged=merged))


@router.put("/providers/{provider_id:path}")
async def update_provider(
    provider_id: str,
    payload: ProviderConfigRequest,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    config = dict(payload.config)
    if "id" not in config:
        config["id"] = provider_id
    config.setdefault("enable", True)
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=provider_id,
        config=config,
        write=True,
    )
    await service.update_provider(provider_id, config)
    return ok(message="更新成功，已经实时生效~")


@router.delete("/providers/{provider_id:path}")
async def delete_provider(
    provider_id: str,
    request: Request,
    auth: AuthContext = Depends(require_provider_scope),
    service: ProviderConfigService = Depends(get_service),
):
    await _authorize_provider_resource(
        request,
        auth,
        resource_type="provider",
        resource_id=provider_id,
        write=True,
    )
    await service.delete_provider(provider_id)
    return ok(message="删除成功，已经实时生效。")
