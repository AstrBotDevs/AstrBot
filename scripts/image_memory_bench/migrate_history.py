"""Explicitly externalize or re-inline exported JSONL conversation histories.

The input is never modified. Inspect the dry run before using --apply. Keep the
input alongside the media directory as the rollback backup.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from astrbot.core.utils.image_media_store import (
    ImageMediaStore,
    materialize_image_media_refs,
    persist_inline_image_refs,
)


async def main() -> int:
    """Transform an export into a new file without modifying live histories."""
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--media-dir", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=["externalize", "inline"], default="externalize"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve() or args.output.exists():
        parser.error("Output must be a new file distinct from the rollback input")
    if args.rollback:
        if not args.apply:
            parser.error("--rollback requires --apply")
        # The input is the verified original export; rollback writes that exact
        # export to a new path, so the original remains the recovery anchor.
        args.mode = "inline"
    store = ImageMediaStore(args.media_dir)
    record_count = 0
    image_count = 0
    output = args.output.open("x", encoding="utf-8") if args.apply else None
    try:
        with args.input.open(encoding="utf-8") as source:
            for line in source:
                record = json.loads(line)
                raw_history = record.get("history", [])
                history = (
                    json.loads(raw_history)
                    if isinstance(raw_history, str)
                    else raw_history
                )
                if not isinstance(history, list):
                    raise ValueError("History must be a message list")
                for message in history:
                    parts = message.get("content")
                    if isinstance(parts, list):
                        image_count += sum(
                            isinstance(part, dict)
                            and part.get("type") in {"image_url", "image_media_ref"}
                            for part in parts
                        )
                if args.apply:
                    if args.mode == "externalize" and not args.rollback:
                        history = persist_inline_image_refs(history, store)
                    else:
                        history = await materialize_image_media_refs(
                            history, store, strict=True
                        )
                    record["history"] = (
                        json.dumps(history, ensure_ascii=False)
                        if isinstance(raw_history, str)
                        else history
                    )
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                record_count += 1
    except BaseException:
        if output is not None:
            output.close()
            args.output.unlink(missing_ok=True)
        raise
    finally:
        if output is not None:
            output.close()
    print(
        json.dumps(
            {"records": record_count, "images": image_count, "applied": args.apply}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
