#!/usr/bin/env python3
"""Inspect or migrate one legacy conversation while AstrBot is stopped."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Validate the maintenance target before loading AstrBot services.

    Args:
        argv: Optional command-line arguments for tests or embedding.

    Returns:
        Zero on success, two for rejected input, or one for a failed operation.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.environ.get("ASTRBOT_ROOT", Path.cwd())),
        help="AstrBot root containing the existing data directory.",
    )
    parser.add_argument(
        "--conversation", help="Conversation ID selected for maintenance."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List up to 100 oversized conversations without reading their bodies.",
    )
    parser.add_argument(
        "--stopped",
        action="store_true",
        help="Confirm all AstrBot processes using this data root have been stopped.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the prepared migration; omission performs preflight only.",
    )
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()
    database = root / "data" / "data_v4.db"
    if not database.is_file():
        parser.error(
            "The selected root does not contain data/data_v4.db; no database was created."
        )
    if args.list:
        if args.apply or args.conversation:
            parser.error("--list cannot be combined with --apply or --conversation.")
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT conversation_id, substr(title, 1, 80), "
                "length(CAST(content AS BLOB)) FROM conversations "
                "WHERE length(CAST(content AS BLOB)) > ? "
                "ORDER BY inner_conversation_id LIMIT 100",
                (16 * 1024 * 1024,),
            )
            print(
                json.dumps(
                    [
                        {"conversation_id": cid, "title": title, "history_bytes": size}
                        for cid, title, size in rows
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0
    if not args.conversation:
        parser.error("--conversation is required unless --list is used.")
    if not args.stopped:
        parser.error(
            "Stop AstrBot first, then pass --stopped. This flag does not stop running processes."
        )
    if not hasattr(sqlite3.Connection, "blobopen"):
        parser.error(
            "Incremental SQLite reading is unavailable; use the project's supported Python 3.12+ runtime."
        )

    # Core imports create root-specific services, so select the root first.
    os.environ["ASTRBOT_ROOT"] = str(root)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from astrbot.core.db.sqlite import SQLiteDatabase
    from astrbot.core.image_asset_store import (
        ImageAssetImportConflictError,
        ImageStorageLimitError,
        ImageValidationError,
    )
    from astrbot.core.image_history_maintenance import (
        ImageHistoryMaintenanceError,
        run_image_history_maintenance,
    )
    from astrbot.core.image_history_maintenance_storage import ConversationSourceError
    from astrbot.core.image_history_migration import ImageHistoryMigrationError
    from astrbot.core.image_history_stream import StreamHistoryError

    async def run() -> dict:
        db = SQLiteDatabase(str(database))
        try:
            await db.initialize()
            db.inited = True
            return await run_image_history_maintenance(
                db, args.conversation, apply=args.apply
            )
        finally:
            await db.engine.dispose()

    try:
        result = asyncio.run(run())
    except KeyboardInterrupt:
        print(
            "Maintenance interrupted. Rerun the same command to verify or resume the task.",
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        # Do not echo SQL parameters, legacy image URLs, or history content.
        if isinstance(exc, ImageHistoryMigrationError):
            print(f"Maintenance stopped: legacy image {exc.reason}.", file=sys.stderr)
        elif isinstance(
            exc,
            (
                ImageHistoryMaintenanceError,
                ConversationSourceError,
                StreamHistoryError,
                ImageAssetImportConflictError,
                ImageStorageLimitError,
                ImageValidationError,
            ),
        ):
            print(f"Maintenance stopped: {exc}", file=sys.stderr)
        else:
            print(f"Maintenance stopped ({type(exc).__name__}).", file=sys.stderr)
        print(
            "No successful result was reported; rerun the same command to verify the task state.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
