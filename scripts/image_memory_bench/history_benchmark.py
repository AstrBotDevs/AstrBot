"""Measure SQLite history loading and real SDK request bodies for B-only."""

# The compact benchmark runner keeps subprocess orchestration visibly linear.
# ruff: noqa: E701, E702

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil


async def prepare_database(
    db_path: Path, media_root: Path, fixture: Path, images: int, distinct: bool
) -> None:
    """Create one SQLite input outside the measured child."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.utils.image_media_store import (
        ImageMediaStore,
        persist_inline_image_refs,
    )

    rows = json.loads(fixture.read_text())
    paths = [fixture.parent / row["path"] for row in rows]
    history = []
    raw = []
    for index in range(images):
        path = paths[index % len(paths)]
        # Distinct workloads use separately generated, valid image files listed
        # by the fixture manifest. Never mutate encoded bytes into invalid images.
        data = path.read_bytes()
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        raw.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(data).decode()}",
                    "detail": "high",
                },
            }
        )
    for index, part in enumerate(raw):
        history.extend(
            [
                {"role": "user", "content": [part]},
                {"role": "assistant", "content": f"ack {index}"},
            ]
        )
    history.extend(
        [
            {"role": "user", "content": "final text"},
            {"role": "assistant", "content": "final response"},
        ]
    )
    if media_root.name == "reference":
        history = persist_inline_image_refs(history, ImageMediaStore(media_root))
    db = SQLiteDatabase(str(db_path))
    await db.initialize()
    record = await db.create_conversation(
        user_id="bench", platform_id="bench", content=history, title="benchmark"
    )
    (db_path.parent / "conversation-id").write_text(record.conversation_id)
    await db.engine.dispose()


def count_images(value: object) -> int:
    """Count data image URLs in a decoded SDK body."""
    if isinstance(value, dict):
        return sum(count_images(item) for item in value.values())
    if isinstance(value, list):
        return sum(count_images(item) for item in value)
    return int(isinstance(value, str) and value.startswith("data:image/"))


async def run_child(args: argparse.Namespace) -> dict:
    """Read through SQLite and ConversationManager before selecting context."""
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

    phases = {}

    def mark(phase: str) -> None:
        with args.marker.open("a", encoding="utf-8") as marker:
            marker.write(
                json.dumps({"phase": phase, "monotonic": time.monotonic()}) + "\n"
            )

    mark("start")
    started = time.perf_counter()
    db = SQLiteDatabase(str(args.database))
    await db.initialize()
    conversation = await ConversationManager(db).get_conversation(
        "bench", args.conversation_id
    )
    phases["db_and_convert_ms"] = (time.perf_counter() - started) * 1000
    mark("db_and_convert")
    started = time.perf_counter()
    history = json.loads(conversation.history)
    messages = [Message.model_validate(item) for item in history]
    phases["json_load_bind_ms"] = (time.perf_counter() - started) * 1000
    mark("json_load_bind")
    started = time.perf_counter()
    selected = await ContextManager(
        ContextConfig(enforce_max_turns=args.keep_turns)
    ).process(messages)
    phases["selection_ms"] = (time.perf_counter() - started) * 1000
    mark("materialize")
    mark("selection")
    selected = await materialize_image_media_refs(
        selected, ImageMediaStore(args.media_root)
    )
    payload = [message.model_dump() for message in selected]
    mark("sdk")
    async with AsyncOpenAI(
        api_key="local", base_url=args.endpoint, max_retries=0
    ) as client:
        for _ in range(args.warmup):
            await client.chat.completions.create(model="local", messages=payload)
        await client.chat.completions.create(model="local", messages=payload)
    await db.engine.dispose()
    return {
        "phases_ms": phases,
        "selected_messages": len(payload),
        "selected_images": count_images(payload),
    }


def main() -> int:
    """Prepare paired databases and monitor fresh children."""
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument("--images", type=int, default=50)
    parser.add_argument("--keep-turns", type=int, default=25)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--cold-repeats", type=int, default=10)
    parser.add_argument("--warm-repeats", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--distinct", action="store_true")
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--endpoint")
    parser.add_argument("--body-file", type=Path)
    parser.add_argument("--marker", type=Path)
    args = parser.parse_args()
    fixture_rows = json.loads(args.fixture.read_text())
    max_fixture_bytes = max((row.get("bytes", 0) for row in fixture_rows), default=0)
    budget_class = (
        "over-4MiB-source-stress"
        if 4 * ((max_fixture_bytes + 2) // 3) > 4 * 1024 * 1024
        else "representative-within-4MiB-source"
    )
    if args.child:
        result = asyncio.run(run_child(args))
        metadata = json.loads(args.body_file.read_text())
        result.update(
            {
                "http_json_bytes": metadata["bytes"],
                "http_body_sha256": metadata["sha256"],
                "http_images": metadata["images"],
            }
        )
        if not result["selected_images"] or not result["http_images"]:
            raise RuntimeError("actual SDK body contains no images")
        args.output.write_text(json.dumps(result) + "\n")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    csv_file = args.csv.open("w", newline="", encoding="utf-8") if args.csv else None
    writer = None
    received_body = {"path": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(data)
            Path(received_body["path"]).write_text(
                json.dumps(
                    {
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "images": count_images(body),
                    }
                )
            )
            response = b'{"choices":[{"message":{"content":"ok"}}]}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v1"
    try:
        for mode in ("inline", "reference"):
            for repeat in range(args.cold_repeats + args.warm_repeats):
                with tempfile.TemporaryDirectory(
                    prefix="astrbot-history-input-"
                ) as temp:
                    root = Path(temp)
                    db_path = root / f"{mode}.db"
                    media = root / mode
                    asyncio.run(
                        prepare_database(
                            db_path, media, args.fixture, args.images, args.distinct
                        )
                    )
                    conversation_id = (db_path.parent / "conversation-id").read_text()
                    child_output = root / "child.jsonl"
                    body_file = root / "http-metadata.json"
                    received_body["path"] = body_file
                    warmup = 0 if repeat < args.cold_repeats else args.warmup
                    command = [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        str(args.fixture),
                        str(child_output),
                        "--child",
                        "--repo",
                        str(args.repo),
                        "--database",
                        str(db_path),
                        "--media-root",
                        str(media),
                        "--conversation-id",
                        conversation_id,
                        "--keep-turns",
                        str(args.keep_turns),
                        "--warmup",
                        str(warmup),
                        "--endpoint",
                        endpoint,
                        "--body-file",
                        str(body_file),
                        "--marker",
                        str(root / "marker.jsonl"),
                    ]
                    proc = subprocess.Popen(
                        command,
                        cwd=args.repo,
                        env={**os.environ, "ASTRBOT_ROOT": str(root)},
                    )
                    monitor = psutil.Process(proc.pid)
                    samples = []
                    started = time.monotonic()
                    limit = min(2 * 1024**3, psutil.virtual_memory().available // 4)
                    stop_reason = None
                    while proc.poll() is None:
                        try:
                            now = time.monotonic()
                            rss = monitor.memory_info().rss
                            samples.append({"seconds": now, "rss": rss})
                            if now - started > 120:
                                stop_reason = "timeout"
                            elif rss > limit:
                                stop_reason = "memory_limit"
                            if stop_reason:
                                proc.kill()
                                break
                        except psutil.NoSuchProcess:
                            break
                        time.sleep(0.01)
                    proc.wait()
                    if child_output.exists():
                        result = json.loads(child_output.read_text())
                    else:
                        result = {
                            "status": "error",
                            "error": stop_reason or "child_failed",
                        }
                    markers = [
                        json.loads(line)
                        for line in (root / "marker.jsonl").read_text().splitlines()
                    ]
                    for sample in samples:
                        eligible = [
                            marker
                            for marker in markers
                            if marker["monotonic"] <= sample["seconds"]
                        ]
                        sample["phase"] = (
                            max(eligible, key=lambda marker: marker["monotonic"])[
                                "phase"
                            ]
                            if eligible
                            else "pre-start"
                        )
                    result.update(
                        {
                            "mode": mode,
                            "repeat": repeat,
                            "cold": warmup == 0,
                            "workload": f"sqlite-history-{args.images}-{'distinct' if args.distinct else 'same'}",
                            "budget_class": budget_class,
                            "rss_high_water_bytes": max(
                                (sample["rss"] for sample in samples), default=None
                            ),
                            "stop_reason": stop_reason,
                            "rss_samples": samples,
                        }
                    )
                    with args.output.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps(result) + "\n")
                    if csv_file:
                        fields = [
                            "mode",
                            "repeat",
                            "cold",
                            "workload",
                            "rss_high_water_bytes",
                            "http_json_bytes",
                            "http_body_sha256",
                            "http_images",
                        ]
                        if writer is None:
                            writer = csv.DictWriter(csv_file, fieldnames=fields)
                            writer.writeheader()
                        writer.writerow({field: result.get(field) for field in fields})
    finally:
        server.shutdown()
        if csv_file:
            csv_file.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
