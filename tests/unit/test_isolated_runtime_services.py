"""Regression tests for test-owned runtime service construction."""

import base64
from pathlib import Path

import pytest

from tests.fixtures.helpers import create_isolated_runtime_services


@pytest.mark.asyncio
async def test_isolated_runtime_services_do_not_use_repository_data(tmp_path: Path):
    services = create_isolated_runtime_services(
        tmp_path, tmp_path / "data" / "db.sqlite"
    )

    try:
        assert Path(services.config.config_path).is_relative_to(tmp_path)
        assert Path(services.db.db_path).is_relative_to(tmp_path)
        assert Path(services.preferences.path).is_relative_to(tmp_path)
        assert services.config["platform"] == []
    finally:
        await services.metrics.shutdown()
        await services.preferences.terminate()


@pytest.mark.asyncio
async def test_isolated_runtime_services_do_not_share_computer_or_tool_images(
    tmp_path: Path,
):
    """Each runtime owns independent mutable computer and image-cache state."""
    first = create_isolated_runtime_services(
        tmp_path / "first",
        tmp_path / "first" / "data" / "db.sqlite",
    )
    second = create_isolated_runtime_services(
        tmp_path / "second",
        tmp_path / "second" / "data" / "db.sqlite",
    )

    try:
        assert first.computer_runtime is not second.computer_runtime
        assert first.tool_image_cache is not second.tool_image_cache
        assert first.llm_metadata_catalog is not second.llm_metadata_catalog

        first.llm_metadata_catalog.replace(
            {
                "first-model": {
                    "id": "first-model",
                    "reasoning": False,
                    "tool_call": False,
                    "knowledge": "none",
                    "release_date": "",
                    "modalities": {"input": ["text"], "output": ["text"]},
                    "open_weights": False,
                    "limit": {"context": 1, "output": 1},
                }
            }
        )
        assert second.llm_metadata_catalog.get("first-model") is None

        cached = first.tool_image_cache.save_image(
            base64.b64encode(b"first-runtime").decode(),
            tool_call_id="call-1",
            tool_name="example",
        )

        assert (
            second.tool_image_cache.get_image_base64_by_path(cached.file_path) is None
        )
    finally:
        await first.metrics.shutdown()
        await second.metrics.shutdown()
        await first.computer_runtime.terminate()
        await second.computer_runtime.terminate()
        await first.preferences.terminate()
        await second.preferences.terminate()
