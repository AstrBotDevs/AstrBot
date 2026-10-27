import ast
import json
from functools import lru_cache
from pathlib import Path

from astrbot.dashboard.services.auth_service import ALL_OPEN_API_SCOPES
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
    assert system_config_update["x-astrbot-sensitive-scopes"] == ["config:edit_admin"]
    assert "`config:edit_admin`" in system_config_update["description"]


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


REPO_ROOT = Path(__file__).resolve().parents[2]
ASTRBOT_ROOT = REPO_ROOT / "astrbot"

# Call sites that bind a scope: ``require_scope(request, "<scope>")`` and the
# OpenAPI-aware dependency ``ScopeDependency("<scope>")``.  The position of the
# scope argument differs between the two.
SCOPE_ARGUMENT_INDEX = {
    "require_scope": 1,
    "ScopeDependency": 0,
}

# Scopes that gate dashboard administration endpoints (restart, updates, logs,
# stats, cron, backups, API-key management, tool permissions).  They are
# intentionally not grantable to API keys so a leaked key cannot administer the
# instance.  They are listed explicitly so that every new scope has to be
# classified as either grantable or dashboard-only - the decision that was
# missed for ``kb``.
DASHBOARD_ONLY_SCOPES = frozenset({"system", "tool"})


def _scope_call_argument(node: ast.Call, index: int) -> ast.expr | None:
    """Return the AST node holding the scope argument of a call.

    Args:
        node: Scope-checking call expression.
        index: Positional index of its scope argument.

    Returns:
        The scope argument expression, or None when it is absent.
    """
    for keyword in node.keywords:
        if keyword.arg == "scope":
            return keyword.value
    if len(node.args) > index:
        return node.args[index]
    return None


@lru_cache(maxsize=1)
def _collect_scope_arguments() -> tuple[dict[str, list[str]], list[str]]:
    """Collect statically written scopes and dynamic call sites.

    Returns:
        A mapping of scope literal to the ``path:line`` locations using it, plus
        the locations whose scope argument is computed at runtime.
    """
    literals: dict[str, list[str]] = {}
    dynamic: list[str] = []
    for path in sorted(ASTRBOT_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            )
            if name not in SCOPE_ARGUMENT_INDEX:
                continue
            location = f"{path.relative_to(REPO_ROOT).as_posix()}:{node.lineno}"
            argument = _scope_call_argument(node, SCOPE_ARGUMENT_INDEX[name])
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                literals.setdefault(argument.value, []).append(location)
            else:
                dynamic.append(location)
    return literals, dynamic


def test_every_static_scope_is_grantable():
    """Every scope written in the code must be classified in the registry."""
    literals, dynamic = _collect_scope_arguments()
    call_sites = sum(len(locations) for locations in literals.values())
    unclassified = {
        scope: locations
        for scope, locations in literals.items()
        if scope not in ALL_OPEN_API_SCOPES and scope not in DASHBOARD_ONLY_SCOPES
    }
    assert not unclassified, (
        f"{call_sites} static scope call sites over {len(literals)} scopes and "
        f"{len(dynamic)} dynamic call sites skipped; these scopes are neither "
        f"grantable to API keys (ALL_OPEN_API_SCOPES) nor declared "
        f"dashboard-only: {unclassified}"
    )


def test_dashboard_only_scopes_are_not_grantable():
    """The dashboard-only list must not overlap the grantable scopes."""
    assert DASHBOARD_ONLY_SCOPES.isdisjoint(ALL_OPEN_API_SCOPES)


def test_knowledge_base_scope_is_grantable():
    """The knowledge-base routes' scope must exist in the registry."""
    literals, _ = _collect_scope_arguments()
    assert "kb" in literals, (
        f"expected a route to call require_scope(..., 'kb'); found: {sorted(literals)}"
    )
    assert "kb" in ALL_OPEN_API_SCOPES, (
        f"knowledge-base routes require the 'kb' scope, which is missing from "
        f"ALL_OPEN_API_SCOPES: {ALL_OPEN_API_SCOPES}"
    )
