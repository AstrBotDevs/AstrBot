from __future__ import annotations

import asyncio
import contextlib
import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import HostUnavailable, InvalidRequest, RemoteHostError
from ..protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    ErrorFrame,
    RequestFrame,
    ResponseFrame,
    decode_frame,
    encode_frame,
)
from .stdio_server import _SUPPORTED_FEATURES, StdioPluginServer
from .transport import StreamTransport

DEFAULT_UDS_RECONNECT_GRACE = 30.0


@dataclass(frozen=True, slots=True)
class ExternalCredential:
    """Credential payload issued by the Host for external UDS attachment."""

    plugin_id: str
    credential: str
    socket_path: str


def load_external_credential(path: Path | str) -> ExternalCredential:
    """Load an external UDS credential file, enforcing restrictive permissions.

    Args:
        path: Path to the JSON credential file created by the Host.

    Returns:
        Parsed ExternalCredential.

    Raises:
        InvalidRequest: The file is missing, is a symlink, has permissive Unix
            permissions, or contains invalid JSON.
    """
    cred_path = Path(path)
    try:
        file_stat = os.lstat(cred_path)
    except OSError as exc:
        raise InvalidRequest(f"cannot stat credential file: {exc}") from exc
    if stat.S_ISLNK(file_stat.st_mode):
        raise InvalidRequest("external credential file must not be a symlink")
    if os.name == "posix" and (stat.S_IMODE(file_stat.st_mode) & 0o077) != 0:
        raise InvalidRequest("external credential file must have 0600 permissions")

    try:
        raw = cred_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise InvalidRequest(f"invalid external credential JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidRequest("external credential payload must be a JSON object")
    plugin_id = data.get("plugin_id")
    credential = data.get("credential")
    socket_path = data.get("socket_path")
    if (
        not isinstance(plugin_id, str)
        or not plugin_id
        or not isinstance(credential, str)
        or not credential
        or not isinstance(socket_path, str)
        or not socket_path
    ):
        raise InvalidRequest(
            "external credential must define plugin_id, credential, and socket_path"
        )
    return ExternalCredential(
        plugin_id=plugin_id,
        credential=credential,
        socket_path=socket_path,
    )


async def _uds_attach(
    credential: ExternalCredential,
    *,
    resume_token: str | None = None,
) -> tuple[StreamTransport, dict[str, Any]]:
    """Open a Unix domain socket to the Host and complete attach / attach.resume."""
    try:
        reader, writer = await asyncio.open_unix_connection(
            credential.socket_path,
            limit=MAX_FRAME_BYTES + 1,
        )
    except OSError as exc:
        raise HostUnavailable(f"UDS connect failed: {exc}") from exc

    transport = StreamTransport(reader, writer)
    attach_payload: dict[str, Any] = {
        "plugin_id": credential.plugin_id,
        "credential": credential.credential,
        "protocol_version": PROTOCOL_VERSION,
        "features": list(_SUPPORTED_FEATURES),
    }
    method = "attach.resume" if resume_token is not None else "attach"
    params: dict[str, Any] = (
        {"attach": attach_payload, "resume_token": resume_token}
        if resume_token is not None
        else attach_payload
    )
    req_id = "worker:attach"
    try:
        await transport.write(
            encode_frame(RequestFrame(id=req_id, method=method, params=params))
        )
        line = await transport.read()
        if line is None:
            raise HostUnavailable("EOF before attach response")
        frame = decode_frame(line)
        if isinstance(frame, ErrorFrame):
            raise RemoteHostError(frame.code, frame.message)
        if not isinstance(frame, ResponseFrame) or frame.id != req_id:
            raise InvalidRequest("unexpected frame before attach response")
        if not isinstance(frame.result, dict):
            raise InvalidRequest("attach response must be an object")
        return transport, frame.result
    except Exception:
        with contextlib.suppress(Exception):
            await transport.close()
        raise


async def serve_uds_plugin(
    plugin_root: Path,
    credential_file: Path | str,
    *,
    legacy: bool = False,
    reconnect_grace: float = DEFAULT_UDS_RECONNECT_GRACE,
) -> None:
    """Connect to the Host Unix domain socket and serve one plugin externally.

    Preserves resumable stream state across transient Host disconnects within
    ``reconnect_grace`` seconds using ``attach.resume``.

    Args:
        plugin_root: Plugin repository root.
        credential_file: Host-issued JSON credential file (``0600``).
        legacy: Load the plugin through the legacy compat layer.
        reconnect_grace: Maximum seconds to attempt ``attach.resume`` after an
            unexpected disconnect.
    """
    credential = load_external_credential(credential_file)
    transport, attached = await _uds_attach(credential)
    resume_token = attached.get("resume_token")
    host_epoch = attached.get("host_epoch")
    server = StdioPluginServer(plugin_root, legacy=legacy, transport=transport)

    try:
        while True:
            await server.serve(stop_on_exit=False)
            with contextlib.suppress(Exception):
                await transport.close()
            if server._closing or not resume_token or reconnect_grace <= 0:
                break

            deadline = time.monotonic() + reconnect_grace
            delay = 0.05
            reattached = False
            while time.monotonic() < deadline:
                with contextlib.suppress(OSError, HostUnavailable):
                    new_transport, new_attached = await _uds_attach(
                        credential,
                        resume_token=str(resume_token),
                    )
                    if new_attached.get("host_epoch") != host_epoch:
                        with contextlib.suppress(Exception):
                            await new_transport.close()
                        break
                    transport = new_transport
                    resume_token = new_attached.get("resume_token") or resume_token
                    server.rebind_transport(transport)
                    for replay_frame in server.stream_replay_frames():
                        await server._send(replay_frame)
                    reattached = True
                    break
                await asyncio.sleep(min(delay, max(0.01, deadline - time.monotonic())))
                delay = min(delay * 2.0, 0.5)

            if not reattached:
                break
    finally:
        await server._stop_plugin()
        await server._peer.close()
        with contextlib.suppress(Exception):
            await transport.close()
