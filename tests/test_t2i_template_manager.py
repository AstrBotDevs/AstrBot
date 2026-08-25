import hashlib
from pathlib import Path

import pytest

from astrbot.core.utils.t2i import template_manager

LEGACY_TEMPLATE = "<html>\n<body>legacy default</body>\n</html>\n"
CURRENT_TEMPLATE = "<html>\n<body>current default</body>\n</html>\n"
CUSTOM_TEMPLATE = "<html>\n<body>customized by user</body>\n</html>\n"


@pytest.mark.parametrize(
    ("user_content", "expected_content"),
    [
        pytest.param(None, CURRENT_TEMPLATE, id="missing-template"),
        pytest.param(LEGACY_TEMPLATE, CURRENT_TEMPLATE, id="legacy-template"),
        pytest.param(
            LEGACY_TEMPLATE.replace("\n", "\r\n"),
            CURRENT_TEMPLATE,
            id="legacy-template-crlf",
        ),
        pytest.param(CUSTOM_TEMPLATE, CUSTOM_TEMPLATE, id="custom-template"),
    ],
)
def test_initialize_user_templates_migrates_only_unmodified_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    user_content: str | None,
    expected_content: str,
) -> None:
    """Verify automatic migration preserves customized user templates.

    Args:
        monkeypatch: Pytest fixture used to isolate AstrBot paths and legacy hashes.
        tmp_path: Temporary directory used for built-in and user templates.
        user_content: Existing user template content, or None when it is missing.
        expected_content: Template content expected after manager initialization.
    """
    builtin_root = tmp_path / "astrbot-root"
    builtin_dir = builtin_root / "astrbot/core/utils/t2i/template"
    builtin_dir.mkdir(parents=True)
    (builtin_dir / "base.html").write_text(CURRENT_TEMPLATE, encoding="utf-8")

    data_root = tmp_path / "data"
    user_dir = data_root / "t2i_templates"
    if user_content is not None:
        user_dir.mkdir(parents=True)
        (user_dir / "base.html").write_text(user_content, encoding="utf-8")

    legacy_hash = hashlib.sha256(LEGACY_TEMPLATE.encode()).hexdigest()
    monkeypatch.setattr(
        template_manager,
        "_LEGACY_CORE_TEMPLATE_HASHES",
        {"base.html": frozenset({legacy_hash})},
    )
    monkeypatch.setattr(
        template_manager,
        "get_astrbot_path",
        lambda: str(builtin_root),
    )
    monkeypatch.setattr(
        template_manager,
        "get_astrbot_data_path",
        lambda: str(data_root),
    )

    template_manager.TemplateManager()

    assert (user_dir / "base.html").read_text(encoding="utf-8") == expected_content
