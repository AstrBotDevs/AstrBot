"""Import smoke tests for astrbot.core.utils.file_extract."""

from astrbot.core.utils import file_extract as file_extract_module
from astrbot.core.utils.file_extract import extract_file_moonshotai


class TestImports:
    def test_module_importable(self):
        assert file_extract_module is not None

    def test_extract_file_moonshotai_callable(self):
        assert callable(extract_file_moonshotai)

    def test_extract_file_moonshotai_is_async(self):
        import asyncio

        assert asyncio.iscoroutinefunction(extract_file_moonshotai)


class TestExtractFileMoonshotAiSignature:
    def test_function_name(self):
        assert extract_file_moonshotai.__name__ == "extract_file_moonshotai"

    def test_signature_has_file_path_and_api_key(self):
        import inspect

        sig = inspect.signature(extract_file_moonshotai)
        assert "file_path" in sig.parameters
        assert "api_key" in sig.parameters
