"""文件轮询模式处理器"""

import asyncio
import datetime
import os
from collections.abc import Callable
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

if TYPE_CHECKING:
    from astrbot.core.platform.platform_metadata import PlatformMetadata

    from .cli_event import CLIMessageEvent


class FileHandler:
    """文件轮询模式处理器"""

    def __init__(
        self,
        input_file: str,
        output_file: str,
        poll_interval: float,
        message_converter,
        platform_meta: "PlatformMetadata",
        output_queue: asyncio.Queue,
        event_committer: Callable[["CLIMessageEvent"], None],
    ):
        self.input_file = input_file
        self.output_file = output_file
        self.poll_interval = poll_interval
        self.message_converter = message_converter
        self.platform_meta = platform_meta
        self.output_queue = output_queue
        self.event_committer = event_committer
        self._running = False

    async def run(self) -> None:
        self._running = True
        self._ensure_directories()
        logger.info(
            f"[CLI] File mode: input={self.input_file}, output={self.output_file}"
        )

        output_task = asyncio.create_task(self._output_loop())
        try:
            await self._poll_loop()
        finally:
            self._running = False
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

    def stop(self) -> None:
        self._running = False

    def _ensure_directories(self) -> None:
        for path in (self.input_file, self.output_file):
            dir_path = os.path.dirname(path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
        if not os.path.exists(self.input_file):
            with open(self.input_file, "w") as f:
                f.write("")

    async def _poll_loop(self) -> None:
        while self._running:
            commands = self._read_commands()
            for cmd in commands:
                if cmd:
                    await self._handle_command(cmd)
            await asyncio.sleep(self.poll_interval)

    def _read_commands(self) -> list[str]:
        try:
            if not os.path.exists(self.input_file):
                return []
            with open(self.input_file, encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return []
            with open(self.input_file, "w", encoding="utf-8") as f:
                f.write("")
            return [line.strip() for line in content.split("\n") if line.strip()]
        except Exception as e:
            logger.error(f"[CLI] Failed to read input file: {e}")
            return []

    async def _handle_command(self, text: str) -> None:
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
                self._write_response(message_chain)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    def _write_response(self, message_chain: MessageChain) -> None:
        try:
            text = message_chain.get_plain_text()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] Bot: {text}\n")
        except Exception as e:
            logger.error(f"[CLI] Failed to write output file: {e}")
