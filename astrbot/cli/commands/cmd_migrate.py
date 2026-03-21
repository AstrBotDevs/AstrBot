from __future__ import annotations

from pathlib import Path

import click

from ..utils import get_astrbot_root
from ..utils.openclaw_migrate import run_openclaw_migration


@click.group(name="migrate")
def migrate() -> None:
    """Data migration utilities for external runtimes."""


@migrate.command(name="openclaw")
@click.option(
    "--source",
    "source_path",
    type=click.Path(path_type=Path, file_okay=False, resolve_path=True),
    default=None,
    help="Path to OpenClaw root directory (default: ~/.openclaw).",
)
@click.option(
    "--target",
    "target_path",
    type=click.Path(path_type=Path, file_okay=False, resolve_path=False),
    default=None,
    help=(
        "Custom output directory. If omitted, writes to "
        "data/migrations/openclaw/run-<timestamp>."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview migration candidates without writing files.",
)
def migrate_openclaw(
    source_path: Path | None,
    target_path: Path | None,
    dry_run: bool,
) -> None:
    """Migrate OpenClaw workspace snapshots into AstrBot migration artifacts."""

    astrbot_root = get_astrbot_root()
    source_root = source_path or (Path.home() / ".openclaw")

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=dry_run,
        target_dir=target_path,
    )

    click.echo("OpenClaw migration report:")
    click.echo(f"  Source root:        {report.source_root}")
    click.echo(f"  Source workspace:   {report.source_workspace}")
    click.echo(f"  Dry run:            {report.dry_run}")
    click.echo(f"  Memory entries:     {report.memory_entries_total}")
    click.echo(f"    - sqlite:         {report.memory_entries_from_sqlite}")
    click.echo(f"    - markdown:       {report.memory_entries_from_markdown}")
    click.echo(f"  Workspace files:    {report.workspace_files_total}")
    click.echo(f"  Workspace size:     {report.workspace_bytes_total} bytes")
    click.echo(f"  Config found:       {report.config_found}")

    if dry_run:
        click.echo("")
        click.echo("Dry-run mode: no files were written.")
        click.echo("Run without --dry-run to perform migration.")
        return

    click.echo("")
    click.echo(f"Migration output:     {report.target_dir}")
    click.echo(f"  Copied files:       {report.copied_workspace_files}")
    click.echo(f"  Imported memories:  {report.copied_memory_entries}")
    click.echo(f"  Timeline written:   {report.wrote_timeline}")
    click.echo(f"  Config TOML written: {report.wrote_config_toml}")
    click.echo("Done.")


__all__ = ["migrate"]
