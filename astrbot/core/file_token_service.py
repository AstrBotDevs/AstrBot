import asyncio
import os
import uuid


class FileTokenService:
    """维护一个简单的基于令牌的文件下载服务"""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.staged_files = {}

    async def register_file(self, file_path: str) -> str:
        """向令牌服务注册一个文件。

        Args:
            file_path(str): 文件路径

        Returns:
            str: 一个单次令牌

        Raises:
            FileNotFoundError: 当路径不存在时抛出。
        """
        async with self.lock:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            file_token = str(uuid.uuid4())
            self.staged_files[file_token] = file_path
            return file_token

    async def handle_file(self, file_token: str) -> str:
        async with self.lock:
            if file_token not in self.staged_files:
                raise KeyError(f"无效文件 token: {file_token}")
            file_path = self.staged_files.pop(file_token, None)
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            return file_path
