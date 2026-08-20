from __future__ import annotations

from tests.unit.dashboard.dashboard_lifecycle_support import *  # noqa: F403


def test_access_log_redacts_plugin_page_and_file_handles():
    logger = object.__new__(_ProxyAwareHypercornLogger)

    def atoms(path: str, query: bytes = b"secret=query"):
        return logger.atoms(
            {
                "type": "http",
                "method": "GET",
                "path": path,
                "query_string": query,
                "headers": [],
                "http_version": "1.1",
                "scheme": "https",
                "client": ("127.0.0.1", 1234),
            },
            {"status": 404, "headers": [(b"content-length", b"0")]},
            0.01,
        )

    page = atoms("/api/plugin-pages/v1/sessions/page-secret/")
    file = atoms("/api/plugin-files/v1/file-secret")
    assert "page-secret" not in page["r"]
    assert "file-secret" not in file["r"]
    assert page["U"] == "/api/plugin-pages/v1/sessions/<redacted>/"
    assert file["U"] == "/api/plugin-files/v1/<redacted>"
    assert page["q"] == file["q"] == ""


def test_dashboard_uses_bundled_dist_when_data_dist_is_stale(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    user_dist.mkdir(parents=True)
    bundled_dist.mkdir()
    (bundled_dist / "index.html").write_text("bundled", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )
    monkeypatch.setattr(
        "astrbot.application.should_use_bundled_dashboard_dist",
        lambda *_args, **_kwargs: True,
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path == str(user_dist)


def test_dashboard_prefers_repo_dist_when_data_dist_matches(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    from astrbot.core.config.default import VERSION

    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    repo_dist = tmp_path / "repo-dist"
    (user_dist / "assets").mkdir(parents=True)
    (repo_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (user_dist / "index.html").write_text("user", encoding="utf-8")
    (repo_dist / "assets" / "version").write_text(f"v{VERSION}", encoding="utf-8")
    (repo_dist / "index.html").write_text("repo", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: repo_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: tmp_path / "bundled-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path == str(repo_dist)


def test_dashboard_ignores_mismatched_data_dist_without_bundled(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")
    (user_dist / "index.html").write_text("stale", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path is None


def test_dashboard_ignores_incomplete_mismatched_data_dist_without_bundled(
    core_lifecycle_td: AstrBotCoreLifecycle,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "data"
    user_dist = data_dir / "dist"
    bundled_dist = tmp_path / "bundled-dist"
    (user_dist / "assets").mkdir(parents=True)
    (user_dist / "assets" / "version").write_text("v0.0.1", encoding="utf-8")

    monkeypatch.setattr(
        "astrbot.application.get_astrbot_data_path",
        lambda: str(data_dir),
    )
    monkeypatch.setattr(
        "astrbot.application.get_bundled_dashboard_dist_path",
        lambda: bundled_dist,
    )
    monkeypatch.setattr(
        "astrbot.application.get_repo_dashboard_dist_path",
        lambda: tmp_path / "repo-dist",
    )

    webui_dir = asyncio.run(resolve_dashboard_assets())
    shutdown_event = asyncio.Event()
    server = _create_dashboard(
        core_lifecycle_td.runtime,
        core_lifecycle_td,
        core_lifecycle_td.db,
        shutdown_event,
        webui_dir,
    )

    assert server.data_path is None
