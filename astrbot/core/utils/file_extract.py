from pathlib import Path

from astrbot.core.utils.network_utils import create_proxy_client


async def extract_file_moonshotai(file_path: str, api_key: str) -> str:
    """Extract text from a file using Moonshot AI API.

    Args:
        file_path: Path to the local file to extract text from.
        api_key: Moonshot AI API key.

    Returns:
        Extracted text content from the file.
    """
    path = Path(file_path)
    async with create_proxy_client(
        "Moonshot",
        headers={"Authorization": f"Bearer {api_key}"},
    ) as client:
        with path.open("rb") as file_handle:
            upload_resp = await client.post(
                "https://api.moonshot.cn/v1/files",
                data={"purpose": "file-extract"},
                files={"file": (path.name, file_handle)},
                timeout=60.0,
            )
        upload_resp.raise_for_status()
        file_id = upload_resp.json()["id"]

        content_resp = await client.get(
            f"https://api.moonshot.cn/v1/files/{file_id}/content",
            timeout=60.0,
        )
        content_resp.raise_for_status()
        return content_resp.text
