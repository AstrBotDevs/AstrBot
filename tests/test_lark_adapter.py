"""Import smoke tests for astrbot.core.platform.sources.lark.lark_adapter."""


def test_import_and_class_exists() -> None:
    """Verify the module imports and the main class is accessible."""
    from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter

    assert LarkPlatformAdapter is not None
