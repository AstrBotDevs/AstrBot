"""Record the exact code and dependency baseline for image experiments."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Write a reproducibility manifest without reading application data."""
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    packages = sorted(
        f"{dist.metadata['Name']}=={dist.version}"
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    )
    manifest = {
        "commit": commit,
        "working_tree_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "--binary"], cwd=Path.cwd())
        ).hexdigest(),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
    }
    if args.fixtures:
        files = []
        for path in sorted(args.fixtures.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                files.append(
                    {
                        "path": str(path.relative_to(args.fixtures)),
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        manifest["fixtures"] = files
    args.output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"commit": commit, "package_count": len(packages)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
