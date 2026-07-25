from __future__ import annotations

from astrbot.core import file_token_service


class FileServiceError(Exception):
    pass


class FileService:
    async def resolve_token_file(self, file_token: str) -> str:
        try:
            return await file_token_service.handle_file(file_token)
        except (FileNotFoundError, KeyError) as exc:
            raise FileServiceError(str(exc)) from exc
