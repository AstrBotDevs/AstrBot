from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Any

from aiohttp import ClientSession, ClientTimeout, WSMsgType

TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
API_BASE = "https://api.sgroup.qq.com"
DEFAULT_INTENTS = 1107300352  # public_messages + public_guild_messages + direct_message


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed command-line arguments.
    """

    parser = argparse.ArgumentParser(
        description="Capture raw QQ Official Bot WebSocket gateway events."
    )
    parser.add_argument(
        "--appid",
        default=os.getenv("QQ_BOT_APPID") or os.getenv("QQOFFICIAL_APPID"),
        help="QQ bot appid. Defaults to QQ_BOT_APPID or QQOFFICIAL_APPID.",
    )
    parser.add_argument(
        "--secret",
        default=os.getenv("QQ_BOT_SECRET") or os.getenv("QQOFFICIAL_SECRET"),
        help="QQ bot secret. Defaults to QQ_BOT_SECRET or QQOFFICIAL_SECRET.",
    )
    parser.add_argument(
        "--intents",
        type=int,
        default=int(os.getenv("QQ_BOT_INTENTS", str(DEFAULT_INTENTS))),
        help=(
            "Gateway intents integer. Default enables public_messages, "
            "public_guild_messages and direct_message."
        ),
    )
    parser.add_argument(
        "--output",
        default="qqofficial_ws_events.jsonl",
        help="Path to write raw received gateway packets as JSON Lines.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Seconds to run. 0 means run until Ctrl+C.",
    )
    return parser.parse_args()


async def fetch_access_token(session: ClientSession, appid: str, secret: str) -> str:
    """Fetch QQ bot app access token.

    Args:
        session: Shared aiohttp client session.
        appid: QQ bot appid.
        secret: QQ bot secret.

    Returns:
        Access token string.

    Raises:
        RuntimeError: If the token API does not return an access token.
    """

    async with session.post(
        TOKEN_URL,
        json={"appId": appid, "clientSecret": secret},
    ) as response:
        data = await response.json(content_type=None)

    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError(f"Failed to fetch access token: {data}")
    return str(access_token)


async def fetch_gateway(session: ClientSession, appid: str, access_token: str) -> dict:
    """Fetch QQ bot gateway metadata.

    Args:
        session: Shared aiohttp client session.
        appid: QQ bot appid.
        access_token: App access token.

    Returns:
        Gateway metadata returned by QQ official API.

    Raises:
        RuntimeError: If the gateway API response has no URL.
    """

    headers = {
        "Authorization": f"QQBot {access_token}",
        "X-Union-Appid": appid,
    }
    async with session.get(f"{API_BASE}/gateway/bot", headers=headers) as response:
        data = await response.json(content_type=None)

    if not data.get("url"):
        raise RuntimeError(f"Failed to fetch gateway URL: {data}")
    return dict(data)


async def heartbeat_loop(ws, interval: float, last_seq: dict[str, int | None]) -> None:
    """Send QQ gateway heartbeat packets until the websocket closes.

    Args:
        ws: Active aiohttp websocket connection.
        interval: Heartbeat interval in seconds.
        last_seq: Mutable holder containing the last gateway sequence number.
    """

    while not ws.closed:
        await ws.send_json({"op": 1, "d": last_seq.get("value")})
        await asyncio.sleep(interval)


async def capture_events(args: argparse.Namespace) -> None:
    """Connect to QQ gateway and capture raw websocket packets.

    Args:
        args: Parsed command-line arguments.

    Raises:
        ValueError: If appid or secret is missing.
    """

    if not args.appid or not args.secret:
        raise ValueError(
            "appid and secret are required via args or environment variables."
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    timeout = ClientTimeout(total=30)
    async with ClientSession(timeout=timeout) as session:
        access_token = await fetch_access_token(session, args.appid, args.secret)
        gateway = await fetch_gateway(session, args.appid, access_token)
        gateway_url = str(gateway["url"])
        shard_count = int(gateway.get("shards") or 1)
        print(f"gateway: {gateway_url}")
        print(f"session_start_limit: {gateway.get('session_start_limit')}")
        print(f"intents: {args.intents}")
        print(f"output: {output_path}")

        async with session.ws_connect(gateway_url) as ws:
            last_seq: dict[str, int | None] = {"value": None}
            heartbeat_task: asyncio.Task | None = None
            started_at = time.monotonic()

            with output_path.open("a", encoding="utf-8") as fp:
                while not ws.closed:
                    if (
                        args.duration > 0
                        and time.monotonic() - started_at >= args.duration
                    ):
                        break
                    if stop_event.is_set():
                        break

                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=1)
                    except TimeoutError:
                        continue

                    if msg.type == WSMsgType.TEXT:
                        packet: dict[str, Any] = json.loads(msg.data)
                        fp.write(json.dumps(packet, ensure_ascii=False) + "\n")
                        fp.flush()

                        op = packet.get("op")
                        seq = packet.get("s")
                        event_name = packet.get("t")
                        if isinstance(seq, int):
                            last_seq["value"] = seq

                        print(
                            json.dumps(
                                {
                                    "op": op,
                                    "s": seq,
                                    "t": event_name,
                                    "d_keys": sorted(packet.get("d", {}).keys())
                                    if isinstance(packet.get("d"), dict)
                                    else None,
                                },
                                ensure_ascii=False,
                            )
                        )

                        if op == 10:
                            heartbeat_interval = (
                                packet.get("d", {}).get("heartbeat_interval", 30000)
                                if isinstance(packet.get("d"), dict)
                                else 30000
                            )
                            interval = max(float(heartbeat_interval) / 1000, 1)
                            identify_payload = {
                                "op": 2,
                                "d": {
                                    "token": f"QQBot {access_token}",
                                    "intents": args.intents,
                                    "shard": [0, shard_count],
                                },
                            }
                            await ws.send_json(identify_payload)
                            print("sent IDENTIFY")
                            if heartbeat_task is None:
                                heartbeat_task = asyncio.create_task(
                                    heartbeat_loop(ws, interval, last_seq)
                                )
                        elif op == 7:
                            print("gateway requested reconnect; stop capture")
                            break
                        elif op == 9:
                            print("invalid session; stop capture")
                            break
                    elif msg.type in (
                        WSMsgType.CLOSED,
                        WSMsgType.CLOSE,
                        WSMsgType.ERROR,
                    ):
                        break

            if heartbeat_task:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)


def main() -> None:
    """Run the QQ official websocket capture script."""

    asyncio.run(capture_events(parse_args()))


if __name__ == "__main__":
    main()
