"""Static guard for the developer API key scope registry.

Knowledge-base routes require the ``kb`` scope, but ``kb`` was missing from
``ALL_OPEN_API_SCOPES``.  ``_require_api_key_scope`` rejects any scope outside
that tuple *before* the API key is even loaded, so a ``kb``-scoped key could
neither be created nor used and every knowledge-base call returned 403
(issue #10322).

The tests below walk the ``astrbot`` package and check every scope that is
written down statically, so a route can no longer require a scope that the
registry never hands out.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path

from astrbot.dashboard.services.auth_service import ALL_OPEN_API_SCOPES

REPO_ROOT = Path(__file__).resolve().parents[1]
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
    """Return the AST node holding the scope argument of a call."""
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
