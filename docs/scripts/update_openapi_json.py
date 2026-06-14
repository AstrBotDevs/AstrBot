#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPEC = REPO_ROOT / "openspec" / "openapi-v1.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "public" / "openapi.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update the public OpenAPI JSON document from the v1 YAML spec."
    )
    parser.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC,
        help=f"OpenAPI YAML source path. Default: {DEFAULT_SPEC}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"OpenAPI JSON output path. Default: {DEFAULT_OUTPUT}",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected OpenAPI object in {path}")
    return data


def main() -> int:
    args = parse_args()
    spec_path = args.spec.resolve()
    output_path = args.output.resolve()

    spec = load_yaml(spec_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Updated {output_path.relative_to(REPO_ROOT)} from {spec_path.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
