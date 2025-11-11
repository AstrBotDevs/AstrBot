import typing as T
from abc import ABC, abstractmethod

from ...api.event.astr_message_event import AstrMessageEvent
from ...api.star.star import StarMetadata
from .registry import StarHandlerMetadata
from ...api.star.context import Context


class VirtualStar(ABC):
    """Abstract base class for virtual plugin implementations.
    
    VirtualStar defines the interface for plugins that can run in isolated
    runtime environments (separate processes). It handles the complete lifecycle
    of a plugin from initialization to shutdown.
    """
    def __init__(self, context: Context) -> None:
        self._context = context

    @abstractmethod
    async def initialize(self) -> None:
        """Establish connection and initialize the plugin.
        
        This method should:
        - Start the plugin process (if applicable)
        - Establish communication channels
        - Wait for the plugin to be ready
        
        Raises:
            RuntimeError: If initialization fails
        """
        ...

    @abstractmethod
    async def handshake(self) -> StarMetadata:
        """Perform handshake to retrieve plugin metadata.
        
        This method should:
        - Request plugin metadata from the plugin
        - Cache handler information locally
        - Validate the plugin's compatibility
        
        Returns:
            StarMetadata: Complete plugin metadata including handlers
            
        Raises:
            RuntimeError: If handshake fails or times out
        """
        ...

    # @abstractmethod
    # async def turn_on(self) -> None:
    #     """Attach and prepare resources. Only call when the plugin is not active.
        
    #     This method should:
    #     - Activate the plugin
    #     - Initialize any runtime resources
    #     - Prepare the plugin to handle events
        
    #     Raises:
    #         RuntimeError: If activation fails
    #     """
    #     ...

    # @abstractmethod
    # async def turn_off(self) -> None:
    #     """Detach and clean up resources. Make the plugin inactive.
        
    #     This method should:
    #     - Deactivate the plugin
    #     - Release runtime resources
    #     - Keep the process running but idle
        
    #     Raises:
    #         RuntimeError: If deactivation fails
    #     """
    #     ...

    @abstractmethod
    def get_triggered_handlers(
        self,
        event: AstrMessageEvent,
    ) -> list[StarHandlerMetadata]:
        """Get the list of handlers that should be triggered for this event.
        
        This method uses cached handler metadata to determine which handlers
        should handle the given event. No RPC calls should be made here.
        
        Args:
            event: The message event to check
            
        Returns:
            List of handler metadata that match the event
        """
        ...

    @abstractmethod
    async def call_handler(
        self,
        handler: StarHandlerMetadata,
        event: AstrMessageEvent,
        *args,
        **kwargs,
    ) -> T.Any:
        """Call a registered handler in the plugin.
        
        This method should:
        - Serialize the event and arguments
        - Call the handler via RPC
        - Wait for and return the result
        
        Args:
            handler: The handler metadata
            event: The message event
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
            
        Returns:
            The result from the handler
            
        Raises:
            RuntimeError: If the handler call fails or times out
        """
        ...
