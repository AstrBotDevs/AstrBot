import json
import subprocess
import sys
from pathlib import Path

from docs.scripts.update_openapi_json import (
    PUBLIC_OPEN_API_SCOPES,
    filter_public_openapi,
    load_yaml,
    render_scope_reference,
)

SPEC_PATH = Path(__file__).resolve().parents[2] / "openspec" / "openapi-v1.yaml"
PUBLIC_SPEC_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "public" / "openapi.json"
)
ZH_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "zh" / "dev" / "openapi-scopes.md"
)
EN_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "en" / "dev" / "openapi-scopes.md"
)


def test_public_openapi_is_filtered_by_supported_scope() -> None:
    spec = filter_public_openapi(load_yaml(SPEC_PATH))

    assert "/api/v1/conversations" in spec["paths"]
    assert spec["paths"]["/api/v1/conversations"]["get"]["x-astrbot-scope"] == "data"
    assert "/api/v1/commands" not in spec["paths"]
    assert "/api/v1/files/tokens/{file_token}" not in spec["paths"]
    assert "/api/v1/stats/versions" not in spec["paths"]

    for methods in spec["paths"].values():
        for operation in methods.values():
            assert operation["x-astrbot-scope"] in PUBLIC_OPEN_API_SCOPES
            assert "**Required scope:**" in operation["description"]


def test_public_openapi_documents_sensitive_subscopes() -> None:
    spec = filter_public_openapi(load_yaml(SPEC_PATH))

    chat_send = spec["paths"]["/api/v1/chat"]["post"]
    assert chat_send["x-astrbot-sensitive-scopes"] == ["chat:admin"]
    assert chat_send["description"] == (
        "**Required scope:** `chat`\n\n**Conditional sensitive scope:** `chat:admin`"
    )

    system_config_update = spec["paths"]["/api/v1/system-config"]["put"]
    assert system_config_update["x-astrbot-sensitive-scopes"] == [
        "config:edit_admin",
        "config:secrets",
        "config:security",
    ]
    assert "`config:edit_admin`, `config:secrets`, `config:security`" in (
        system_config_update["description"]
    )


def test_scope_reference_lists_every_supported_scope() -> None:
    spec = filter_public_openapi(load_yaml(SPEC_PATH))

    zh_reference = render_scope_reference(spec, language="zh")
    en_reference = render_scope_reference(spec, language="en")

    for scope in PUBLIC_OPEN_API_SCOPES:
        assert f"## `{scope}`" in zh_reference
        assert f"## `{scope}`" in en_reference
        definition = spec["x-astrbot-scope-definitions"][scope]
        assert definition["description_zh"] in zh_reference
        assert definition["description"] in en_reference
    assert "| `GET` | `/api/v1/conversations` | — |" in zh_reference
    assert "| `POST` | `/api/v1/chat` | `chat:admin` |" in en_reference
    assert "**包含权限:** `bot`、`provider`" in zh_reference
    assert "**Sensitive sub-scope `chat:admin`:**" in en_reference


def test_generated_openapi_scope_artifacts_are_current() -> None:
    spec = filter_public_openapi(load_yaml(SPEC_PATH))

    assert json.loads(PUBLIC_SPEC_PATH.read_text(encoding="utf-8")) == spec
    assert ZH_REFERENCE_PATH.read_text(encoding="utf-8") == render_scope_reference(
        spec,
        language="zh",
    )
    assert EN_REFERENCE_PATH.read_text(encoding="utf-8") == render_scope_reference(
        spec,
        language="en",
    )


def test_openapi_generator_supports_outputs_outside_repository(tmp_path: Path) -> None:
    """The generator must succeed when callers select external output paths."""
    output_path = tmp_path / "openapi.json"
    zh_path = tmp_path / "zh" / "openapi-scopes.md"
    en_path = tmp_path / "en" / "openapi-scopes.md"
    script_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "scripts"
        / "update_openapi_json.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--output",
            str(output_path),
            "--zh-scope-output",
            str(zh_path),
            "--en-scope-output",
            str(en_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert str(output_path) in completed.stdout
    assert output_path.is_file()
    assert zh_path.is_file()
    assert en_path.is_file()
