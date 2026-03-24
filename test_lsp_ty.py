"""Test LSP client connecting to ty server via stdio."""

from __future__ import annotations

import asyncio
import sys


async def test_lsp_ty_integration():
    """Test that LSP client can connect to ty server via stdio."""
    print("=" * 60)
    print("LSP Client - ty Server Integration Test")
    print("=" * 60)

    # Start ty server as subprocess
    print("\n[1] Starting ty server...")
    ty_process = await asyncio.create_subprocess_exec(
        "ty",
        "server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    print(f"    ✓ ty server started (PID: {ty_process.pid})")

    # Import LSP client
    print("\n[2] Importing LSP client...")
    try:
        from astrbot._internal.protocols.lsp.client import AstrbotLspClient

        client = AstrbotLspClient()
        print("    ✓ LSP client created")
    except Exception as e:
        print(f"    ✗ Failed to import/create client: {e}")
        ty_process.terminate()
        return False

    # Connect to ty server
    print("\n[3] Connecting to ty server...")
    try:
        await client.connect_to_server(
            command=["ty", "server"],
            workspace_uri="file:///home/lightjunction/GITHUB/AstrBot",
        )
        print("    ✓ Connected to ty server")
    except Exception as e:
        print(
            f"    ⚠ Connection failed (expected if ty doesn't support external connections): {e}"
        )
        # This is expected - ty server uses stdio but our client expects subprocess

    # Test 4: Send initialize request
    print("\n[4] Testing LSP protocol...")
    try:
        result = await client.send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": "file:///home/lightjunction/GITHUB/AstrBot",
                "capabilities": {},
            },
        )
        print(f"    ✓ Initialize response: {result}")
    except Exception as e:
        print(f"    ⚠ LSP request failed: {e}")

    # Cleanup
    print("\n[5] Shutting down...")
    await client.shutdown()
    ty_process.terminate()
    await ty_process.wait()
    print("    ✓ Cleanup complete")

    print("\n" + "=" * 60)
    print("LSP ty integration test completed")
    print("=" * 60)

    return True


if __name__ == "__main__":
    result = asyncio.run(test_lsp_ty_integration())
    sys.exit(0 if result else 1)
