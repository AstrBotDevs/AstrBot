import asyncio
import os
import uuid
import time
from urllib.parse import urlparse, unquote
import platform


class FileTokenService:
    """维护一个简单的基于令牌的文件下载服务，支持超时和懒清除。"""

    def __init__(self, default_timeout: float = 300):
        self.lock = asyncio.Lock()
        self.staged_files = {}  # token: (file_path, expire_time)
        self.default_timeout = default_timeout

    async def _cleanup_expired_tokens(self):
        """清理过期的令牌"""
        now = time.time()
        expired_tokens = [
            token for token, (_, expire) in self.staged_files.items() if expire < now
        ]
        for token in expired_tokens:
            self.staged_files.pop(token, None)

    async def register_file(self, file_path: str, timeout: float = None) -> str:
        """向令牌服务注册一个文件。

        Args:
            file_path(str): 文件路径
            timeout(float): 超时时间，单位秒（可选）

        Returns:
            str: 一个单次令牌

        Raises:
            FileNotFoundError: 当路径不存在时抛出
        """

        # 处理 file:///
        try:
            parsed_uri = urlparse(file_path)
            if parsed_uri.scheme == "file":
                local_path = unquote(parsed_uri.path)
                if platform.system() == "Windows" and local_path.startswith("/"):
                    local_path = local_path[1:]
            else:
                # 如果没有 file:/// 前缀，则认为是普通路径
                local_path = file_path
        except Exception:
            # 解析失败时，按原路径处理
            local_path = file_path

        async with self.lock:
            await self._cleanup_expired_tokens()

            if not os.path.exists(local_path):
                raise FileNotFoundError(
                    f"文件不存在: {local_path} (原始输入: {file_path})"
                )

            file_token = str(uuid.uuid4())
            expire_time = time.time() + (
                timeout if timeout is not None else self.default_timeout
            )
            # 存储转换后的真实路径
            self.staged_files[file_token] = (local_path, expire_time)
            return file_token

    async def handle_file(self, file_token: str) -> str:
        """根据令牌获取文件路径，使用后令牌失效。

        Args:
            file_token(str): 注册时返回的令牌

        Returns:
            str: 文件路径

        Raises:
            KeyError: 当令牌不存在或已过期时抛出
            FileNotFoundError: 当文件本身已被删除时抛出
        """
        async with self.lock:
            await self._cleanup_expired_tokens()

            if file_token not in self.staged_files:
                raise KeyError(f"无效或过期的文件 token: {file_token}")

            file_path, _ = self.staged_files.pop(file_token)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            return file_path
