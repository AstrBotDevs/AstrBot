"""Keep inventory filters aligned with the implemented public contract."""

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def inventory_spec() -> dict:
    path = Path(__file__).resolve().parents[2] / "openspec" / "openapi-v1.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("path", "location", "operation_id"),
    [
        (
            "/api/v1/provider-sources/models",
            "query",
            "listProviderSourceModelsById",
        ),
        (
            "/api/v1/provider-sources/{source_id}/models",
            "path",
            "listProviderSourceModels",
        ),
    ],
)
def test_model_catalog_documents_only_supported_source_parameter(
    inventory_spec: dict, path: str, location: str, operation_id: str
) -> None:
    operation = inventory_spec["paths"][path]["get"]
    parameters = [
        inventory_spec["components"]["parameters"][parameter["$ref"].rsplit("/", 1)[1]]
        if "$ref" in parameter
        else parameter
        for parameter in operation["parameters"]
    ]
    assert [
        (parameter["name"], parameter["in"], parameter.get("required", False))
        for parameter in parameters
    ] == [("source_id", location, True)]
    assert operation["operationId"] == operation_id
    assert operation["x-astrbot-scope"] == "provider"
    assert operation["responses"] == {"200": {"$ref": "#/components/responses/Ok"}}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/providers",
        "/api/v1/provider-sources/providers",
        "/api/v1/provider-sources/{source_id}/providers",
    ],
)
def test_provider_inventory_retains_supported_capability_filter(
    inventory_spec: dict, path: str
) -> None:
    operation = inventory_spec["paths"][path]["get"]
    capability = next(
        parameter
        for parameter in operation["parameters"]
        if parameter.get("name") == "capability"
    )
    assert capability["in"] == "query"
    assert capability["schema"] == {"$ref": "#/components/schemas/ProviderCapability"}
    assert not capability.get("required", False)
    assert inventory_spec["components"]["schemas"]["ProviderCapability"]["enum"] == [
        "chat",
        "agent",
        "stt",
        "tts",
        "embedding",
        "rerank",
        "decision",
    ]
