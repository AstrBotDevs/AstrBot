"""TokenManager 单元测试"""

import os
import tempfile
from unittest.mock import patch

import pytest


class TestTokenManager:
    """TokenManager 测试类"""

    @pytest.fixture
    def temp_data_path(self):
        """创建临时数据目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def token_manager(self, temp_data_path):
        """创建 TokenManager 实例"""
        with patch(
            "astrbot.core.platform.sources.cli.config.token_manager.get_astrbot_data_path",
            return_value=temp_data_path,
        ):
            from astrbot.core.platform.sources.cli.config.token_manager import (
                TokenManager,
            )

            return TokenManager()

    def test_generate_new_token(self, token_manager, temp_data_path):
        """测试首次生成 Token"""
        token = token_manager.token
        assert token is not None
        assert len(token) > 0

        # 验证 Token 文件已创建
        token_file = os.path.join(temp_data_path, ".cli_token")
        assert os.path.exists(token_file)

    def test_load_existing_token(self, temp_data_path):
        """测试加载已存在的 Token"""
        # 预先写入 Token
        token_file = os.path.join(temp_data_path, ".cli_token")
        expected_token = "test_token_12345"
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(expected_token)

        with patch(
            "astrbot.core.platform.sources.cli.config.token_manager.get_astrbot_data_path",
            return_value=temp_data_path,
        ):
            from astrbot.core.platform.sources.cli.config.token_manager import (
                TokenManager,
            )

            manager = TokenManager()
            assert manager.token == expected_token

    def test_validate_correct_token(self, token_manager):
        """测试验证正确的 Token"""
        token = token_manager.token
        assert token_manager.validate(token) is True

    def test_validate_wrong_token(self, token_manager):
        """测试验证错误的 Token"""
        _ = token_manager.token  # 确保 Token 已生成
        assert token_manager.validate("wrong_token") is False

    def test_validate_empty_token(self, token_manager):
        """测试验证空 Token"""
        _ = token_manager.token  # 确保 Token 已生成
        assert token_manager.validate("") is False

    def test_validate_without_server_token(self, temp_data_path):
        """测试服务器无 Token 时跳过验证"""
        with patch(
            "astrbot.core.platform.sources.cli.config.token_manager.get_astrbot_data_path",
            return_value=temp_data_path,
        ):
            from astrbot.core.platform.sources.cli.config.token_manager import (
                TokenManager,
            )

            manager = TokenManager()
            # 模拟 _ensure_token 返回 None（Token 生成失败场景）
            with patch.object(manager, "_ensure_token", return_value=None):
                manager._token = None  # 重置缓存

                # 无 Token 时应跳过验证
                assert manager.validate("any_token") is True

    def test_regenerate_empty_token_file(self, temp_data_path):
        """测试空 Token 文件时重新生成"""
        # 创建空 Token 文件
        token_file = os.path.join(temp_data_path, ".cli_token")
        with open(token_file, "w", encoding="utf-8") as f:
            f.write("")

        with patch(
            "astrbot.core.platform.sources.cli.config.token_manager.get_astrbot_data_path",
            return_value=temp_data_path,
        ):
            from astrbot.core.platform.sources.cli.config.token_manager import (
                TokenManager,
            )

            manager = TokenManager()
            token = manager.token

            # 应该生成新 Token
            assert token is not None
            assert len(token) > 0
