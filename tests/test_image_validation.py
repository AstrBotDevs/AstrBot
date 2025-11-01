"""Test image component validation for empty base64 data."""

import os

import pytest

from astrbot.core.message.components import Image, Record
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class TestImageValidation:
    """Test Image component validation for empty base64 data."""

    @pytest.mark.asyncio
    async def test_empty_base64_in_convert_to_file_path(self):
        """Test that empty base64 data raises ValueError in convert_to_file_path."""
        # Create an Image with empty base64 data
        image = Image(file="base64://")

        # Should raise ValueError when trying to convert to file path
        with pytest.raises(ValueError, match="Base64 data is empty for image"):
            await image.convert_to_file_path()

    @pytest.mark.asyncio
    async def test_empty_base64_in_convert_to_base64(self):
        """Test that empty base64 data raises ValueError in convert_to_base64."""
        # Create an Image with empty base64 data
        image = Image(file="base64://")

        # Should raise ValueError when trying to convert to base64
        with pytest.raises(ValueError, match="Base64 data is empty for image"):
            await image.convert_to_base64()

    @pytest.mark.asyncio
    async def test_valid_base64_in_convert_to_file_path(self, tmp_path):
        """Test that valid base64 data works correctly in convert_to_file_path."""
        # Ensure temp directory exists
        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Create a small valid base64 image (1x1 transparent PNG)
        valid_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg=="
        image = Image(file=f"base64://{valid_base64}")

        # Should successfully convert to file path
        file_path = await image.convert_to_file_path()
        assert file_path is not None
        assert isinstance(file_path, str)
        assert len(file_path) > 0

    @pytest.mark.asyncio
    async def test_valid_base64_in_convert_to_base64(self):
        """Test that valid base64 data works correctly in convert_to_base64."""
        # Create a small valid base64 image
        valid_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+P+/HgAFhAJ/wlseKgAAAABJRU5ErkJggg=="
        image = Image(file=f"base64://{valid_base64}")

        # Should successfully convert to base64
        result = await image.convert_to_base64()
        assert result is not None
        assert result == valid_base64


class TestRecordValidation:
    """Test Record component validation for empty base64 data."""

    @pytest.mark.asyncio
    async def test_empty_base64_in_convert_to_file_path(self):
        """Test that empty base64 data raises ValueError in convert_to_file_path."""
        # Create a Record with empty base64 data
        record = Record(file="base64://")

        # Should raise ValueError when trying to convert to file path
        with pytest.raises(ValueError, match="Base64 data is empty for record"):
            await record.convert_to_file_path()

    @pytest.mark.asyncio
    async def test_empty_base64_in_convert_to_base64(self):
        """Test that empty base64 data raises ValueError in convert_to_base64."""
        # Create a Record with empty base64 data
        record = Record(file="base64://")

        # Should raise ValueError when trying to convert to base64
        with pytest.raises(ValueError, match="Base64 data is empty for record"):
            await record.convert_to_base64()
