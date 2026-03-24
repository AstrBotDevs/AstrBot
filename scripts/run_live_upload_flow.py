import argparse
import asyncio
import logging
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import aiohttp
import websockets


def build_ws_url(base_url: str, api_key: str, username: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.startswith("https://"):
        ws_base = "wss://" + normalized.removeprefix("https://").removeprefix("wss://")
    elif normalized.startswith("http://"):
        ws_base = "ws://" + normalized.removeprefix("http://").removeprefix("wss://")
    else:
        ws_base = f"ws://{normalized}"

    query = urlencode(
        {
            "api_key": api_key,
            "username": username,
            "ct": "live",
        }
    )
    return f"{ws_base}/api/v1/live/ws?{query}"


def build_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def create_logger(log_file: str | None) -> logging.Logger:
    logger = logging.getLogger("live_upload_flow")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


async def upload_file(session: aiohttp.ClientSession, base_url: str, api_key: str, file_path: Path) -> str:
    logger = logging.getLogger("live_upload_flow")
    form = aiohttp.FormData()
    with file_path.open("rb") as file_handle:
        form.add_field(
            "file",
            file_handle,
            filename=file_path.name,
            content_type="application/octet-stream",
        )
        async with session.post(
            f"{base_url.rstrip('/')}/api/v1/file",
            data=form,
            headers=build_headers(api_key),
        ) as resp:
            payload = await resp.json()

    logger.info(
        "[UPLOAD] status=%s, attachment_id=%s",
        payload.get("status"),
        payload.get("data", {}).get("attachment_id"),
    )
    if payload.get("status") != "ok":
        raise RuntimeError(f"Upload failed: {payload}")
    attachment_id = payload["data"]["attachment_id"]
    logger.info("[UPLOAD] attachment_id=%s", attachment_id)
    return attachment_id


async def get_file(session: aiohttp.ClientSession, base_url: str, api_key: str, attachment_id: str) -> bytes:
    logger = logging.getLogger("live_upload_flow")
    url = f"{base_url.rstrip('/')}/api/v1/file?{urlencode({'attachment_id': attachment_id})}"
    async with session.get(url, headers=build_headers(api_key)) as resp:
        logger.info("[GET] status=%s, content_type=%s", resp.status, resp.headers.get("Content-Type"))
        if resp.status != 200:
            text = await resp.text()
            raise RuntimeError(f"Failed to fetch attachment: {resp.status} {text}")
        return await resp.read()


async def run_live_check(base_url: str, api_key: str, username: str, attachment_id: str, text: str) -> None:
    logger = logging.getLogger("live_upload_flow")
    ws_url = build_ws_url(base_url, api_key, username)
    message = {
        "t": "text_input",
        "message": [
            {"type": "file", "attachment_id": attachment_id},
            {"type": "plain", "text": text},
        ],
    }

    async with websockets.connect(ws_url) as websocket:
        logger.info("[WS] connected: %s", ws_url)
        logger.info("[WS] send: %s", json.dumps(message, ensure_ascii=False))
        await websocket.send(json.dumps(message))

        try:
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=90)
                data = json.loads(raw)
                logger.info("[WS] recv: %s", json.dumps(data, ensure_ascii=False))
                if data.get("t") == "end":
                    break
        except asyncio.TimeoutError:
            logger.warning("[WS] timeout reached, stop collecting messages")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Upload file and test live mode input path.")
    parser.add_argument("--base-url", default="http://localhost:6185", help="Server base URL")
    parser.add_argument("--api-key", required=True, help="OpenAPI key")
    parser.add_argument("--username", default="alice", help="OpenAPI username")
    parser.add_argument("--file", required=True, type=Path, help="Local file to upload")
    parser.add_argument(
        "--text",
        default="Please analyze the uploaded file.",
        help="Additional text for live message",
    )
    parser.add_argument(
        "--log-file",
        help="Write logs to this file in addition to terminal output",
    )
    parser.add_argument(
        "--skip-download-check",
        action="store_true",
        help="Skip GET attachment content verification",
    )

    args = parser.parse_args()

    create_logger(args.log_file)
    logger = logging.getLogger("live_upload_flow")

    if not args.file.exists():
        raise FileNotFoundError(f"file not found: {args.file}")
    if not args.file.is_file():
        raise ValueError(f"not a regular file: {args.file}")

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        attachment_id = await upload_file(session, args.base_url, args.api_key, args.file)
        if not args.skip_download_check:
            content = await get_file(session, args.base_url, args.api_key, attachment_id)
            logger.info("[GET] attachment size=%s bytes", len(content))

    await run_live_check(
        args.base_url,
        args.api_key,
        args.username,
        attachment_id,
        args.text,
    )


if __name__ == "__main__":
    create_logger(None)
    try:
        asyncio.run(main())
    except Exception as e:
        logging.getLogger("live_upload_flow").error("error: %s", e, exc_info=True)
        raise SystemExit(1)
