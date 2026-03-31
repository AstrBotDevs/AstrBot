from pathlib import Path

import anyio
import httpx


async def extract_file_moonshotai(file_path: str, api_key: str) -> str:
    """Extract text from a file using Moonshot AI API"""
    """
    Args:
        file_path: The path to the file to extract text from
        api_key: The API key to use to extract text from the file
    Returns:
        The text extracted from the file
    """
    base_url = "https://api.moonshot.cn/v1"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    source_path = Path(file_path)

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        follow_redirects=True,
        timeout=60.0,
    ) as client:
        source_bytes = await anyio.Path(source_path).read_bytes()
        upload_response = await client.post(
            "/files",
            data={"purpose": "file-extract"},
            files={
                "file": (
                    source_path.name,
                    source_bytes,
                    "application/octet-stream",
                )
            },
        )
        upload_response.raise_for_status()
        uploaded_file = upload_response.json()
        file_id = uploaded_file.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise ValueError("Moonshot file upload did not return a valid file id")

        content_response = await client.get(f"/files/{file_id}/content")
        content_response.raise_for_status()
        return content_response.text
