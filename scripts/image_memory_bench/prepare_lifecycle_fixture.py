"""Prepare a durable multi-session history fixture before measurement."""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path


async def prepare_fixture(
    manifest_path: Path,
    output: Path,
    session_count: int,
    history_turns: int,
    include_stress: bool,
) -> dict:
    """Create shared media and persisted conversations outside the measured child.

    Args:
        manifest_path: Fixture manifest containing valid prepared image paths.
        output: Fresh directory receiving the SQLite database and media objects.
        session_count: Number of conversations to create.
        history_turns: Number of image-bearing turns per conversation.
        include_stress: Whether to include high-entropy stress fixtures.

    Returns:
        A JSON-compatible manifest consumed by ``lifecycle_workloads.py``.

    Raises:
        FileExistsError: The output already contains a database.
        ValueError: The input manifest or requested sizes are invalid.
    """
    if session_count < 1 or history_turns < 1:
        raise ValueError("session count and history turns must be positive")
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("fixture manifest must contain at least one image")
    if not include_stress:
        rows = [row for row in rows if not row.get("stress")]
    if not rows:
        raise ValueError("fixture manifest must contain at least one image")
    output.mkdir(parents=True, exist_ok=True)
    database_path = output / "history.db"
    if database_path.exists():
        raise FileExistsError(f"refusing to overwrite {database_path}")

    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.utils.image_media_store import ImageMediaStore

    media_root = output / "media"
    store = ImageMediaStore(media_root)
    refs = []
    for row in rows:
        path = manifest_path.parent / row["path"]
        refs.append(store.put(path.read_bytes(), detail="high"))

    history = []
    for turn in range(history_turns):
        history.extend(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"fixture turn {turn}"},
                        refs[turn % len(refs)].model_dump(),
                    ],
                },
                {"role": "assistant", "content": f"ack {turn}"},
            ]
        )

    database = SQLiteDatabase(str(database_path))
    await database.initialize()
    conversation_ids = []
    for index in range(session_count):
        conversation = await database.create_conversation(
            user_id="bench",
            platform_id="bench",
            content=deepcopy(history),
            title=f"lifecycle fixture {index}",
        )
        conversation_ids.append(conversation.conversation_id)
    await database.engine.dispose()
    return {
        "database": str(database_path.resolve()),
        "media_root": str(media_root.resolve()),
        "conversation_ids": conversation_ids,
        "session_count": session_count,
        "history_turns": history_turns,
        "media_count": len(refs),
    }


async def main_async(args: argparse.Namespace) -> int:
    """Prepare the fixture and write its machine-readable manifest."""
    result = await prepare_fixture(
        args.manifest,
        args.output,
        args.session_count,
        args.history_turns,
        args.include_stress,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    output_manifest = args.output / "lifecycle-manifest.json"
    output_manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


def main() -> int:
    """Parse fixture preparation arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--session-count", type=int, default=4)
    parser.add_argument("--history-turns", type=int, default=50)
    parser.add_argument(
        "--include-stress",
        action="store_true",
        help="Include high-entropy stress fixtures in the long-running workload.",
    )
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
