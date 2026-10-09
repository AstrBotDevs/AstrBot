from __future__ import annotations

from typing import Any

from astrbot_sdk.assets import AssetRef
from astrbot_sdk.errors import InvalidRequest

from astrbot.core import file_token_service

from .assets import AssetStore


class FileTokenService:
    """Stage a Runner-uploaded asset for token-authorized download.

    Legacy plugins call ``file_token_service.register_file(path)`` to expose
    a local file over HTTP. In isolated mode the file bytes first travel to
    the Host asset store; this service registers the staged host-side path
    with the real FileTokenService and returns the token.
    """

    capability_id = "file.token"

    def __init__(self, store: AssetStore) -> None:
        """Initialize the service.

        Args:
            store: Plugin-namespaced asset store holding uploaded bytes.
        """
        self._store = store

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one file.token operation."""
        if operation != "register":
            raise InvalidRequest(f"unknown file.token operation: {operation}")
        asset = payload.get("asset")
        if not isinstance(asset, AssetRef):
            raise InvalidRequest("file.token register requires an asset reference")
        timeout = payload.get("timeout")
        single_use = bool(payload.get("single_use", True))
        path = self._store.resolve(asset)
        token = await file_token_service.register_file(
            str(path),
            timeout=float(timeout) if isinstance(timeout, int | float) else None,
            single_use=single_use,
        )
        return {"token": token}
