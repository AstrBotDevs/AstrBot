from astrbot.core.utils.astrbot_path import get_astrbot_root
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime


def test_desktop_client_env_marks_desktop_runtime_without_frozen(monkeypatch):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delattr("sys.frozen", raising=False)

    assert is_packaged_desktop_runtime() is True


def test_desktop_client_uses_home_root_without_explicit_astrbot_root(monkeypatch):
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    monkeypatch.delattr("sys.frozen", raising=False)

    assert get_astrbot_root().endswith(".astrbot")


def test_explicit_astrbot_root_overrides_desktop_default(monkeypatch, tmp_path):
    explicit_root = tmp_path / "astrbot-root"
    monkeypatch.setenv("ASTRBOT_DESKTOP_CLIENT", "1")
    monkeypatch.setenv("ASTRBOT_ROOT", str(explicit_root))
    monkeypatch.delattr("sys.frozen", raising=False)

    assert get_astrbot_root() == str(explicit_root.resolve())
