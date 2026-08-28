"""
Custom Hatchling build hook.

Only runs when the environment variable ASTRBOT_BUILD_DASHBOARD=1 is set,
so that `uv sync` / editable installs are never affected.

Usage:
    ASTRBOT_BUILD_DASHBOARD=1 uv build

When enabled, this hook:
1. Runs `pnpm run build` inside the `dashboard/` directory.
2. Copies the resulting `dashboard/dist/` tree into
   `astrbot/dashboard/dist/` so the static assets are shipped
   inside the Python wheel.
3. Builds VitePress with `ASTRBOT_DOCS_BASE=/help/` and copies
   the output into `astrbot/dashboard/dist/help/`.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        # Only run when explicitly requested (e.g. during CI / release builds).
        # This prevents `uv sync` / editable installs from triggering dashboard
        # package installation and frontend builds.
        if os.environ.get("ASTRBOT_BUILD_DASHBOARD", "").strip() != "1":
            return

        root = Path(self.root)
        sys.path.insert(0, str(root))
        from scripts.sync_dashboard_dist import embed_docs_help

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
                ["pnpm", "install", "--frozen-lockfile"],
                cwd=dashboard_src,
                check=True,
            )

        # ── Build the Vue/Vite dashboard ──────────────────────────────────────
        print("[hatch_build] Building Vue dashboard (pnpm run build)...")
        subprocess.run(
            ["pnpm", "run", "build"],
            cwd=dashboard_src,
            check=True,
        )

        if not dist_src.exists():
            print(
                "[hatch_build] dashboard/dist not found after build – skipping copy.",
                file=sys.stderr,
            )
            return

        docs_src = root / "docs"
        if (docs_src / "package.json").exists():
            if not (docs_src / "node_modules").exists():
                print("[hatch_build] Installing docs Node dependencies...")
                subprocess.run(
                    ["pnpm", "install", "--frozen-lockfile"],
                    cwd=docs_src,
                    check=True,
                )
            print("[hatch_build] Building VitePress documentation...")
            env = os.environ.copy()
            env["ASTRBOT_DOCS_BASE"] = "/help/"
            subprocess.run(
                ["pnpm", "run", "docs:build"],
                cwd=docs_src,
                check=True,
                env=env,
            )
            help_dir = embed_docs_help(dist_src, repo_root=root)
            if help_dir is not None:
                print(f"[hatch_build] Docs dist copied → {help_dir.relative_to(root)}")

        # ── Copy into the Python package tree ────────────────────────────────
        if dist_target.exists():
            shutil.rmtree(dist_target)
        shutil.copytree(dist_src, dist_target)
        print(f"[hatch_build] Dashboard dist copied → {dist_target.relative_to(root)}")
