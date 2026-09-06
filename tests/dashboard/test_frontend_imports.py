"""Regression tests for frontend HTTP client conventions.

Ensures dashboard source files always use the project's custom request
module instead of importing axios directly, and that API fetch URLs are
resolved through ``resolveApiUrl``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DASHBOARD_SRC = Path(__file__).parent.parent.parent / "dashboard" / "src"

# Files that are allowed to import axios directly (the wrapper itself).
AXIOS_ALLOWLIST: set[str] = {
    "dashboard/src/utils/request.ts",
}

# TODO: Migrate these files to @/utils/request instead of direct axios.
# These are pre-existing violations discovered after merging origin/master.
AXIOS_EXISTING_VIOLATIONS: set[str] = {
    "dashboard/src/composables/useMessages.ts",
    "dashboard/src/composables/useProviderModelConfigDialog.ts",
    "dashboard/src/components/chat/Chat.vue",
    "dashboard/src/components/chat/ChatMessageList.vue",
    "dashboard/src/components/chat/MessageListDEPRECATED.vue",
    "dashboard/src/components/chat/ProviderModelMenu.vue",
    "dashboard/src/components/chat/RegenerateMenu.vue",
    "dashboard/src/components/chat/ThreadPanel.vue",
    "dashboard/src/components/platform/PlatformRegistrationAction.vue",
    "dashboard/src/views/ConsolePage.vue",
    "dashboard/src/views/CronJobPage.vue",
    "dashboard/src/views/PluginPagePage.vue",
    "dashboard/src/views/SubAgentPage.vue",
    "dashboard/src/views/TracePage.vue",
    "dashboard/src/views/authentication/auth/SetupPage.vue",
    "dashboard/src/views/extension/PluginDetailPage.vue",
}


def _iter_source_files() -> list[Path]:
    """Return all .ts and .vue files under dashboard/src."""
    return sorted(DASHBOARD_SRC.rglob("*.ts")) + sorted(DASHBOARD_SRC.rglob("*.vue"))


def _relative(path: Path) -> str:
    """Return a repo-relative path string for readable error messages."""
    parts = path.parts
    try:
        idx = parts.index("dashboard")
    except ValueError:
        return str(path)
    return "/".join(parts[idx:])


class TestDashboardHttpClientConventions:
    """Prevent direct axios imports and bare API fetch URLs."""

    def test_no_direct_axios_imports(self) -> None:
        """Source files (except the wrapper) must not import plain axios."""
        direct_axios_pattern = re.compile(
            r"import\s+axios\s+from\s+['\"]axios['\"]",
            re.IGNORECASE,
        )
        violations: list[str] = []

        for src in _iter_source_files():
            rel = _relative(src)
            if rel in AXIOS_ALLOWLIST | AXIOS_EXISTING_VIOLATIONS:
                continue
            text = src.read_text(encoding="utf-8")
            if direct_axios_pattern.search(text):
                violations.append(rel)

        if violations:
            pytest.fail(
                "Direct axios imports found. Use `@/utils/request` instead:\n  - "
                + "\n  - ".join(violations)
            )

    def test_api_fetch_urls_use_resolve_api_url(self) -> None:
        """fetch() calls hitting /api/* must wrap the URL in resolveApiUrl()."""
        # Match fetch calls whose first arg starts with "/api/" and is NOT
        # already wrapped in resolveApiUrl.
        bare_api_fetch_pattern = re.compile(
            r"fetch\s*\(\s*['\"](/api/[^'\"]+)['\"]",
        )
        # Allowlist for legitimate non-API fetches (i18n, config, external).
        fetch_allowlist: set[str] = {
            # i18n loader loads JSON translation modules, not backend API.
            "dashboard/src/i18n/loader.ts",
            # main.ts may fetch runtime config before axios is configured.
            "dashboard/src/main.ts",
        }
        # TODO: Migrate these bare fetch() calls to resolveApiUrl().
        fetch_existing_violations: set[str] = {
            "dashboard/src/composables/useMessages.ts",
            "dashboard/src/components/chat/ThreadPanel.vue",
        }
        violations: list[str] = []

        for src in _iter_source_files():
            rel = _relative(src)
            if rel in fetch_allowlist | fetch_existing_violations:
                continue
            text = src.read_text(encoding="utf-8")
            for match in bare_api_fetch_pattern.finditer(text):
                url = match.group(1)
                # SSE/live-log endpoints are handled via resolveApiUrl in stores/common.ts.
                violations.append(f"{rel}: fetch('{url}')")

        if violations:
            pytest.fail(
                "Bare fetch() calls to API paths must use resolveApiUrl():\n  - "
                + "\n  - ".join(violations)
            )
