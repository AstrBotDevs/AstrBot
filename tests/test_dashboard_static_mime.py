import mimetypes

from astrbot.dashboard.server import _ensure_static_asset_mime_types


def test_ensure_static_asset_mime_types_registers_javascript_types(monkeypatch):
    calls = []

    def fake_add_type(mime_type: str, extension: str, strict: bool = True):
        calls.append((mime_type, extension, strict))

    monkeypatch.setattr(mimetypes, "add_type", fake_add_type)

    _ensure_static_asset_mime_types()

    assert ("application/javascript", ".js", True) in calls
    assert ("application/javascript", ".mjs", True) in calls
