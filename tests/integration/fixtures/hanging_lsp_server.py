"""LSP fixture that never answers initialization."""

from __future__ import annotations

import time


def main() -> None:
    time.sleep(5)


if __name__ == "__main__":
    main()
