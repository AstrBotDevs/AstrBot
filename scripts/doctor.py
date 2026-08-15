"""Check the local development toolchain before running AstrBot commands."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    required: bool = True
    expected_prefix: str | None = None


def version(command: tuple[str, ...], cwd: Path) -> str | None:
    executable = shutil.which(command[0])
    if executable is None:
        return None
    try:
        result = subprocess.run(
            (executable, *command[1:]), cwd=cwd, text=True, capture_output=True
        )
    except OSError:
        return None
    if result.returncode:
        return None
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else "available"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Fail for missing tools.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    required = [
        Check("Python", (sys.executable, "--version"), expected_prefix="Python 3.14."),
        Check("uv", ("uv", "--version")),
        Check("Node.js", ("node", "--version"), expected_prefix="v26."),
    ]
    if sys.platform != "win32":
        required.extend(
            [
                Check("shellcheck", ("shellcheck", "--version")),
                Check("shfmt", ("shfmt", "--version")),
                Check("hadolint", ("hadolint", "--version")),
            ]
        )
    optional = [Check("Docker", ("docker", "--version"), required=False)]
    failures: list[str] = []
    for check in [*required, *optional]:
        value = version(check.command, root)
        valid = value is not None and (
            check.expected_prefix is None or value.startswith(check.expected_prefix)
        )
        status = (
            "ok" if valid else ("missing" if value is None else "unexpected version")
        )
        print(f"{check.name:12} {status:18} {value or ''}")
        if check.required and not valid:
            failures.append(check.name)

    dashboard_pnpm = version(("pnpm", "--version"), root / "dashboard")
    pnpm_ok = dashboard_pnpm is not None and dashboard_pnpm.startswith("11.21.")
    print(
        f"{'pnpm':12} {'ok' if pnpm_ok else 'missing/unexpected':18} {dashboard_pnpm or ''}"
    )
    if not pnpm_ok:
        failures.append("pnpm 11.21")

    if failures:
        print(
            "\nMissing or incompatible tools: " + ", ".join(failures), file=sys.stderr
        )
        print(
            "See docs/en/dev/linux.md or docs/zh/dev/linux.md for installation commands.",
            file=sys.stderr,
        )
        if args.strict:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
