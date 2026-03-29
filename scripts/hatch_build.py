"""
Custom Hatchling build hook.

Only runs when the environment variable ASTRBOT_BUILD_DASHBOARD=1 is set,
so that `uv sync` / editable installs are never affected.

Usage:
    ASTRBOT_BUILD_DASHBOARD=1 uv build

When enabled, this hook:
1. Runs `npm run build` inside the `dashboard/` directory.
2. Copies the resulting `dashboard/dist/` tree into
   `astrbot/dashboard/dist/` so the static assets are shipped
   inside the Python wheel.
"""

import os
import shutil
import subprocess
import sys
from logging import getLogger
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

logger = getLogger(__name__)


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        dashboard_src = root / "dashboard"
        dist_src = dashboard_src / "dist"
        dist_target = root / "astrbot" / "dashboard" / "dist"

        if os.environ.get("ASTRBOT_BUILD_DASHBOARD", "").strip() != "1":
            # Ensure the target directory and a placeholder exist so the wheel
            # build does not fail when artifacts = ["..."] is declared.
            dist_target.mkdir(parents=True, exist_ok=True)
            if not dist_target.exists() or not any(dist_target.iterdir()):
                placeholder = dist_target / ".placeholder"
                placeholder.write_text("# dashboard placeholder\n")
            return

        if not dashboard_src.exists():
            logger.warning(
                "[hatch_build] 'dashboard/' directory not found: skipping dashboard build.",
                file=sys.stderr,
            )
            dist_target.mkdir(parents=True, exist_ok=True)
            placeholder = dist_target / ".placeholder"
            placeholder.write_text("# dashboard placeholder\n")
            return

        # ── Install Node dependencies if node_modules is absent ─────────────
        if not (dashboard_src / "node_modules").exists():
            logger.info("[hatch_build] Installing dashboard Node dependencies...")
            subprocess.run(
                ["npm", "install"],
                cwd=dashboard_src,
                check=True,
            )

        # ── Build the Vue/Vite dashboard ──────────────────────────────────────
        logger.info("[hatch_build] Building Vue dashboard (npm run build)...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=dashboard_src,
            check=True,
        )

        if not dist_src.exists():
            logger.warning(
                "[hatch_build] dashboard/dist not found after build: skipping copy.",
                file=sys.stderr,
            )
            dist_target.mkdir(parents=True, exist_ok=True)
            placeholder = dist_target / ".placeholder"
            placeholder.write_text("# dashboard placeholder\n")
            return

        # ── Copy into the Python package tree ───────────────────────────────
        if dist_target.exists():
            shutil.rmtree(dist_target)
        shutil.copytree(dist_src, dist_target)
        logger.info(
            f"[hatch_build] Dashboard dist copied ￫ {dist_target.relative_to(root)}"
        )
