"""TTY交互模式处理器"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from .cli_event import CLIMessageEvent


class TTYHandler:
    """TTY交互模式处理器"""

    EXIT_COMMANDS = frozenset({"exit", "quit"})
    BANNER = """
============================================================
AstrBot CLI Simulator
============================================================
Type your message and press Enter to send.
Type 'exit' or 'quit' to stop.
============================================================
"""

    def __init__(
        self,
        message_converter,
        platform_meta: "PlatformMetadata",
        output_queue: asyncio.Queue,
        event_committer: Callable[["CLIMessageEvent"], None],
    ):
        self.message_converter = message_converter
        self.platform_meta = platform_meta
        self.output_queue = output_queue
        self.event_committer = event_committer
        self._running = False

    async def run(self) -> None:
        self._running = True
        print(self.BANNER)

        output_task = asyncio.create_task(self._output_loop())

        try:
            await self._input_loop()
        except KeyboardInterrupt:
            logger.info("[CLI] Received KeyboardInterrupt")
        finally:
            self._running = False
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

    def stop(self) -> None:
        self._running = False

    async def _input_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while self._running:
            user_input = await loop.run_in_executor(None, input, "You: ")
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in self.EXIT_COMMANDS:
                break
            await self._handle_input(user_input)

    async def _handle_input(self, text: str) -> None:
        from .cli_event import CLIMessageEvent

        message = self.message_converter.convert(text)
        message_event = CLIMessageEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.platform_meta,
            session_id=message.session_id,
            output_queue=self.output_queue,
        )
        self.event_committer(message_event)

    async def _output_loop(self) -> None:
        while self._running:
            try:
                message_chain = await asyncio.wait_for(
                    self.output_queue.get(), timeout=0.5
                )
                self._print_response(message_chain)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def _print_response(self, message_chain: MessageChain) -> None:
        print(f"\nBot: {message_chain.get_plain_text()}\n")
