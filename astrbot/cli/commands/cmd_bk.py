import asyncio
import hashlib
import shutil
import subprocess
from pathlib import Path

import anyio
import click

from astrbot.core import db_helper
from astrbot.core.backup import AstrBotExporter, AstrBotImporter


@click.group(name="bk")
def bk():
    """Backup management (Export/Import)"""


@bk.command(name="export")
@click.option("--output", "-o", help="Output directory", default=None)
@click.option(
    "--gpg-sign",
    "-S",
    is_flag=True,
    help="Sign backup with GPG default private key",
)
@click.option(
    "--gpg-encrypt",
    "-E",
    help="Encrypt for GPG recipient (Asymmetric)",
    metavar="RECIPIENT",
)
@click.option(
    "--gpg-symmetric",
    "-C",
    is_flag=True,
    help="Encrypt with symmetric cipher (GPG)",
)
@click.option(
    "--digest",
    "-d",
    type=click.Choice(["md5", "sha1", "sha256", "sha512"]),
    help="Generate digital digest",
)
def export_data(
    output: str | None,
    gpg_sign: bool,
    gpg_encrypt: str | None,
    gpg_symmetric: bool,
    digest: str | None,
):
    """Export all AstrBot data to a backup archive.

    If any GPG option (-S, -E, -C) is used, the output file will be processed by GPG
    and saved with a .gpg extension.
    """
    if gpg_encrypt and gpg_encrypt.startswith("-"):
        consumed_flag = gpg_encrypt
        click.echo(
            click.style(
                f"Warning: Flag '{consumed_flag}' was interpreted as the recipient for -E.",
                fg="yellow",
            ),
        )
        if consumed_flag == "-S":
            gpg_sign = True
            click.echo("Recovered flag -S (Sign).")
        elif consumed_flag == "-C":
            gpg_symmetric = True
            click.echo("Recovered flag -C (Symmetric).")
        gpg_encrypt = click.prompt("Please enter the GPG recipient (email or key ID)")

    async def _run():
        if gpg_sign or gpg_encrypt or gpg_symmetric:
            if not shutil.which("gpg"):
                raise click.ClickException(
                    "GPG tool not found. Please install GnuPG to use encryption/signing features.",
                )

        exporter = AstrBotExporter(db_helper)

        async def on_progress(stage, current, total, message):
            click.echo(f"[{stage}] {message}")

        try:
            path_str = await exporter.export_all(output, progress_callback=on_progress)
            final_path = Path(path_str)
            click.echo(
                click.style(f"\nRaw backup exported to: {final_path}", fg="green"),
            )

            if gpg_sign or gpg_encrypt or gpg_symmetric:
                gpg_output = final_path.with_name(final_path.name + ".gpg")
                cmd = ["gpg", "--output", str(gpg_output), "--yes"]

                if gpg_symmetric:
                    if gpg_encrypt:
                        click.echo(
                            click.style(
                                "Warning: Symmetric encryption selected, ignoring asymmetric recipient.",
                                fg="yellow",
                            ),
                        )
                    cmd.append("--symmetric")
                else:
                    if gpg_encrypt:
                        cmd.extend(["--encrypt", "--recipient", gpg_encrypt])
                    if gpg_sign:
                        cmd.append("--sign")

                cmd.append(str(final_path))
                click.echo(f"Running GPG: {' '.join(cmd)}")

                process = await asyncio.create_subprocess_exec(*cmd)
                await process.wait()

                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode or 1, cmd)

                await anyio.Path(final_path).unlink()
                final_path = gpg_output
                click.echo(
                    click.style(f"Processed backup created: {final_path}", fg="green"),
                )

            if digest:
                click.echo(f"Calculating {digest} digest...")
                hash_func = getattr(hashlib, digest)()
                async with await anyio.open_file(final_path, "rb") as f:
                    while chunk := await f.read(8192):
                        hash_func.update(chunk)

                digest_val = hash_func.hexdigest()
                digest_file = final_path.with_name(final_path.name + f".{digest}")
                await anyio.Path(digest_file).write_text(
                    f"{digest_val} *{final_path.name}\n",
                    encoding="utf-8",
                )
                click.echo(click.style(f"Digest generated: {digest_file}", fg="green"))

        except subprocess.CalledProcessError as e:
            click.echo(click.style(f"\nGPG process failed: {e}", fg="red"), err=True)
        except Exception as e:
            click.echo(click.style(f"\nExport failed: {e}", fg="red"), err=True)

    asyncio.run(_run())


@bk.command(name="import")
@click.argument("backup_file")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def import_data_command(backup_file: str, yes: bool):
    """Import AstrBot data from a backup archive.

    Automatically handles .zip files and .gpg files (signed or encrypted).
    """
    backup_path = Path(backup_file)
    if not backup_path.exists():
        raise click.ClickException(f"Backup file not found: {backup_file}")

    if not yes:
        click.confirm(
            "This will OVERWRITE all current data (DB, Config, Plugins). Continue?",
            abort=True,
            default=False,
        )

    async def _run():
        zip_path = backup_path
        is_temp_file = False

        if backup_path.suffix == ".gpg":
            if not shutil.which("gpg"):
                raise click.ClickException(
                    "GPG tool not found. Cannot decrypt .gpg file.",
                )
            decrypted_path = backup_path.with_suffix("")
            click.echo(f"Processing GPG file {backup_path}...")
            try:
                cmd = [
                    "gpg",
                    "--output",
                    str(decrypted_path),
                    "--decrypt",
                    str(backup_path),
                ]
                process = await asyncio.create_subprocess_exec(*cmd)
                await process.wait()
                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode or 1, cmd)
                zip_path = decrypted_path
                is_temp_file = True
            except subprocess.CalledProcessError:
                click.echo(
                    click.style(
                        "GPG processing failed. Verify signature or decryption key.",
                        fg="red",
                    ),
                    err=True,
                )
                return

        importer = AstrBotImporter(db_helper)

        async def on_progress(stage, current, total, message):
            click.echo(f"[{stage}] {message}")

        try:
            result = await importer.import_all(
                str(zip_path),
                progress_callback=on_progress,
            )
            if result.errors:
                click.echo(
                    click.style("\nImport failed with errors:", fg="red"),
                    err=True,
                )
                for err in result.errors:
                    click.echo(f"  - {err}", err=True)
            else:
                click.echo(click.style("\nImport completed successfully!", fg="green"))
            if result.warnings:
                click.echo(click.style("\nWarnings:", fg="yellow"))
                for warn in result.warnings:
                    click.echo(f"  - {warn}")
        finally:
            if is_temp_file and await anyio.Path(zip_path).exists():
                await anyio.Path(zip_path).unlink()
                click.echo(f"Cleaned up temporary file: {zip_path}")

    asyncio.run(_run())
