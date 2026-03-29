"""
Custom maturin build hook for AstrBot.

This hook runs before the native extension is built.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_root():
    """Get project root directory."""
    return Path(__file__).parent.parent.parent


def get_dashboard_dist():
    """Get the dashboard dist source directory."""
    root = get_root()
    return root / "dashboard" / "dist"


def get_dashboard_target():
    """Get the target directory in the Python package."""
    root = get_root()
    return root / "astrbot" / "dashboard" / "dist"


def build_dashboard():
    """Build the Vue dashboard using npm."""
    root = get_root()
    dashboard_src = root / "dashboard"

    if not dashboard_src.exists():
        print("[maturin-hook] dashboard/ directory not found, skipping dashboard build")
        return False

    # Install node_modules if needed
    if not (dashboard_src / "node_modules").exists():
        print("[maturin-hook] Installing dashboard Node dependencies...")
        subprocess.run(
            ["npm", "install"],
            cwd=dashboard_src,
            check=True,
            capture_output=True,
            text=True,
        )
        print(
            "[maturin-hook] npm install output:",
            subprocess.run(
                ["npm", "install"],
                cwd=dashboard_src,
                capture_output=True,
                text=True,
            ).stderr,
        )

    # Build dashboard
    print("[maturin-hook] Building Vue dashboard (npm run build)...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=dashboard_src,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[maturin-hook] npm build failed: {result.stderr}")
        return False
    print(f"[maturin-hook] npm build stdout: {result.stdout}")
    return True


def copy_dashboard_dist():
    """Copy dashboard dist to Python package."""
    dist_src = get_dashboard_dist()
    dist_target = get_dashboard_target()

    if not dist_src.exists():
        print("[maturin-hook] No dashboard/dist found after build")
        # Remove broken symlink if present so placeholder can be created
        if dist_target.is_symlink() and not dist_target.exists():
            dist_target.unlink()
        return False

    # Remove existing target (symlink or directory)
    if dist_target.is_symlink():
        dist_target.unlink()
    elif dist_target.exists():
        shutil.rmtree(dist_target)

    # Copy dist
    shutil.copytree(dist_src, dist_target)
    print(f"[maturin-hook] Dashboard dist copied to {dist_target}")
    return True


def generate_placeholder():
    """Generate placeholder if no dashboard."""
    dist_target = get_dashboard_target()

    # Remove broken symlink if present so we can create a real directory
    if dist_target.is_symlink() and not dist_target.exists():
        dist_target.unlink()

    dist_target.mkdir(parents=True, exist_ok=True)

    placeholder = dist_target / ".placeholder"
    if not any(dist_target.iterdir()):
        placeholder.write_text("# dashboard placeholder\n")
        print(f"[maturin-hook] Created placeholder at {placeholder}")


class MaturinBuildHook:
    """Maturin build hook class."""

    def __init__(self, args):
        self.args = args
        print(f"[maturin-hook] MaturinBuildHook initialized with args: {args}")

    def pre_build(self):
        """Called before build."""
        print("[maturin-hook] pre_build called!")
        print(f"[maturin-hook] Current dir: {os.getcwd()}")
        print(f"[maturin-hook] sys.argv: {sys.argv}")
        print(
            f"[maturin-hook] ASTRBOT_BUILD_DASHBOARD: {os.environ.get('ASTRBOT_BUILD_DASHBOARD', 'NOT SET')}"
        )

        root = get_root()
        print(f"[maturin-hook] Project root: {root}")

        if os.environ.get("ASTRBOT_BUILD_DASHBOARD", "").strip() == "1":
            print("[maturin-hook] Building dashboard...")
            if build_dashboard():
                copy_dashboard_dist()
        else:
            print(
                "[maturin-hook] Skipping dashboard build (ASTRBOT_BUILD_DASHBOARD != 1)"
            )
            generate_placeholder()

        return 0


def pre_build_hook(ctx):
    """Entry point for maturin pre-build hook.

    Args:
        ctx: BuildContext with manifest_path and cargo_args

    Returns:
        int: 0 on success
    """
    print("[maturin-hook] pre_build_hook called!")
    print(f"[maturin-hook] ctx: {ctx}")
    print(f"[maturin-hook] sys.argv: {sys.argv}")

    root = Path(__file__).parent.parent.parent
    print(f"[maturin-hook] Project root: {root}")

    if os.environ.get("ASTRBOT_BUILD_DASHBOARD", "").strip() == "1":
        print("[maturin-hook] Building dashboard...")
        if build_dashboard():
            copy_dashboard_dist()
        else:
            generate_placeholder()
    else:
        print("[maturin-hook] Skipping dashboard build (ASTRBOT_BUILD_DASHBOARD != 1)")
        generate_placeholder()

    # Ensure target directory exists for wheel artifacts
    dist_target = get_dashboard_target()
    dist_target.mkdir(parents=True, exist_ok=True)
    if not any(dist_target.iterdir()):
        generate_placeholder()

    return 0
