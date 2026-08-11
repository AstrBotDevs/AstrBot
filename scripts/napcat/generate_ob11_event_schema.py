"""Generate a JSON Schema for NapCat's OneBot v11 event union."""

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
    parser.add_argument(
        "--napcat-repo-url", default="https://github.com/NapNeko/NapCatQQ"
    )
    parser.add_argument("--clone-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--type-name", default="OB11AllEvent")
    parser.add_argument("--force-clone", action="store_true")
    parser.add_argument("--revision")
    return parser.parse_args()


def run(
    command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> None:
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("NapCat schema generation requires Python 3.14.")
    args = parse_args()
    if not args.type_name.strip():
        raise SystemExit("TypeName must not be empty.")
    pnpm_command = "pnpm.cmd" if os.name == "nt" else "pnpm"
    for command in ("git", pnpm_command):
        if shutil.which(command) is None:
            raise SystemExit(f"Required command not found: {command}")

    repo_root = Path(__file__).resolve().parents[2]
    revision_path = Path(__file__).with_name("napcat-revision.txt")
    revision = (args.revision or revision_path.read_text(encoding="utf-8")).strip()
    if not revision:
        raise SystemExit("NapCat revision must not be empty.")
    clone_dir = (args.clone_dir or repo_root / ".tmp" / "NapCatQQ").resolve()
    output_dir = (args.output_dir or repo_root / ".tmp" / "napcat-schema").resolve()
    if args.force_clone and clone_dir.exists():
        shutil.rmtree(clone_dir)
    if not clone_dir.exists():
        clone_dir.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                args.napcat_repo_url,
                str(clone_dir),
            ]
        )
    else:
        print(f"Reusing NapCat repository at {clone_dir}")

    current_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=clone_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if current_revision != revision:
        run(["git", "fetch", "--depth", "1", "origin", revision], cwd=clone_dir)
        run(["git", "checkout", "--detach", revision], cwd=clone_dir)

    event_file = clone_dir / "packages/napcat-webui-frontend/src/types/onebot/event.ts"
    segment_file = (
        clone_dir / "packages/napcat-webui-frontend/src/types/onebot/segment.ts"
    )
    for path in (event_file, segment_file):
        if not path.is_file():
            raise SystemExit(f"NapCat event type file not found: {path}")

    schema_test_dir = output_dir / "ob11-schema-test"
    schema_test_dir.mkdir(parents=True, exist_ok=True)
    tsconfig_path = schema_test_dir / "tsconfig.json"
    tsconfig_path.write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "target": "ES2020",
                    "module": "ESNext",
                    "moduleResolution": "bundler",
                    "strict": True,
                    "skipLibCheck": True,
                    "allowImportingTsExtensions": True,
                    "resolveJsonModule": True,
                    "isolatedModules": True,
                    "noEmit": True,
                },
                "files": [
                    os.path.relpath(event_file, schema_test_dir).replace("\\", "/"),
                    os.path.relpath(segment_file, schema_test_dir).replace("\\", "/"),
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    schema_path = output_dir / "ob11-all-event.schema.json"
    if schema_path == tsconfig_path:
        raise SystemExit(
            "Schema output path must not collide with the generated tsconfig path."
        )

    environment = os.environ.copy()
    for name, path in {
        "PNPM_HOME": repo_root / ".tmp" / "pnpm-home",
        "PNPM_STORE_DIR": repo_root / ".tmp" / "pnpm-store",
        "XDG_CACHE_HOME": repo_root / ".tmp" / "xdg-cache",
    }.items():
        path.mkdir(parents=True, exist_ok=True)
        environment[name] = str(path)
    run(
        [
            pnpm_command,
            "dlx",
            "typescript-json-schema",
            str(tsconfig_path),
            args.type_name,
            "--noExtraProps",
            "--required",
            "--topRef",
            "--out",
            str(schema_path),
        ],
        env=environment,
    )
    if not schema_path.is_file():
        raise SystemExit(f"Schema file was not created: {schema_path}")
    json.loads(schema_path.read_text(encoding="utf-8"))
    print(f"Generated schema:\n  {schema_path}\nGenerated tsconfig:\n  {tsconfig_path}")


if __name__ == "__main__":
    main()
