"""
ABP Protocol Demo - Demonstrates ABP (AstrBot Protocol) functionality.

This example shows:
1. Creating an Orchestrator
2. Registering a mock star with the orchestrator
3. Using the ABP client to call star tools
4. Verifying the result

Run with: uv run python examples/abp_demo.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import anyio


# Mock Star class that implements the expected interface
@dataclass
class MockStar:
    """A mock star (plugin) for demonstration."""

    name: str
    description: str = "A mock star for demonstration"

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Handle tool calls from the ABP client.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        if tool_name == "echo":
            return {"echo": arguments.get("message", "")}
        elif tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            return {"result": a + b}
        elif tool_name == "status":
            return {"status": "ok", "star": self.name}
        else:
            raise ValueError(f"Unknown tool: {tool_name}")


async def main() -> None:
    """Run the ABP demo."""
    print("=" * 60)
    print("ABP Protocol Demo")
    print("=" * 60)

    # Import here to demonstrate the module structure
    from astrbot._internal.runtime.orchestrator import AstrbotOrchestrator

    print("\n1. Creating Orchestrator...")
    orchestrator = AstrbotOrchestrator()
    print(f"   - Orchestrator created: {orchestrator}")
    print(f"   - Running: {orchestrator.running}")

    # Connect the ABP client
    print("\n2. Connecting ABP client...")
    await orchestrator.abp.connect()
    print(f"   - ABP connected: {orchestrator.abp.connected}")

    # Create and register a mock star
    print("\n3. Registering mock star...")
    mock_star = MockStar(name="demo-star", description="Demo star for ABP testing")
    await orchestrator.register_star("demo-star", mock_star)
    print(f"   - Star registered: {mock_star.name}")
    print(f"   - Stars in registry: {await orchestrator.list_stars()}")

    # Call star tool via ABP client
    print("\n4. Calling star tool via ABP client...")

    # Test 1: Echo tool
    print("\n   Test 1: echo tool")
    result = await orchestrator.abp.call_star_tool(
        star_name="demo-star",
        tool_name="echo",
        arguments={"message": "Hello from ABP!"}
    )
    print(f"   - Result: {result}")

    # Test 2: Add tool
    print("\n   Test 2: add tool")
    result = await orchestrator.abp.call_star_tool(
        star_name="demo-star",
        tool_name="add",
        arguments={"a": 10, "b": 25}
    )
    print(f"   - Result: {result}")

    # Test 3: Status tool
    print("\n   Test 3: status tool")
    result = await orchestrator.abp.call_star_tool(
        star_name="demo-star",
        tool_name="status",
        arguments={}
    )
    print(f"   - Result: {result}")

    # Verify get_star
    print("\n5. Verifying star retrieval...")
    star = await orchestrator.get_star("demo-star")
    print(f"   - Retrieved star: {star}")
    print(f"   - Star name: {star.name if star else 'None'}")

    # Unregister star
    print("\n6. Unregistering star...")
    await orchestrator.unregister_star("demo-star")
    print(f"   - Stars remaining: {await orchestrator.list_stars()}")

    # Shutdown
    print("\n7. Shutting down...")
    await orchestrator.shutdown()
    print(f"   - Running: {orchestrator.running}")

    print("\n" + "=" * 60)
    print("ABP Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    anyio.run(main)
