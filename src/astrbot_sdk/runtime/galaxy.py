"""
VPL means Virtual Star Layer.
In the AstrBot 5.0 architecture, VPL is a layer that allows different types of stars to interact with the core system in a standardized way.
Currently, AstrBot has two types of stars:
    1. Legacy Stars: These are the traditional stars that still running in the same runtime as AstrBot core.
    2. New Stars: These are the modern stars that run in isolated runtime, they communicate with AstrBot core through stdio streams or websocket.

The VPL module provides the necessary abstractions and interfaces to manage these stars seamlessly,
let AstrBot core interact with both types of stars without needing to know the underlying implementation details.
"""

from .stars.virtual import VirtualStar
from .stars.new import NewStdioStar, NewWebSocketStar
# from .types import StarURI, StarType


class Galaxy:
    """Manages the lifecycle and interactions of Virtual Stars (plugins) within AstrBot."""

    vs_map: dict[str, VirtualStar] = {}

    async def connect_to_stdio_star(self, star_name: str, config: dict) -> NewStdioStar:
        """Connect to a new-style stdio star given its name."""
        star = NewStdioStar(**config)
        await star.initialize()
        self.vs_map[star_name] = star
        return star

    async def connect_to_websocket_star(
        self, star_name: str, config: dict
    ) -> NewWebSocketStar:
        """Connect to a new-style websocket star given its name."""
        star = NewWebSocketStar(**config)
        await star.initialize()
        self.vs_map[star_name] = star
        return star
