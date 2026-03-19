#!/usr/bin/env python3
"""
CLI commands to manage the WebUI (dashboard) lifecycle: install/build/dev/serve.

Commands:
- webui install [--root]         : install frontend dependencies (pnpm/npm)
- webui build [--root]           : build production assets
- webui dev [--root]             : run frontend dev server (long-running)
- webui serve [--root --port]    : serve built dist via simple HTTP server

This file follows the existing AstrBot CLI conventions and raises ClickException
for error conditions so callers and pre-commit hooks can observe failures.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from astrbot.cli.utils.basic import get_astrbot_root
from astrbot.core.utils.astrbot_path import get_astrbot_path


def _find_dashboard_source(root: str | None = None) -> Path | None:
    """
    Locate the dashboard source directory.

    Priority:
      1. <ASTRBOT_ROOT>/dashboard
      2. repository/dashboard relative to the project path (get_astrbot_path)
      3. None if not found
    """
    base = Path(root) if root else Path(get_astrbot_root())
    cand = base / "dashboard"
    if cand.is_dir():
        return cand

    pkg_cand = Path(get_astrbot_path()) / "dashboard"
    if pkg_cand.is_dir():
        return pkg_cand

    return None


def _find_dashboard_dist(root: str | None = None) -> Path | None:
    """
    Locate the built dashboard dist directory.

    Priority:
      1. <ASTRBOT_ROOT>/data/dist
      2. packaged astrbot/dashboard/dist
      3. None
    """
    base = Path(root) if root else Path(get_astrbot_root())
    cand = base / "data" / "dist"
    if cand.is_dir():
        return cand

    pkg_dist = Path(get_astrbot_path()) / "dashboard" / "dist"
    if pkg_dist.is_dir():
        return pkg_dist

    return None


def _choose_package_manager() -> str:
    """
    Prefer pnpm, fall back to npm. Raise ClickException if none available.
    """
    if shutil.which("pnpm"):
        return "pnpm"
    if shutil.which("npm"):
        return "npm"
    raise click.ClickException(
        "Neither 'pnpm' nor 'npm' found on PATH. Please install one of them to build/run the dashboard."
    )


@click.group(name="webui")
def webui_group() -> None:
    """Manage the WebUI (dashboard) frontend: install/build/dev/serve"""
    pass


# Export a stable symbol expected by the command registry
webui = webui_group


@webui_group.command(name="install")
@click.option("--root", type=str, required=False, help="AstrBot root directory")
def webui_install(root: str | None) -> None:
    """Install frontend dependencies (pnpm/npm install)."""
    src = _find_dashboard_source(root)
    if not src:
        raise click.ClickException(
            "Dashboard source directory not found. Cannot install dependencies."
        )
    pm = _choose_package_manager()
    click.echo(f"Installing frontend dependencies using {pm} in {src}")
    try:
        subprocess.run([pm, "install"], cwd=str(src), check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"Failed to install frontend dependencies: {e}")


@webui_group.command(name="build")
@click.option("--root", type=str, required=False, help="AstrBot root directory")
def webui_build(root: str | None) -> None:
    """Build production dashboard (runs pnpm/npm run build)."""
    src = _find_dashboard_source(root)
    if not src:
        raise click.ClickException(
            "Dashboard source directory not found. Cannot build."
        )
    pm = _choose_package_manager()
    click.echo(f"Building dashboard using {pm} in {src}")

    # Ensure dependencies are installed first (best-effort)
    try:
        subprocess.run([pm, "install"], cwd=str(src), check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(
            f"Failed to install frontend dependencies before build: {e}"
        )

    try:
        subprocess.run([pm, "run", "build"], cwd=str(src), check=True)
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"Dashboard build failed: {e}")


@webui_group.command(name="dev")
@click.option("--root", type=str, required=False, help="AstrBot root directory")
def webui_dev(root: str | None) -> None:
    """Start the frontend dev server (long-running)."""
    src = _find_dashboard_source(root)
    if not src:
        raise click.ClickException(
            "Dashboard source directory not found. Cannot start dev server."
        )
    pm = _choose_package_manager()
    click.echo(f"Starting dashboard dev server using {pm} in {src}")

    # Note: This is intentionally long-running; we do not set check=True to allow
    # the process's exit code to be observed by the caller.
    try:
        subprocess.run([pm, "run", "dev"], cwd=str(src))
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"Dev server exited with error: {e}")


@webui_group.command(name="serve")
@click.option("--root", type=str, required=False, help="AstrBot root directory")
@click.option("--port", type=int, required=False, default=8080, help="Port to serve on")
def webui_serve(root: str | None, port: int) -> None:
    """Serve built dashboard dist via a simple HTTP server."""
    dist = _find_dashboard_dist(root)
    if not dist:
        raise click.ClickException(
            "Built dashboard dist not found. Run 'astrbot webui build' first."
        )
    click.echo(f"Serving dashboard from {dist} on port {port}")
    python_bin = shutil.which("python3") or shutil.which("python") or sys.executable
    try:
        # Long running; let exit code propagate
        subprocess.run([python_bin, "-m", "http.server", str(port)], cwd=str(dist))
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"Failed to serve dashboard: {e}")
