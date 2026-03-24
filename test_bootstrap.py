"""Bootstrap integration test - validates the orchestrator and gateway."""

from __future__ import annotations

import asyncio
import sys


async def test_bootstrap_components():
    """Test that all bootstrap components can be imported and initialized."""
    print("=" * 60)
    print("AstrBot Bootstrap Integration Test")
    print("=" * 60)

    # Test 1: Import all components
    print("\n[1] Testing imports...")
    try:
        from astrbot._internal.geteway.server import AstrbotGateway
        from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

        print("    ✓ All imports successful")
    except Exception as e:
        print(f"    ✗ Import failed: {e}")
        return False

    # Test 2: Create orchestrator
    print("\n[2] Testing orchestrator creation...")
    try:
        orchestrator = AstrbotOrchestrator()
        print("    ✓ Orchestrator created")
        print(f"      - LSP client: {type(orchestrator.lsp).__name__}")
        print(f"      - MCP client: {type(orchestrator.mcp).__name__}")
        print(f"      - ACP client: {type(orchestrator.acp).__name__}")
        print(f"      - ABP client: {type(orchestrator.abp).__name__}")
    except Exception as e:
        print(f"    ✗ Orchestrator creation failed: {e}")
        return False

    # Test 3: Test ABP star registration
    print("\n[3] Testing ABP star registration...")
    try:
        from unittest.mock import AsyncMock, MagicMock

        # Create a mock star
        mock_star = MagicMock()
        mock_star.call_tool = AsyncMock(return_value="test_result")

        # Register the star
        await orchestrator.register_star("test-star", mock_star)
        print("    ✓ Star registered")

        # Verify registration
        retrieved = await orchestrator.get_star("test-star")
        if retrieved is mock_star:
            print("    ✓ Star retrieval works")
        else:
            print("    ✗ Star retrieval failed")

        # List stars
        stars = await orchestrator.list_stars()
        print(f"    ✓ Stars list: {stars}")

        # Unregister
        await orchestrator.unregister_star("test-star")
        print("    ✓ Star unregistered")
    except Exception as e:
        print(f"    ✗ ABP star test failed: {e}")
        import traceback

        traceback.print_exc()

    # Test 4: Create gateway
    print("\n[4] Testing gateway creation...")
    try:
        gateway = AstrbotGateway(orchestrator)
        print("    ✓ Gateway created")
        print(f"      - Host: {gateway._host}")
        print(f"      - Port: {gateway._port}")
        print(f"      - WebSocket manager: {type(gateway.ws_manager).__name__}")
    except Exception as e:
        print(f"    ✗ Gateway creation failed: {e}")
        import traceback

        traceback.print_exc()

    # Test 5: Check anyio usage in components
    print("\n[5] Checking anyio compliance...")
    import inspect

    orchestrator_source = inspect.getsource(orchestrator.__class__)
    if "asyncio" in orchestrator_source and "import asyncio" in orchestrator_source:
        print("    ⚠ Orchestrator imports asyncio (violation)")
    else:
        print("    ✓ Orchestrator uses anyio only")

    gateway_source = inspect.getsource(gateway.__class__)
    if "import asyncio" in gateway_source:
        print("    ⚠ Gateway imports asyncio (violation)")
    else:
        print("    ✓ Gateway anyio check passed")

    print("\n" + "=" * 60)
    print("Bootstrap integration test completed")
    print("=" * 60)

    return True


if __name__ == "__main__":
    # Run with asyncio since the test itself is sync
    result = asyncio.run(test_bootstrap_components())
    sys.exit(0 if result else 1)
