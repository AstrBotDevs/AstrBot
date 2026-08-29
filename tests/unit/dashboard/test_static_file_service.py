from pathlib import Path

from astrbot.dashboard.services.static_file_service import StaticFileService


def test_resolve_static_file_serves_help_index_and_html_fallback(
    tmp_path: Path,
) -> None:
    help_dir = tmp_path / "help" / "platform"
    help_dir.mkdir(parents=True)
    (tmp_path / "help" / "index.html").write_text("docs-index", encoding="utf-8")
    (help_dir / "napcat.html").write_text("napcat", encoding="utf-8")

    service = StaticFileService()

    index = service.resolve_static_file(tmp_path, "help")
    assert index is not None
    assert index.read_text(encoding="utf-8") == "docs-index"

    trailing = service.resolve_static_file(tmp_path, "help/")
    assert trailing == index

    page = service.resolve_static_file(tmp_path, "help/platform/napcat")
    assert page is not None
    assert page.read_text(encoding="utf-8") == "napcat"


def test_not_found_message_does_not_point_upstream() -> None:
    message = StaticFileService().get_not_found_message()
    assert "docs.astrbot.app" not in message
    assert "make run" in message


def test_index_routes_use_current_dashboard_paths() -> None:
    routes = StaticFileService().list_index_routes()
    assert "/dashboard" in routes
    assert "/dashboard/default" not in routes
    assert "/console" not in routes
    assert "/conversation" not in routes
    assert "/logs" not in routes
    assert "/tool-use" not in routes
