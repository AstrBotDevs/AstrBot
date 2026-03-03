"""
Custom Hatchling build hook.

During `hatch build` (or `pip wheel`), this hook:
1. Runs `npm run build` inside the `dashboard/` directory.
2. Copies the resulting `dashboard/dist/` tree into
   `astrbot/dashboard/dist/` so the static assets are shipped
   inside the Python wheel.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        root = Path(self.root)
        dashboard_src = root / "dashboard"
        dist_src = dashboard_src / "dist"
        dist_target = root / "astrbot" / "dashboard" / "dist"

        if not dashboard_src.exists():
            print(
                "[hatch_build] 'dashboard/' directory not found – skipping dashboard build.",
                file=sys.stderr,
            )
            return

        # ── Install Node dependencies if node_modules is absent ─────────────
        if not (dashboard_src / "node_modules").exists():
            print("[hatch_build] Installing dashboard Node dependencies...")
            subprocess.run(
                ["npm", "install"],
                cwd=dashboard_src,
                check=True,
            )

        # ── Build the Vue/Vite dashboard ──────────────────────────────────────
        print("[hatch_build] Building Vue dashboard (npm run build)...")
        subprocess.run(
            ["npm", "run", "build"],
            cwd=dashboard_src,
            check=True,
        )

        if not dist_src.exists():
            print(
                "[hatch_build] dashboard/dist not found after build – skipping copy.",
                file=sys.stderr,
            )
            return

        # ── Copy into the Python package tree ────────────────────────────────
        if dist_target.exists():
            shutil.rmtree(dist_target)
        shutil.copytree(dist_src, dist_target)
        print(f"[hatch_build] Dashboard dist copied → {dist_target.relative_to(root)}")
