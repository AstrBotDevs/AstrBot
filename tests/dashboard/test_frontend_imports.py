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
            if rel in AXIOS_ALLOWLIST:
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
        violations: list[str] = []

        for src in _iter_source_files():
            rel = _relative(src)
            if rel in fetch_allowlist:
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
