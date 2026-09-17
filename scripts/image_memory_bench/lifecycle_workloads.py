"""Run real history lifecycle workloads in an isolated, measured child process."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil

REQUESTS = 200
SESSIONS = 4
WINDOW_TURNS = 25


def _count_images(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_count_images(item) for item in value.values())
    if isinstance(value, list):
        return sum(_count_images(item) for item in value)
    return int(isinstance(value, str) and value.startswith("data:image/"))


def _image_hashes(value: Any) -> list[str]:
    if isinstance(value, dict):
        if value.get("type") == "image_url" and isinstance(
            value.get("image_url"), dict
        ):
            encoded = value["image_url"].get("url", "").split(",", 1)[-1]
            try:
                return [hashlib.sha256(base64.b64decode(encoded)).hexdigest()]
            except Exception:
                return []
        return [item for child in value.values() for item in _image_hashes(child)]
    if isinstance(value, list):
        return [item for child in value for item in _image_hashes(child)]
    return []


async def _child(args: argparse.Namespace) -> dict[str, Any]:
    """Execute the production database, context, materialization, and SDK path."""
    sys.path.insert(0, str(args.repo.resolve()))
    from openai import AsyncOpenAI

    from astrbot.core.agent.context.config import ContextConfig
    from astrbot.core.agent.context.manager import ContextManager
    from astrbot.core.agent.message import Message
    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.utils.image_media_store import (
        ImageMediaStore,
        materialize_image_media_refs,
    )

    async def load_payload(
        database: SQLiteDatabase, conversation_id: str
    ) -> tuple[list, str, list]:
        conversation = await ConversationManager(database).get_conversation(
            "bench", conversation_id
        )
        messages = [
            Message.model_validate(item) for item in json.loads(conversation.history)
        ]
        selected = await ContextManager(
            ContextConfig(enforce_max_turns=args.window_turns)
        ).process(messages)
        selected = await materialize_image_media_refs(
            selected, ImageMediaStore(args.media_root)
        )
        payload = [message.model_dump() for message in selected]
        semantic_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return payload, semantic_hash, messages

    async def session(
        client: AsyncOpenAI, session_id: str, request_count: int
    ) -> dict[str, Any]:
        database = SQLiteDatabase(str(args.database))
        await database.initialize()
        semantic_hashes: list[str] = []
        image_counts: list[int] = []
        image_hash_orders: list[list[str]] = []
        for turn in range(request_count):
            _, _, messages = await load_payload(database, session_id)
            image_refs = [
                part.model_dump() if hasattr(part, "model_dump") else part
                for message in messages
                for part in (
                    message.content if isinstance(message.content, list) else []
                )
                if (part.model_dump() if hasattr(part, "model_dump") else part).get(
                    "type"
                )
                == "image_media_ref"
            ]
            if not image_refs:
                raise RuntimeError(
                    "lifecycle fixture has no persisted image references"
                )
            messages.extend(
                [
                    Message(role="user", content=[image_refs[turn % len(image_refs)]]),
                    Message(role="assistant", content=f"ack {turn}"),
                ]
            )
            await ConversationManager(database).update_conversation(
                "bench",
                session_id,
                history=[message.model_dump() for message in messages],
            )
            payload, semantic_hash, _ = await load_payload(database, session_id)
            semantic_hashes.append(semantic_hash)
            image_counts.append(_count_images(payload))
            image_hash_orders.append(_image_hashes(payload))
            if not image_hash_orders[-1] or image_counts[-1] > args.window_turns:
                raise RuntimeError("active image window is empty or unbounded")
            await client.chat.completions.create(model="local", messages=payload)
            del payload
        await database.engine.dispose()
        return {
            "session": session_id,
            "requests": request_count,
            "image_counts": image_counts,
            "image_hash_orders": image_hash_orders,
            "semantic_hashes": semantic_hashes,
        }

    if args.restart_check:
        checks = []
        database = SQLiteDatabase(str(args.database))
        await database.initialize()
        for session_id in args.conversation_ids:
            payload, semantic_hash, _ = await load_payload(database, session_id)
            checks.append(
                {
                    "session": session_id,
                    "images": _count_images(payload),
                    "semantic_hash": semantic_hash,
                    "image_hash_order": _image_hashes(payload),
                }
            )
        await database.engine.dispose()
        return {"restart_checks": checks}

    async with AsyncOpenAI(
        api_key="local", base_url=args.endpoint, max_retries=0
    ) as client:
        session_count = len(args.conversation_ids)
        base_requests, remainder = divmod(args.request_count, session_count)
        request_counts = [
            base_requests + (index < remainder) for index in range(session_count)
        ]
        results = await asyncio.gather(
            *(
                session(client, cid, request_count)
                for cid, request_count in zip(args.conversation_ids, request_counts)
            )
        )
    return {
        "sessions": results,
        "total_requests": sum(request_counts),
        "request_count_per_session": request_counts,
        "window_turns": args.window_turns,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument(
        "--conversation-id", dest="conversation_ids", action="append", default=[]
    )
    parser.add_argument("--endpoint")
    parser.add_argument("--rss-jsonl", type=Path)
    parser.add_argument("--restart-check", action="store_true")
    parser.add_argument("--session-count", type=int, choices=(1, 4), default=4)
    parser.add_argument("--request-count", type=int, default=REQUESTS)
    parser.add_argument("--window-turns", type=int, default=WINDOW_TURNS)
    args = parser.parse_args()
    if args.request_count < 1 or args.window_turns < 1:
        parser.error("request count and window turns must be positive")
    if args.child:
        if (
            args.database is None
            or args.media_root is None
            or args.endpoint is None
            or len(args.conversation_ids) != args.session_count
        ):
            parser.error(
                "child requires database, media root, endpoint, and the requested conversation IDs"
            )
        result = asyncio.run(_child(args))
        args.output.write_text(json.dumps(result) + "\n", encoding="utf-8")
        return 0
    if len(args.conversation_ids) != args.session_count:
        parser.error(
            f"exactly {args.session_count} --conversation-id values are required"
        )
    if args.database is None or args.media_root is None:
        parser.error("--database and --media-root are required")

    requests: list[dict[str, Any]] = []

    class Sink(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            size = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(size)
            requests.append(
                {
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "images": _count_images(json.loads(body)),
                }
            )
            response = b'{"choices":[{"message":{"content":"ok"}}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Sink)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="astrbot-lifecycle-") as run_dir:
        child_output = Path(run_dir) / "child.json"
        rss_path = args.rss_jsonl or args.output.with_name(
            args.output.stem + ".rss.jsonl"
        )
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            str(child_output),
            "--child",
            "--repo",
            str(args.repo.resolve()),
            "--database",
            str(args.database.resolve()),
            "--media-root",
            str(args.media_root.resolve()),
            "--endpoint",
            f"http://127.0.0.1:{server.server_port}/v1",
            "--session-count",
            str(args.session_count),
            "--request-count",
            str(args.request_count),
            "--window-turns",
            str(args.window_turns),
        ]
        for conversation_id in args.conversation_ids:
            command.extend(["--conversation-id", conversation_id])
        started = time.monotonic()
        process = subprocess.Popen(command, cwd=args.repo)
        child = psutil.Process(process.pid)
        stop_reason = None
        with rss_path.open("w", encoding="utf-8") as rss:
            while process.poll() is None:
                current = child.memory_info().rss
                private_bytes = None
                try:
                    private_bytes = child.memory_full_info().uss
                except (AttributeError, psutil.AccessDenied):
                    pass
                rss.write(
                    json.dumps(
                        {
                            "seconds": time.monotonic() - started,
                            "rss": current,
                            "private_bytes": private_bytes,
                        }
                    )
                    + "\n"
                )
                rss.flush()
                if (
                    current > min(2 * 1024**3, psutil.virtual_memory().available // 4)
                    or time.monotonic() - started > 120
                ):
                    stop_reason = (
                        "memory_limit"
                        if current
                        > min(2 * 1024**3, psutil.virtual_memory().available // 4)
                        else "timeout"
                    )
                    process.kill()
                    break
                time.sleep(0.01)
        return_code = process.wait()
        server.shutdown()
        result = (
            json.loads(child_output.read_text())
            if child_output.exists()
            else {"error": "child failed"}
        )
        validation_errors = []
        restart_result = {"skipped": stop_reason or "child_failed"}
        if stop_reason is None and return_code == 0:
            restart_output = Path(run_dir) / "restart.json"
            restart_command = command.copy()
            restart_command[2] = str(restart_output)
            restart_command.append("--restart-check")
            restart_process = subprocess.run(
                restart_command, cwd=args.repo, check=False
            )
            restart_result = (
                json.loads(restart_output.read_text())
                if restart_output.exists()
                else {"error": "restart child failed"}
            )
            if restart_result.get("restart_checks"):
                expected = {
                    item["session"]: item for item in result.get("sessions", [])
                }
                for check in restart_result["restart_checks"]:
                    prior = expected.get(check["session"])
                    if (
                        prior is None
                        or check["images"] != prior["image_counts"][-1]
                        or check["image_hash_order"] != prior["image_hash_orders"][-1]
                    ):
                        validation_errors.append(
                            "fresh-process restart changed the active image window"
                        )
            if restart_process.returncode != 0:
                return_code = restart_process.returncode
        result.update(
            {
                "returncode": return_code,
                "stop_reason": stop_reason,
                "request_count": len(requests),
                "expected_request_count": args.request_count,
                "requests": requests,
                "rss_jsonl": str(rss_path),
                "restart": restart_result,
            }
        )
        if any(
            request["images"] <= 0 or request["images"] > args.window_turns
            for request in requests
        ):
            validation_errors.append("sink observed an invalid active image window")
        if len(requests) != args.request_count:
            validation_errors.append("sink did not observe the expected request count")
        if validation_errors:
            result["validation_errors"] = validation_errors
            return_code = return_code or 1
            result["returncode"] = return_code
        args.output.write_text(json.dumps(result) + "\n", encoding="utf-8")
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
