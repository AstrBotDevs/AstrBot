"""
ACP integration tests.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from astrbot._internal.protocols.acp.client import AstrbotAcpClient


class TestAstrbotAcpClient:
    """Test suite for ACP client."""

    @pytest.fixture
    def acp_client(self) -> AstrbotAcpClient:
        """Create an ACP client instance."""
        return AstrbotAcpClient()

    def test_acp_client_initial_state(self, acp_client: AstrbotAcpClient) -> None:
        """Test ACP client initial state."""
        assert acp_client.connected is False
        assert acp_client._reader is None
        assert acp_client._writer is None

    @pytest.mark.asyncio
    async def test_acp_client_connect_to_tcp_server(self) -> None:
        """Test ACP client can connect to a TCP server."""
        # Create a simple echo server
        async def echo_handler(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                while True:
                    data = await reader.read(4096)
                    if not data:
                        break
                    # Echo back the same data
                    writer.write(data)
                    await writer.drain()
            except Exception:
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        # Start server
        server = await asyncio.start_server(echo_handler, host="127.0.0.1", port=0)
        addr = server.sockets[0].getsockname()
        port = addr[1]

        try:
            # Connect client
            client = AstrbotAcpClient()
            await client.connect_to_server(host="127.0.0.1", port=port)

            assert client.connected is True
            assert client._reader is not None
            assert client._writer is not None

            await client.shutdown()
        finally:
            server.close()
            await server.wait_closed()

    @pytest.mark.asyncio
    async def test_acp_client_connect_to_unix_socket(self) -> None:
        """Test ACP client can connect to a Unix socket server."""
        client = AstrbotAcpClient()

        # Create temp socket path
        with tempfile.TemporaryDirectory() as tmpdir:
            socket_path = os.path.join(tmpdir, "test_acp.sock")

            # Create a simple echo server
            async def echo_handler(
                reader: asyncio.StreamReader, writer: asyncio.StreamWriter
            ) -> None:
                try:
                    while True:
                        data = await reader.read(4096)
                        if not data:
                            break
                        writer.write(data)
                        await writer.drain()
                except Exception:
                    pass
                finally:
                    writer.close()
                    await writer.wait_closed()

            # Start server using loop.create_unix_server
            loop = asyncio.get_running_loop()
            server = await loop.create_unix_server(echo_handler, path=socket_path)

            try:
                # Connect client
                await client.connect_to_unix_socket(socket_path)

                assert client.connected is True
                assert client._reader is not None
                assert client._writer is not None

                await client.shutdown()
            finally:
                server.close()
                await server.wait_closed()
