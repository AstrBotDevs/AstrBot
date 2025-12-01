from pathlib import Path

from openai import AsyncOpenAI


async def extract_file_moonshotai(file_path: str, api_key: str) -> str:
    """Extract text from a file using Moonshot AI API"""
    """
    Args:
        file_path: The path to the file to extract text from
        api_key: The API key to use to extract text from the file
    Returns:
        The text extracted from the file
    """
    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.moonshot.cn/v1",
    )
    file_object = await client.files.create(
        file=Path(file_path),
        purpose="file-extract",  # type: ignore
    )
    return (await client.files.content(file_id=file_object.id)).text
