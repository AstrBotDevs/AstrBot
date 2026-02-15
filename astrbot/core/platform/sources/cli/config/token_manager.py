"""Token管理器

负责认证Token的生成、读取和验证。
"""

import os
import secrets

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class TokenManager:
    """Token管理器

    I/O契约:
        Input: None
        Output: token (str | None)
    """

    TOKEN_FILE = ".cli_token"

    def __init__(self):
        """初始化Token管理器"""
        self._token: str | None = None
        self._token_file = os.path.join(get_astrbot_data_path(), self.TOKEN_FILE)

    @property
    def token(self) -> str | None:
        """获取当前Token"""
        if self._token is None:
            self._token = self._ensure_token()
        return self._token

    def _ensure_token(self) -> str | None:
        """确保Token存在，不存在则自动生成

        Returns:
            Token字符串或None
        """
        try:
            # 如果token文件已存在，直接读取
            if os.path.exists(self._token_file):
                with open(self._token_file, encoding="utf-8") as f:
                    token = f.read().strip()

                if token:
                    logger.info("Authentication token loaded from file")
                    return token
                else:
                    logger.warning("Token file is empty, regenerating")

            # 首次启动或token为空，自动生成新token
            token = secrets.token_urlsafe(32)

            # 写入文件
            with open(self._token_file, "w", encoding="utf-8") as f:
                f.write(token)

            # 设置严格权限（仅所有者可读写）
            try:
                os.chmod(self._token_file, 0o600)
            except OSError:
                # Windows可能不支持chmod
                pass

            logger.info("Generated new authentication token: %s", token)
            logger.info("Token saved to: %s", self._token_file)
            return token

        except Exception as e:
            logger.error("Failed to ensure token: %s", e)
            logger.warning("Authentication disabled due to token error")
            return None

    def validate(self, provided_token: str) -> bool:
        """验证提供的Token

        Args:
            provided_token: 待验证的Token

        Returns:
            验证是否通过
        """
        if not self.token:
            # 无Token时跳过验证
            return True

        if not provided_token:
            logger.warning("Request rejected: missing auth_token")
            return False

        if provided_token != self.token:
            logger.warning(
                "Request rejected: invalid auth_token (length=%d)", len(provided_token)
            )
            return False

        return True
