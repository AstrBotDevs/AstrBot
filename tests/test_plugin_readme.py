from pathlib import Path

import pytest

from astrbot.dashboard.services.plugin_service import (
    PLUGIN_README_MAX_BYTES,
    PluginService,
    PluginServiceError,
)


def _empty_plugin_service() -> PluginService:
    return PluginService.__new__(PluginService)


def test_readme_filename_candidates_prefers_exact_locale() -> None:
    assert PluginService._readme_filename_candidates("zh-CN") == [
        "README_zh-CN.md",
        "README-zh-CN.md",
        "README.zh-CN.md",
        "README_zh.md",
        "README-zh.md",
        "README.zh.md",
        "README.md",
    ]


def test_readme_filename_candidates_reject_path_traversal() -> None:
    with pytest.raises(PluginServiceError):
        PluginService._readme_filename_candidates("../private")


def test_local_readme_uses_case_insensitive_locale_file(tmp_path: Path) -> None:
    (tmp_path / "readme_EN-us.md").write_text("English docs", encoding="utf-8")
    (tmp_path / "README.md").write_text("Default docs", encoding="utf-8")

    data, _ = _empty_plugin_service()._read_local_readme(
        "astrbot_plugin_demo",
        tmp_path,
        "en-US",
    )

    assert data == {
        "content": "English docs",
        "locale": "en-US",
        "filename": "readme_EN-us.md",
    }


def test_local_readme_falls_back_to_only_localized_file(tmp_path: Path) -> None:
    (tmp_path / "README_zh.md").write_text("中文文档", encoding="utf-8")

    data, _ = _empty_plugin_service()._read_local_readme(
        "astrbot_plugin_demo",
        tmp_path,
        "en-US",
    )

    assert data["content"] == "中文文档"
    assert data["filename"] == "README_zh.md"


def test_local_readme_rejects_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"x" * (PLUGIN_README_MAX_BYTES + 1))

    with pytest.raises(PluginServiceError, match="size limit"):
        _empty_plugin_service()._read_local_readme(
            "astrbot_plugin_demo",
            tmp_path,
            None,
        )


@pytest.mark.asyncio
async def test_market_readme_uses_github_localized_candidate(monkeypatch) -> None:
    service = _empty_plugin_service()
    requested_urls: list[str] = []

    async def fake_get_online_plugins(**_kwargs):
        return {
            "owner/astrbot_plugin_demo": {
                "author": "owner",
                "name": "astrbot_plugin_demo",
                "repo": "https://github.com/owner/astrbot_plugin_demo",
            }
        }, None

    async def fake_fetch_remote_readme(url: str):
        requested_urls.append(url)
        if url.endswith("/README_zh.md"):
            return "中文 README"
        return None

    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(service, "_fetch_remote_readme", fake_fetch_remote_readme)

    data, _ = await service.get_market_plugin_readme(
        plugin_id="owner/astrbot_plugin_demo",
        locale="zh-CN",
    )

    assert data["content"] == "中文 README"
    assert data["filename"] == "README_zh.md"
    assert requested_urls[0].endswith("/README_zh-CN.md")
    assert requested_urls[-1].endswith("/README_zh.md")


@pytest.mark.asyncio
async def test_market_readme_prefers_explicit_readme_url(monkeypatch) -> None:
    service = _empty_plugin_service()
    requested_urls: list[str] = []

    async def fake_get_online_plugins(**_kwargs):
        return {
            "owner/astrbot_plugin_demo": {
                "author": "owner",
                "name": "astrbot_plugin_demo",
                "repo": "https://git.example.com/owner/astrbot_plugin_demo",
                "readme_url": "https://docs.example.com/README.md",
            }
        }, None

    async def fake_fetch_remote_readme(url: str):
        requested_urls.append(url)
        return "# Docs"

    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(service, "_fetch_remote_readme", fake_fetch_remote_readme)

    data, _ = await service.get_market_plugin_readme(
        plugin_id="owner/astrbot_plugin_demo",
        locale="ja-JP",
    )

    assert requested_urls == ["https://docs.example.com/README.md"]
    assert data["filename"] == "README.md"


@pytest.mark.asyncio
async def test_market_readme_rejects_non_github_repository_without_url(
    monkeypatch,
) -> None:
    service = _empty_plugin_service()

    async def fake_get_online_plugins(**_kwargs):
        return {
            "owner/astrbot_plugin_demo": {
                "author": "owner",
                "name": "astrbot_plugin_demo",
                "repo": "https://git.example.com/owner/astrbot_plugin_demo",
            }
        }, None

    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)

    with pytest.raises(PluginServiceError, match="only supports GitHub"):
        await service.get_market_plugin_readme(
            plugin_id="owner/astrbot_plugin_demo",
            locale="en-US",
        )


@pytest.mark.asyncio
async def test_market_readme_supports_scp_github_repository(monkeypatch) -> None:
    service = _empty_plugin_service()
    requested_urls: list[str] = []

    async def fake_get_online_plugins(**_kwargs):
        return {
            "owner/astrbot_plugin_demo": {
                "author": "owner",
                "name": "astrbot_plugin_demo",
                "repo": "git@github.com:owner/astrbot_plugin_demo.git",
            }
        }, None

    async def fake_fetch_remote_readme(url: str):
        requested_urls.append(url)
        return "# Default README"

    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(service, "_fetch_remote_readme", fake_fetch_remote_readme)

    data, _ = await service.get_market_plugin_readme(
        plugin_id="owner/astrbot_plugin_demo",
        locale="en-US",
    )

    assert data["filename"] == "README_en-US.md"
    assert requested_urls == [
        "https://raw.githubusercontent.com/owner/astrbot_plugin_demo/HEAD/README_en-US.md"
    ]


@pytest.mark.asyncio
async def test_market_readme_does_not_fallback_to_chinese_for_other_locale(
    monkeypatch,
) -> None:
    service = _empty_plugin_service()

    async def fake_get_online_plugins(**_kwargs):
        return {
            "owner/astrbot_plugin_demo": {
                "author": "owner",
                "name": "astrbot_plugin_demo",
                "repo": "https://github.com/owner/astrbot_plugin_demo",
            }
        }, None

    async def fake_fetch_remote_readme(url: str):
        if url.endswith("/README_zh.md"):
            return "# 中文 README"
        return None

    monkeypatch.setattr(service, "get_online_plugins", fake_get_online_plugins)
    monkeypatch.setattr(service, "_fetch_remote_readme", fake_fetch_remote_readme)

    with pytest.raises(PluginServiceError, match="not found"):
        await service.get_market_plugin_readme(
            plugin_id="owner/astrbot_plugin_demo",
            locale="en-US",
        )


@pytest.mark.asyncio
async def test_readme_url_rejects_private_address() -> None:
    with pytest.raises(PluginServiceError, match="non-public"):
        await PluginService._validate_public_readme_url("https://127.0.0.1/README.md")
