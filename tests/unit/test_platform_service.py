from pathlib import Path
from types import SimpleNamespace

import pytest

from astrbot.core.platform.catalog import PlatformAdapterDescriptor, PlatformCatalog
from astrbot.core.platform.provisioning import PlatformProvisioningValidationError
from astrbot.dashboard.services import platform_service
from astrbot.dashboard.services.platform_service import (
    PlatformService,
    PlatformServiceError,
)


def _service(
    platform_manager: object,
    platform_catalog: PlatformCatalog | None = None,
) -> PlatformService:
    return PlatformService(platform_manager, platform_catalog or PlatformCatalog())


def test_platform_service_find_platform_by_uuid_delegates_to_platform_manager() -> None:
    platform = object()
    platform_manager = SimpleNamespace(
        find_inst_by_webhook_uuid=lambda webhook_uuid: (
            platform if webhook_uuid == "uuid-1" else None
        )
    )
    service = _service(platform_manager)

    result = service.find_platform_by_uuid("uuid-1")

    assert result is platform


def test_platform_service_does_not_scan_manager_attributes_for_webhooks() -> None:
    hidden_adapter = SimpleNamespace(config={"webhook_uuid": "uuid-1"})
    platform_manager = SimpleNamespace(
        find_inst_by_webhook_uuid=lambda _webhook_uuid: None,
        hidden_adapter=hidden_adapter,
    )
    service = _service(platform_manager)

    assert service.find_platform_by_uuid("uuid-1") is None


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_success() -> None:
    calls: list[tuple[str, str, dict]] = []

    async def _invoke_action(platform_id: str, action_name: str, **kwargs) -> dict:
        calls.append((platform_id, action_name, kwargs))
        return {"status": "ok", "data": {"done": True}}

    service = _service(SimpleNamespace(invoke_action=_invoke_action))

    result = await service.invoke_platform_action(
        "napcat-main",
        "send_poke",
        {"user_id": "123456", "target_id": "654321"},
    )

    assert result == {"status": "ok", "data": {"done": True}}
    assert calls == [
        (
            "napcat-main",
            "send_poke",
            {"user_id": "123456", "target_id": "654321"},
        )
    ]


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_validates_input() -> None:
    service = _service(SimpleNamespace(invoke_action=None))

    with pytest.raises(PlatformServiceError, match="Missing action_name") as exc_info:
        await service.invoke_platform_action("napcat-main", "   ", {})
    assert exc_info.value.status_code == 400

    with pytest.raises(
        PlatformServiceError, match="Payload must be an object"
    ) as exc_info:
        await service.invoke_platform_action("napcat-main", "send_poke", [])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_platform_service_invoke_platform_action_maps_common_errors() -> None:
    async def _missing(*_args, **_kwargs):
        raise LookupError("Platform adapter not found: missing")

    async def _unsupported(*_args, **_kwargs):
        raise NotImplementedError(
            "Platform missing does not support action `send_poke`"
        )

    async def _bad_payload(*_args, **_kwargs):
        raise ValueError("group_id is required")

    missing_service = _service(SimpleNamespace(invoke_action=_missing))
    unsupported_service = _service(SimpleNamespace(invoke_action=_unsupported))
    bad_payload_service = _service(SimpleNamespace(invoke_action=_bad_payload))

    with pytest.raises(
        PlatformServiceError, match="Platform adapter not found"
    ) as exc_info:
        await missing_service.invoke_platform_action("missing", "send_poke", {})
    assert exc_info.value.status_code == 404

    with pytest.raises(
        PlatformServiceError, match="does not support action"
    ) as exc_info:
        await unsupported_service.invoke_platform_action("missing", "send_poke", {})
    assert exc_info.value.status_code == 400

    with pytest.raises(PlatformServiceError, match="group_id is required") as exc_info:
        await bad_payload_service.invoke_platform_action(
            "napcat-main", "send_group_notice", {}
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_platform_registration_uses_catalog_provisioner() -> None:
    catalog = PlatformCatalog()
    observed: dict[str, object] = {}

    async def provisioner(*, action: str, payload: dict, platform_config: dict) -> dict:
        observed.update(
            {
                "action": action,
                "payload": payload,
                "platform_config": platform_config,
            }
        )
        return {"status": "pending", "registration_code": "code-1"}

    adapter = type("ProvisionedAdapter", (), {})
    catalog.register(
        PlatformAdapterDescriptor.create(
            name="provisioned",
            description="Provisioned test adapter",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
            provisioner=provisioner,
        ),
        adapter,
    )
    service = _service(SimpleNamespace(), catalog)

    result = await service.handle_platform_registration(
        "provisioned",
        {
            "action": " START ",
            "platform_config": {"id": "provisioned-main"},
        },
    )

    assert result == {"status": "pending", "registration_code": "code-1"}
    assert observed == {
        "action": "start",
        "payload": {
            "action": " START ",
            "platform_config": {"id": "provisioned-main"},
        },
        "platform_config": {"id": "provisioned-main"},
    }


@pytest.mark.asyncio
async def test_platform_registration_discovers_descriptor_into_runtime_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = PlatformCatalog()
    discovered: list[str] = []

    async def provisioner(*, action: str, payload: dict, platform_config: dict) -> dict:
        return {"status": action, "id": platform_config.get("id")}

    def discover(adapter_type: str, target_catalog: PlatformCatalog) -> type:
        discovered.append(adapter_type)
        adapter = type("LazilyDiscoveredAdapter", (), {})
        target_catalog.register(
            PlatformAdapterDescriptor.create(
                name=adapter_type,
                description="Lazily discovered test adapter",
                default_config_tmpl=None,
                adapter_display_name=None,
                logo_path=None,
                support_streaming_message=True,
                i18n_resources=None,
                config_metadata=None,
                provisioner=provisioner,
            ),
            adapter,
        )
        return adapter

    monkeypatch.setattr(platform_service, "discover_platform_adapter", discover)
    service = _service(SimpleNamespace(), catalog)

    result = await service.handle_platform_registration(
        "lazy-provisioned",
        {"action": "start", "platform_config": {"id": "lazy-main"}},
    )

    assert discovered == ["lazy-provisioned"]
    assert result == {"status": "start", "id": "lazy-main"}


@pytest.mark.asyncio
async def test_platform_registration_maps_provisioning_validation_errors() -> None:
    catalog = PlatformCatalog()

    async def provisioner(*, action: str, payload: dict, platform_config: dict) -> dict:
        raise PlatformProvisioningValidationError("Missing registration_code")

    adapter = type("InvalidProvisioningAdapter", (), {})
    catalog.register(
        PlatformAdapterDescriptor.create(
            name="invalid-provisioning",
            description="Invalid provisioning test adapter",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
            provisioner=provisioner,
        ),
        adapter,
    )
    service = _service(SimpleNamespace(), catalog)

    with pytest.raises(
        PlatformServiceError, match="Missing registration_code"
    ) as exc_info:
        await service.handle_platform_registration(
            "invalid-provisioning",
            {"action": "poll"},
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_platform_registration_rejects_unknown_or_unprovisioned_adapters() -> (
    None
):
    catalog = PlatformCatalog()
    adapter = type("UnprovisionedAdapter", (), {})
    catalog.register(
        PlatformAdapterDescriptor.create(
            name="unprovisioned",
            description="Unprovisioned test adapter",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
        ),
        adapter,
    )
    service = _service(SimpleNamespace(), catalog)

    for platform_type in ("unprovisioned", "not-a-platform"):
        with pytest.raises(
            PlatformServiceError, match="Unsupported platform registration"
        ) as exc_info:
            await service.handle_platform_registration(
                platform_type, {"action": "start"}
            )
        assert exc_info.value.status_code == 404


def test_platform_service_does_not_import_concrete_platform_sources() -> None:
    source = Path("astrbot/dashboard/services/platform_service.py").read_text(
        encoding="utf-8"
    )

    assert "astrbot.core.platform.sources" not in source
