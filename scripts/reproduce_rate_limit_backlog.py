"""Reproduce delayed rate-limit admission without plugins, models, or networking.

Run from any checkout with Python 3.12+. Use --source to compare a saved baseline
RateLimitStage file with the modified file. Only the production class is executed;
its imports/decorator dependencies are replaced with minimal fixtures.
"""

import argparse
import ast
import asyncio
import collections
import datetime
import enum
import hashlib
import json
import random
import time
from pathlib import Path
from types import SimpleNamespace


class Event:
    """Minimal event carrying a synthetic session and a stop flag."""

    unified_msg_origin = "repro:GroupMessage:synthetic"

    def __init__(self, number: int) -> None:
        """Initialize the event.

        Args:
            number: Position in the incoming message burst.
        """
        self.number = number
        self.stopped = False

    def stop_event(self) -> None:
        """Mark this event as discarded."""
        self.stopped = True


class Strategy(enum.Enum):
    """Values consumed by the unchanged production limiter."""

    STALL = "stall"
    DISCARD = "discard"


async def main() -> None:
    """Execute a concurrent burst and print a timestamped JSON result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "astrbot/core/pipeline/rate_limit_check/stage.py",
    )
    parser.add_argument("--strategy", choices=["stall", "discard"], default="stall")
    parser.add_argument("--window", type=float, default=60)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--messages", type=int, default=7)
    parser.add_argument("--probability", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=5)
    parser.add_argument("--max-pending", type=int, default=None)
    args = parser.parse_args()
    if args.window <= 0 or args.count <= 0 or args.messages <= 0:
        parser.error("window, count, and messages must be positive")
    if not 0 <= args.probability <= 1:
        parser.error("probability must be between 0 and 1")

    source = args.source.read_text(encoding="utf-8")
    class_node = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "RateLimitStage"
    )
    tree = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            class_node,
        ],
        type_ignores=[],
    )
    ast.fix_missing_locations(tree)
    namespace = {
        "__name__": "rate_limit_reproduction",
        "asyncio": asyncio,
        "defaultdict": collections.defaultdict,
        "deque": collections.deque,
        "datetime": datetime.datetime,
        "timedelta": datetime.timedelta,
        "logger": SimpleNamespace(info=lambda *args, **kwargs: None),
        "RateLimitStrategy": Strategy,
        "Stage": object,
        "register_stage": lambda cls: cls,
    }
    exec(compile(tree, str(args.source), "exec"), namespace)
    limiter = namespace["RateLimitStage"]()
    limiter.rate_limit_count = args.count
    limiter.rate_limit_time = datetime.timedelta(seconds=args.window)
    limiter.rl_strategy = args.strategy
    if args.max_pending is not None:
        limiter.max_pending = args.max_pending

    started = time.monotonic()
    rng = random.Random(args.seed)
    events = [Event(number) for number in range(1, args.messages + 1)]
    decisions = []

    async def consume(event: Event) -> None:
        """Apply the real limiter before a deterministic mock reply decision.

        Args:
            event: Incoming message event; no real reply will be sent.
        """
        await limiter.process(event)
        row = {
            "message": event.number,
            "seconds": round(time.monotonic() - started, 3),
            "discarded": event.stopped,
        }
        if not event.stopped:
            row["mock_reply"] = rng.random() < args.probability
        decisions.append(row)

    # Match the dispatch pattern: one independent pipeline task per event.
    tasks = [asyncio.create_task(consume(event)) for event in events]
    topic_ended = time.monotonic() - started
    await asyncio.sleep(0.01)
    pending = sum(not task.done() for task in tasks)
    await asyncio.gather(*tasks)
    print(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "strategy": args.strategy,
                "window": args.window,
                "count": args.count,
                "max_pending": getattr(limiter, "max_pending", "unbounded"),
                "seed": args.seed,
                "probability": args.probability,
                "incoming_messages": args.messages,
                "topic_ended_seconds": round(topic_ended, 3),
                "pending_after_burst": pending,
                "decisions": decisions,
                "model_api_calls": 0,
                "platform_sends": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
