from astrbot.core.file_token_service import FileTokenService


class FileServiceError(Exception):
    pass


class FileService:
    def __init__(self, file_token_service: FileTokenService) -> None:
        self.file_token_service = file_token_service

    async def resolve_token_file(self, file_token: str) -> str:
        try:
            return await self.file_token_service.handle_file(file_token)
        except (FileNotFoundError, KeyError, OSError) as exc:
            raise FileServiceError("File not found") from exc

    async def claim_token_file(self, file_token: str) -> tuple[str, bool]:
        try:
            return await self.file_token_service.claim_file(file_token)
        except (FileNotFoundError, KeyError, OSError) as exc:
            raise FileServiceError("File not found") from exc
