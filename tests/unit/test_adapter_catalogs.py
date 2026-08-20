from types import ModuleType

import pytest

from astrbot.core.platform.catalog import PlatformCatalog
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.provider.catalog import ProviderCatalog
from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.register import register_provider_adapter


def _declared_provider(module_name: str, adapter_type: str) -> tuple[ModuleType, type]:
    module = ModuleType(module_name)
    adapter = type("ProviderAdapter", (), {"__module__": module_name})
    register_provider_adapter(
        adapter_type,
        "test provider",
        default_config_tmpl={"nested": {"value": "original"}},
    )(adapter)
    module.ProviderAdapter = adapter
    return module, adapter


def _declared_platform(module_name: str, adapter_name: str) -> tuple[ModuleType, type]:
    module = ModuleType(module_name)
    adapter = type("PlatformAdapter", (), {"__module__": module_name})
    register_platform_adapter(
        adapter_name,
        "test platform",
        default_config_tmpl={"nested": {"value": "original"}},
    )(adapter)
    module.PlatformAdapter = adapter
    return module, adapter


def test_provider_catalog_scans_preimported_module_and_isolates_runtimes() -> None:
    module, adapter = _declared_provider("tests.adapters.provider", "test-provider")
    first = ProviderCatalog()
    second = ProviderCatalog()

    first.register_module(module)
    second.register_module(module)

    first_registration = first.get("test-provider")
    second_registration = second.get("test-provider")
    assert first_registration is not None
    assert second_registration is not None
    assert first_registration.cls_type is adapter
    assert second_registration.cls_type is adapter
    assert first_registration.descriptor.provider_type is ProviderType.CHAT_COMPLETION

    first.unregister_module(module.__name__)

    assert first.get("test-provider") is None
    assert second.get("test-provider") is not None


def test_provider_descriptor_templates_are_immutable_and_metadata_is_copied() -> None:
    module, _ = _declared_provider("tests.adapters.provider_template", "test-template")
    catalog = ProviderCatalog()
    catalog.register_module(module)
    registration = catalog.get("test-template")
    assert registration is not None

    with pytest.raises(TypeError):
        registration.descriptor.default_config_tmpl["nested"] = {}  # type: ignore[index]

    first_template = registration.metadata().default_config_tmpl
    second_template = registration.metadata().default_config_tmpl
    assert first_template is not None
    assert second_template is not None
    first_template["nested"]["value"] = "changed"
    assert second_template["nested"]["value"] == "original"


def test_provider_catalog_rejects_conflicting_adapter_types() -> None:
    first_module, _ = _declared_provider("tests.adapters.provider_one", "collision")
    second_module, _ = _declared_provider("tests.adapters.provider_two", "collision")
    catalog = ProviderCatalog()
    catalog.register_module(first_module)

    with pytest.raises(ValueError, match="Provider adapter type collision"):
        catalog.register_module(second_module)


def test_platform_catalog_scans_preimported_module_and_unregisters_exact_module() -> (
    None
):
    first_module, first_adapter = _declared_platform(
        "tests.adapters.platform_one",
        "platform-one",
    )
    second_module, second_adapter = _declared_platform(
        "tests.adapters.platform_two",
        "platform-two",
    )
    catalog = PlatformCatalog()

    catalog.register_module(first_module)
    catalog.register_module(second_module)

    assert catalog.get("platform-one").cls_type is first_adapter
    assert catalog.get("platform-two").cls_type is second_adapter
    assert catalog.unregister_module(first_module.__name__) == ("platform-one",)
    assert catalog.get("platform-one") is None
    assert catalog.get("platform-two").cls_type is second_adapter
