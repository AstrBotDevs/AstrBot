#!/usr/bin/env python3

from __future__ import annotations

import argparse

if __package__:
    from .release_constants_loader import load_release_constant
else:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.release.release_constants_loader import load_release_constant


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print a release constant from astrbot/core/release_constants.py.",
    )
    parser.add_argument("name", help="Constant name, e.g. NIGHTLY_TAG.")
    args = parser.parse_args()
    print(load_release_constant(args.name))


if __name__ == "__main__":
    main()
