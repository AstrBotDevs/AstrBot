"""Generate formatted Pydantic v2 models from normalized NapCat JSON Schema."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-path", type=Path)
    parser.add_argument("--output-path", type=Path)
    return parser.parse_args()


def main() -> None:
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("NapCat model generation requires Python 3.14.")
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = (
        args.schema_path
        or repo_root
        / ".tmp"
        / "napcat-schema"
        / "ob11-all-event.normalized.schema.json"
    ).resolve()
    output_path = (
        args.output_path
        or repo_root / ".tmp" / "napcat-schema" / "ob11_event_models.py"
    ).resolve()
    if schema_path == output_path:
        raise SystemExit("SchemaPath and OutputPath must be different.")
    if shutil.which("uv") is None or shutil.which("uvx") is None:
        raise SystemExit("Required commands not found: uv and uvx")
    if not schema_path.is_file():
        raise SystemExit(f"Schema file not found: {schema_path}")
    try:
        json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Schema file is not valid JSON: {schema_path}\n{exc}"
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = output_path.with_name(f".{output_path.name}.tmp.py")
    try:
        subprocess.run(
            [
                "uvx",
                "--python",
                "3.14",
                "--from",
                "datamodel-code-generator",
                "datamodel-codegen",
                "--input",
                str(schema_path),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(temporary_output),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.14",
                "--formatters",
                "builtin",
                "--disable-timestamp",
                "--extra-fields",
                "forbid",
                "--use-schema-description",
                "--field-constraints",
                "--use-generic-base-class",
            ],
            check=True,
            cwd=repo_root,
        )
        if not temporary_output.is_file():
            raise SystemExit(f"Python models file was not created: {temporary_output}")
        subprocess.run(
            ["uv", "run", "ruff", "check", "--fix", str(temporary_output)],
            check=True,
        )
        subprocess.run(
            ["uv", "run", "ruff", "format", str(temporary_output)], check=True
        )
        os.replace(temporary_output, output_path)
    finally:
        temporary_output.unlink(missing_ok=True)
    print(f"Generated Python models:\n  {output_path}")


if __name__ == "__main__":
    main()
