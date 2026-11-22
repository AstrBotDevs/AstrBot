from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from .group_worker import serve_group_stdio
from .stdio_server import serve_stdio_plugin
from .uds_runner import serve_uds_plugin
from .ws_runner import RUNNER_TOKEN_ENV, serve_ws_plugin

# Legacy plugins may spawn multiprocessing children (spawn start method). The
# fresh child interpreter re-imports this module during multiprocessing's
# main-module fixup, before it can import the plugin module by name. Reinstall
# the legacy compat shims so plugin code importing `astrbot.*` works there.
if __name__ != "__main__" and os.environ.get("ASTRBOT_SDK_LEGACY_RUNNER") == "1":
    from ..compat.v1.api import install as _install_legacy_api

    _install_legacy_api(host_version=os.environ.get("ASTRBOT_HOST_VERSION") or None)
    # Fresh interpreters do not inherit sys.modules; rebuild the parent's
    # virtual data.plugins anchors so the plugin module resolves by name.
    from .loader import reinstall_virtual_plugin_roots_from_env

    reinstall_virtual_plugin_roots_from_env()


def main() -> None:
    """Run the AstrBot SDK plugin Runner CLI."""
    parser = argparse.ArgumentParser(prog="astrbot-sdk-runner")
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument(
        "--stdio",
        action="store_true",
        help="Use the stdio transport (host-spawned runners)",
    )
    transport.add_argument(
        "--group-stdio",
        action="store_true",
        help="Serve multiple plugins over a multiplexed stdio stream",
    )
    transport.add_argument(
        "--ws",
        metavar="URL",
        help="Dial out to the Host WebSocket listener (ws:// or wss://)",
    )
    transport.add_argument(
        "--uds",
        metavar="CREDENTIAL_FILE",
        help="Attach to the Host Unix domain socket via an external credential file",
    )
    parser.add_argument("--plugin-root", type=Path, required=False)
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Load the plugin through the legacy compat layer",
    )
    args = parser.parse_args()
    if args.group_stdio:
        asyncio.run(serve_group_stdio())
        return
    if args.plugin_root is None:
        parser.error("--plugin-root is required for --stdio/--ws/--uds")
    if args.stdio:
        asyncio.run(serve_stdio_plugin(args.plugin_root, legacy=args.legacy))
        return
    if args.uds:
        asyncio.run(
            serve_uds_plugin(
                args.plugin_root,
                Path(args.uds),
                legacy=args.legacy,
            )
        )
        return
    asyncio.run(
        serve_ws_plugin(
            args.plugin_root,
            args.ws,
            token=os.environ.get(RUNNER_TOKEN_ENV),
            legacy=args.legacy,
        )
    )


if __name__ == "__main__":
    main()
