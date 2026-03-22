import asyncio
import hashlib
import shutil
import subprocess
from pathlib import Path

import anyio
import click

from astrbot.core import db_helper
from astrbot.core.backup import AstrBotExporter, AstrBotImporter


async def _get_kb_manager():
    """Initialize and return a KnowledgeBaseManager with full dependency chain."""
    from astrbot.core import astrbot_config, sp
    from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.persona_mgr import PersonaManager
    from astrbot.core.provider.manager import ProviderManager
    from astrbot.core.umop_config_router import UmopConfigRouter

    ucr = UmopConfigRouter(sp=sp)
    await ucr.initialize()

    acm = AstrBotConfigManager(
        default_config=astrbot_config,
        ucr=ucr,
        sp=sp,
    )

    persona_mgr = PersonaManager(db_helper, acm)
    await persona_mgr.initialize()

    provider_manager = ProviderManager(
        acm,
        db_helper,
        persona_mgr,
    )

    kb_manager = KnowledgeBaseManager(provider_manager)
    await kb_manager.initialize()

    return kb_manager


@click.group(name="bk")
def bk():
    """Backup management (Export/Import)"""
    pass


@bk.command(name="export")
@click.option("--output", "-o", help="Output directory", default=None)
@click.option(
    "--gpg-sign", "-S", is_flag=True, help="Sign backup with GPG default private key"
)
@click.option(
    "--gpg-encrypt",
    "-E",
    help="Encrypt for GPG recipient (Asymmetric)",
    metavar="RECIPIENT",
)
@click.option(
    "--gpg-symmetric", "-C", is_flag=True, help="Encrypt with symmetric cipher (GPG)"
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

    Examples:

    \b
    1. Standard Export:
       astrbot bk export
       -> Generates a plain .zip file.

    \b
    2. Signed Backup (Integrity Check):
       astrbot bk export -S
       -> Generates a .zip.gpg file containing the backup and your signature.
       -> NOT ENCRYPTED, but packaged in OpenPGP format.
       -> Use 'astrbot bk import' or 'gpg --verify' to check integrity.

    \b
    3. Password Protected (Symmetric Encryption):
       astrbot bk export -C
       -> Generates an encrypted .zip.gpg file.
       -> Prompts for a passphrase.
       -> Only accessible with the passphrase.

    \b
    4. Encrypted for Recipient (Asymmetric Encryption):
       astrbot bk export -E "alice@example.com"
       -> Generates an encrypted .zip.gpg file for Alice.
       -> Only Alice's private key can decrypt it.

    \b
    5. Signed and Encrypted with Digest:
       astrbot bk export -S -E "bob@example.com" -d sha256
       -> Signs, encrypts for Bob, and generates a SHA256 checksum file.
    """

    # Handle case where -E consumes the next flag (e.g. -E -S)
    if gpg_encrypt and gpg_encrypt.startswith("-"):
        consumed_flag = gpg_encrypt
        click.echo(
            click.style(
                f"Warning: Flag '{consumed_flag}' was interpreted as the recipient for -E.",
                fg="yellow",
            )
        )

        # Recover flags
        if consumed_flag == "-S":
            gpg_sign = True
            click.echo("Recovered flag -S (Sign).")
        elif consumed_flag == "-C":
            gpg_symmetric = True
            click.echo("Recovered flag -C (Symmetric).")

        # Prompt for the actual recipient
        gpg_encrypt = click.prompt("Please enter the GPG recipient (email or key ID)")

    async def _run():
        if gpg_sign or gpg_encrypt or gpg_symmetric:
            if not shutil.which("gpg"):
                raise click.ClickException(
                    "GPG tool not found. Please install GnuPG to use encryption/signing features."
                )

        exporter = AstrBotExporter(db_helper)

        async def on_progress(stage, current, total, message):
            click.echo(f"[{stage}] {message}")

        try:
            path_str = await exporter.export_all(output, progress_callback=on_progress)
            final_path = Path(path_str)
            click.echo(
                click.style(f"\nRaw backup exported to: {final_path}", fg="green")
            )

            # GPG Operations
            if gpg_sign or gpg_encrypt or gpg_symmetric:
                # Construct GPG command
                # output file usually ends with .gpg
                gpg_output = final_path.with_name(final_path.name + ".gpg")
                cmd = ["gpg", "--output", str(gpg_output), "--yes"]

                if gpg_symmetric:
                    if gpg_encrypt:
                        click.echo(
                            click.style(
                                "Warning: Symmetric encryption selected, ignoring asymmetric recipient.",
                                fg="yellow",
                            )
                        )
                    cmd.append("--symmetric")
                    # No --batch to allow interactive passphrase entry on TTY
                else:
                    # Asymmetric or just Sign
                    # Note: If encrypting, -s adds signature to the encrypted packet.
                    if gpg_encrypt:
                        cmd.extend(["--encrypt", "--recipient", gpg_encrypt])

                    if gpg_sign:
                        cmd.append("--sign")

                cmd.append(str(final_path))

                click.echo(f"Running GPG: {' '.join(cmd)}")

                # Replace subprocess.run with asyncio.create_subprocess_exec to avoid blocking the event loop
                process = await asyncio.create_subprocess_exec(*cmd)
                await process.wait()

                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode or 1, cmd)

                # Clean up original file
                await anyio.Path(final_path).unlink()
                final_path = gpg_output
                click.echo(
                    click.style(f"Processed backup created: {final_path}", fg="green")
                )

            # Digest Generation
            if digest:
                click.echo(f"Calculating {digest} digest...")
                hash_func = getattr(hashlib, digest)()
                # Read file in chunks
                async with await anyio.open_file(final_path, "rb") as f:
                    while chunk := await f.read(8192):
                        hash_func.update(chunk)

                digest_val = hash_func.hexdigest()
                digest_file = final_path.with_name(final_path.name + f".{digest}")
                await anyio.Path(digest_file).write_text(
                    f"{digest_val} *{final_path.name}\n", encoding="utf-8"
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
    If the file is encrypted, you will be prompted for the passphrase.
    If a digest file (.sha256, .md5, etc.) exists, it will be verified automatically.
    """
    backup_path = Path(backup_file)
    if not backup_path.exists():
        raise click.ClickException(f"Backup file not found: {backup_file}")

    # 1. Verify Digest if exists
    def _verify_digest(file_path: Path) -> bool:
        supported_digests = ["sha256", "sha512", "md5", "sha1"]
        digest_verified = True  # Default true if no digest file found

        for algo in supported_digests:
            digest_file = file_path.with_name(f"{file_path.name}.{algo}")
            if digest_file.exists():
                click.echo(f"Found digest file: {digest_file.name}")
                try:
                    # Parse digest file
                    content = digest_file.read_text(encoding="utf-8").strip()
                    # Format: "digest *filename" or "digest  filename"
                    # We expect the hash to be the first part
                    if " " in content:
                        expected_digest = content.split()[0].lower()
                    else:
                        expected_digest = content.lower()

                    click.echo(f"Verifying {algo} digest...")
                    hash_func = getattr(hashlib, algo)()
                    with open(file_path, "rb") as f:
                        while chunk := f.read(8192):
                            hash_func.update(chunk)

                    calculated_digest = hash_func.hexdigest().lower()

                    if calculated_digest == expected_digest:
                        click.echo(
                            click.style("Digest verification PASSED.", fg="green")
                        )
                    else:
                        click.echo(
                            click.style(
                                "Digest verification FAILED!", fg="red", bold=True
                            )
                        )
                        click.echo(f"  Expected: {expected_digest}")
                        click.echo(f"  Actual:   {calculated_digest}")
                        digest_verified = False
                except Exception as e:
                    click.echo(click.style(f"Error checking digest: {e}", fg="red"))
                    digest_verified = False

        return digest_verified

    if not _verify_digest(backup_path):
        if not yes:
            if not click.confirm(
                "Digest verification failed. Abort import?", default=True, abort=True
            ):
                pass
        else:
            click.echo(
                click.style(
                    "Warning: Digest verification failed. Continuing due to --yes.",
                    fg="yellow",
                )
            )

    if not yes:
        click.confirm(
            "This will OVERWRITE all current data (DB, Config, Plugins). Continue?",
            abort=True,
            default=False,
        )

    async def _run():
        zip_path = backup_path
        is_temp_file = False

        # Handle GPG encrypted files
        if backup_path.suffix == ".gpg":
            if not shutil.which("gpg"):
                raise click.ClickException(
                    "GPG tool not found. Cannot decrypt .gpg file."
                )

            # Remove .gpg extension for output
            decrypted_path = backup_path.with_suffix("")
            # If it doesn't look like a zip after stripping .gpg, maybe append .zip?
            # But the exporter creates .zip.gpg, so stripping .gpg gives .zip.

            click.echo(f"Processing GPG file {backup_path}...")
            try:
                cmd = [
                    "gpg",
                    "--output",
                    str(decrypted_path),
                    "--decrypt",  # This handles both decryption and signature verification/extraction
                    str(backup_path),
                ]
                # Allow interactive passphrase
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

        kb_mgr = await _get_kb_manager()
        importer = AstrBotImporter(db_helper, kb_mgr)

        async def on_progress(stage, current, total, message):
            click.echo(f"[{stage}] {message}")

        try:
            result = await importer.import_all(
                str(zip_path), progress_callback=on_progress
            )

            if result.errors:
                click.echo(
                    click.style("\nImport failed with errors:", fg="red"), err=True
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
