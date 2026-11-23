"""Common path validation and command-line handling for standalone skill scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Protocol


class Renderer(Protocol):
    def __call__(
        self, source: Path, destination: Path, /, *, dpi: int, emit_pdf: bool
    ) -> list[Path]: ...


def parse_input_path(
    parser: argparse.ArgumentParser, *, suffix: str | None = None
) -> tuple[argparse.Namespace, Path]:
    """Parse arguments and validate the requested input file."""
    args = parser.parse_args()
    path = args.input.expanduser().resolve(strict=False)
    if not path.is_file():
        parser.error(f"Input file not found: {path}")
    if suffix is not None and path.suffix.lower() != suffix:
        parser.error(f"Input path must end with {suffix}")
    return args, path


def parse_conversion_paths(
    parser: argparse.ArgumentParser,
) -> tuple[argparse.Namespace, Path, Path]:
    """Resolve input and output paths without writing either file."""
    args, input_path = parse_input_path(parser)
    return args, input_path, args.output.expanduser().resolve(strict=False)


def run_renderer(
    renderer: Renderer,
    *,
    description: str,
    input_help: str,
    input_suffix: str | None = None,
) -> int:
    """Run the shared render CLI with document-specific input validation."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("input", type=Path, help=input_help)
    parser.add_argument("output_dir", type=Path, help="Rendered-page directory")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--emit-pdf", action="store_true")
    args, input_path = parse_input_path(parser, suffix=input_suffix)
    output_dir = args.output_dir.expanduser().resolve(strict=False)
    if args.dpi < 72 or args.dpi > 600:
        parser.error("DPI must be between 72 and 600.")
    try:
        pages = renderer(input_path, output_dir, dpi=args.dpi, emit_pdf=args.emit_pdf)
    except Exception as exc:
        parser.error(str(exc))
    for page in pages:
        print(page)
    return 0
