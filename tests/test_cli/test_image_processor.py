"""ImageProcessor 单元测试"""

import base64
import os
import tempfile
from unittest.mock import MagicMock, patch


class TestImageCodec:
    """ImageCodec 测试类"""

    def test_encode(self):
        """测试 base64 编码"""
        from astrbot.core.platform.sources.cli.message.image_processor import ImageCodec

        data = b"Hello, World!"
        encoded = ImageCodec.encode(data)
        assert encoded == base64.b64encode(data).decode("utf-8")

    def test_decode(self):
        """测试 base64 解码"""
        from astrbot.core.platform.sources.cli.message.image_processor import ImageCodec

        original = b"Hello, World!"
        encoded = base64.b64encode(original).decode("utf-8")
        decoded = ImageCodec.decode(encoded)
        assert decoded == original


class TestImageFileIO:
    """ImageFileIO 测试类"""

    def test_read_existing_file(self):
        """测试读取存在的文件"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageFileIO,
        )

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            data = ImageFileIO.read(temp_path)
            assert data == b"test content"
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """测试读取不存在的文件"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageFileIO,
        )

        data = ImageFileIO.read("/nonexistent/path/file.png")
        assert data is None

    def test_write_temp(self):
        """测试写入临时文件"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageFileIO,
        )

        with patch(
            "astrbot.core.platform.sources.cli.message.image_processor.get_astrbot_temp_path"
        ) as mock_temp:
            mock_temp.return_value = tempfile.gettempdir()

            data = b"test image data"
            temp_path = ImageFileIO.write_temp(data, suffix=".png")

            assert temp_path is not None
            assert os.path.exists(temp_path)

            with open(temp_path, "rb") as f:
                assert f.read() == data

            os.unlink(temp_path)


class TestImageInfo:
    """ImageInfo 测试类"""

    def test_to_dict_url(self):
        """测试 URL 类型转字典"""
        from astrbot.core.platform.sources.cli.message.image_processor import ImageInfo

        info = ImageInfo(type="url", url="https://example.com/image.png")
        result = info.to_dict()

        assert result["type"] == "url"
        assert result["url"] == "https://example.com/image.png"

    def test_to_dict_file(self):
        """测试文件类型转字典"""
        from astrbot.core.platform.sources.cli.message.image_processor import ImageInfo

        info = ImageInfo(type="file", path="/path/to/image.png", size=1024)
        result = info.to_dict()

        assert result["type"] == "file"
        assert result["path"] == "/path/to/image.png"
        assert result["size"] == 1024

    def test_to_dict_with_error(self):
        """测试带错误信息转字典"""
        from astrbot.core.platform.sources.cli.message.image_processor import ImageInfo

        info = ImageInfo(type="file", error="Failed to read")
        result = info.to_dict()

        assert result["error"] == "Failed to read"


class TestImageExtractor:
    """ImageExtractor 测试类"""

    def test_extract_url_image(self):
        """测试提取 URL 图片"""
        from astrbot.core.message.components import Image
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageExtractor,
        )

        chain = MagicMock()
        chain.chain = [Image(file="https://example.com/image.png")]

        images = ImageExtractor.extract(chain)

        assert len(images) == 1
        assert images[0].type == "url"
        assert images[0].url == "https://example.com/image.png"

    def test_extract_empty_chain(self):
        """测试提取空消息链"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageExtractor,
        )

        chain = MagicMock()
        chain.chain = []

        images = ImageExtractor.extract(chain)
        assert len(images) == 0

    def test_extract_mixed_components(self):
        """测试提取混合组件"""
        from astrbot.core.message.components import Image, Plain
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageExtractor,
        )

        chain = MagicMock()
        chain.chain = [
            Plain("Hello"),
            Image(file="https://example.com/1.png"),
            Plain("World"),
            Image(file="https://example.com/2.png"),
        ]

        images = ImageExtractor.extract(chain)

        assert len(images) == 2
        assert images[0].url == "https://example.com/1.png"
        assert images[1].url == "https://example.com/2.png"


class TestChainPreprocessor:
    """ChainPreprocessor 测试类"""

    def test_preprocess_local_file(self):
        """测试预处理本地文件图片"""
        from astrbot.core.message.components import Image
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ChainPreprocessor,
        )

        # 创建临时图片文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(b"fake image data")
            temp_path = f.name

        try:
            chain = MagicMock()
            image = Image(file=f"file:///{temp_path}")
            chain.chain = [image]

            ChainPreprocessor.preprocess(chain)

            # 验证已转换为 base64
            assert image.file.startswith("base64://")
            base64_data = image.file[9:]
            decoded = base64.b64decode(base64_data)
            assert decoded == b"fake image data"
        finally:
            os.unlink(temp_path)

    def test_preprocess_url_unchanged(self):
        """测试 URL 图片不变"""
        from astrbot.core.message.components import Image
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ChainPreprocessor,
        )

        chain = MagicMock()
        image = Image(file="https://example.com/image.png")
        chain.chain = [image]

        ChainPreprocessor.preprocess(chain)

        # URL 应保持不变
        assert image.file == "https://example.com/image.png"


class TestImageProcessor:
    """ImageProcessor 门面测试类"""

    def test_local_file_to_base64(self):
        """测试本地文件转 base64"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageProcessor,
        )

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            temp_path = f.name

        try:
            result = ImageProcessor.local_file_to_base64(temp_path)
            assert result == base64.b64encode(b"test data").decode("utf-8")
        finally:
            os.unlink(temp_path)

    def test_local_file_to_base64_nonexistent(self):
        """测试不存在的文件"""
        from astrbot.core.platform.sources.cli.message.image_processor import (
            ImageProcessor,
        )

        result = ImageProcessor.local_file_to_base64("/nonexistent/file.png")
        assert result is None
