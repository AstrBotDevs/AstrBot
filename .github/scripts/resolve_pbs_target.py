#!/usr/bin/env python3
"""Resolve python-build-standalone target by platform and architecture."""

from __future__ import annotations

import argparse

TARGETS = {
    ("linux", "amd64"): "x86_64-unknown-linux-gnu",
    ("linux", "arm64"): "aarch64-unknown-linux-gnu",
    ("mac", "amd64"): "x86_64-apple-darwin",
    ("mac", "arm64"): "aarch64-apple-darwin",
    ("windows", "amd64"): "x86_64-pc-windows-msvc",
    ("windows", "arm64"): "aarch64-pc-windows-msvc",
}


def resolve_target(platform: str, arch: str) -> str:
    key = (platform.strip().lower(), arch.strip().lower())
    target = TARGETS.get(key)
    if not target:
        supported = ", ".join(
            f"{item_platform}/{item_arch}" for item_platform, item_arch in TARGETS
        )
        raise RuntimeError(
            f"Unsupported python-build-standalone mapping for {platform}/{arch}. "
            f"Supported: {supported}"
        )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, help="linux/mac/windows")
    parser.add_argument("--arch", required=True, help="amd64/arm64")
    args = parser.parse_args()

    print(resolve_target(args.platform, args.arch))


if __name__ == "__main__":
    main()
