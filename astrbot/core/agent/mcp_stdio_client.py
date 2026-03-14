from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, TextIO

import anyio
import anyio.lowlevel
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from anyio.streams.text import TextReceiveStream
from mcp.client.stdio import (
    PROCESS_TERMINATION_TIMEOUT,
    _create_platform_compatible_process,
    _get_executable_command,
    _terminate_process_tree,
    get_default_environment,
)
from mcp.shared.message import SessionMessage

from astrbot import logger

if TYPE_CHECKING:
    import mcp


def _normalize_stdout_line(line: str) -> str:
    return line.rstrip("\r")


def _should_ignore_stdout_line(line: str) -> bool:
    stripped = _normalize_stdout_line(line).strip()
    if not stripped:
        return True

    # JSON-RPC messages are serialized as JSON objects. Wrapper banners from
    # tools such as npm/pnpm/yarn should not abort the session.
    return not stripped.startswith("{")


@asynccontextmanager
async def tolerant_stdio_client(
    server: mcp.StdioServerParameters,
    errlog: TextIO = sys.stderr,
):
    """A stdio MCP transport that ignores obvious non-protocol stdout noise."""

    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]

    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    try:
        command = _get_executable_command(server.command)
        process = await _create_platform_compatible_process(
            command=command,
            args=server.args,
            env=(
                {**get_default_environment(), **server.env}
                if server.env is not None
                else get_default_environment()
            ),
            errlog=errlog,
            cwd=server.cwd,
        )
    except OSError:
        await read_stream.aclose()
        await write_stream.aclose()
        await read_stream_writer.aclose()
        await write_stream_reader.aclose()
        raise

    async def stdout_reader():
        assert process.stdout, "Opened process is missing stdout"

        try:
            async with read_stream_writer:
                buffer = ""
                async for chunk in TextReceiveStream(
                    process.stdout,
                    encoding=server.encoding,
                    errors=server.encoding_error_handler,
                ):
                    lines = (buffer + chunk).split("\n")
                    buffer = lines.pop()

                    for raw_line in lines:
                        line = _normalize_stdout_line(raw_line)
                        if _should_ignore_stdout_line(line):
                            if line.strip():
                                logger.debug(
                                    "Ignoring non-JSON stdout line from MCP stdio server: %s",
                                    line.strip(),
                                )
                            continue

                        try:
                            message = types.JSONRPCMessage.model_validate_json(
                                line.strip()
                            )
                        except Exception as exc:  # pragma: no cover
                            logging.getLogger("mcp.client.stdio").exception(
                                "Failed to parse JSONRPC message from server"
                            )
                            await read_stream_writer.send(exc)
                            continue

                        await read_stream_writer.send(SessionMessage(message))
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async def stdin_writer():
        assert process.stdin, "Opened process is missing stdin"

        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    payload = session_message.message.model_dump_json(
                        by_alias=True,
                        exclude_none=True,
                    )
                    await process.stdin.send(
                        (payload + "\n").encode(
                            encoding=server.encoding,
                            errors=server.encoding_error_handler,
                        )
                    )
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async with (
        anyio.create_task_group() as tg,
        process,
    ):
        tg.start_soon(stdout_reader)
        tg.start_soon(stdin_writer)
        try:
            yield read_stream, write_stream
        finally:
            if process.stdin:  # pragma: no branch
                try:
                    await process.stdin.aclose()
                except Exception:  # pragma: no cover
                    pass

            try:
                with anyio.fail_after(PROCESS_TERMINATION_TIMEOUT):
                    await process.wait()
            except TimeoutError:
                await _terminate_process_tree(process)
            except ProcessLookupError:  # pragma: no cover
                pass

            await read_stream.aclose()
            await write_stream.aclose()
            await read_stream_writer.aclose()
            await write_stream_reader.aclose()
