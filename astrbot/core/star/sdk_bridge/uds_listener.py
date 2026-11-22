"""Host-side Unix Domain Socket listener for externally managed SDK Workers."""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import os
import re
import secrets
import shutil
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from astrbot_sdk.protocol import (
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    ErrorFrame,
    RequestFrame,
    ResponseFrame,
    decode_frame,
    encode_frame,
)
from astrbot_sdk.runtime.transport import FrameTransport, StreamTransport

from astrbot.core import logger


class ExternalUDSListener:
    """Authenticate and accept external Worker UDS connections (`attach` / `attach.resume`).

    The listener never spawns or kills external OS processes; stopping a plugin
    revokes its credential and detaches only its protocol session.
    """

    def __init__(self, socket_dir: Path | None = None) -> None:
        self._owns_dir = socket_dir is None
        if socket_dir is None:
            # Use /tmp with a short directory name so the UDS path stays under
            # macOS's 104-byte sockaddr_un limit.
            self._dir = Path(tempfile.mkdtemp(prefix="ab_uds_", dir="/tmp"))
        else:
            self._dir = Path(socket_dir)
            self._dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(self._dir, 0o700)
        self.socket_path = self._dir / "h.sock"
        if len(str(self.socket_path).encode("utf-8")) >= 104:
            raise ValueError(
                f"UDS socket path exceeds 103 bytes limit: {self.socket_path}"
            )
        self._host_epoch = uuid.uuid4().hex
        self._server: asyncio.AbstractServer | None = None
        self._slots: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        """Bind the Unix domain socket with owner-only permissions."""
        if self._server is not None:
            return
        if not hasattr(asyncio, "start_unix_server"):
            raise NotImplementedError(
                "Unix domain socket external workers require a POSIX host"
            )
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
            limit=MAX_FRAME_BYTES + 1,
        )
        if os.name == "posix":
            os.chmod(self.socket_path, 0o600)

    async def stop(self) -> None:
        """Close the listener socket and clean up owned temporary directories."""
        server = self._server
        self._server = None
        if server is not None:
            server.close()
            await server.wait_closed()
        if self.socket_path.exists():
            with contextlib.suppress(OSError):
                self.socket_path.unlink()
        if self._owns_dir and self._dir.exists():
            with contextlib.suppress(OSError):
                shutil.rmtree(self._dir)
        self._slots.clear()

    def enroll(
        self,
        plugin_id: str,
        credential_dir: Path,
        *,
        credential: str | None = None,
    ) -> tuple[Path, asyncio.Queue[FrameTransport]]:
        """Issue a `0600` external credential file and transport queue for `plugin_id`.

        Args:
            plugin_id: Expected remote plugin ID.
            credential_dir: Directory receiving `<plugin_id>.credential.json`.
            credential: Optional pre-shared secret; random token generated if omitted.

        Returns:
            Tuple of `(credential_file_path, accepted_transport_queue)`.
        """
        resolved_dir = credential_dir.resolve()
        resolved_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(resolved_dir, 0o700)
        secret = credential or secrets.token_urlsafe(32)
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", plugin_id).strip("._") or "plugin"
        cred_path = resolved_dir / f"{safe_name}.credential.json"
        if cred_path.resolve(strict=False).parent != resolved_dir:
            raise ValueError(f"Invalid credential target path: {cred_path}")
        if cred_path.is_symlink():
            cred_path.unlink()
        payload_text = (
            json.dumps(
                {
                    "plugin_id": plugin_id,
                    "credential": secret,
                    "socket_path": str(self.socket_path),
                },
                indent=2,
            )
            + "\n"
        )
        if os.name == "posix":
            # Create the bootstrap file with 0600 permissions directly so it is
            # never readable under a permissive umask before chmod runs.
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(cred_path, flags, 0o600)
            try:
                os.fchmod(fd, 0o600)
                handle = os.fdopen(fd, "w", encoding="utf-8")
            except BaseException:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise
            with handle:
                handle.write(payload_text)
        else:
            cred_path.write_text(payload_text, encoding="utf-8")

        queue: asyncio.Queue[FrameTransport] = asyncio.Queue()
        self._slots[plugin_id] = {
            "credential": secret,
            "queue": queue,
            "cred_path": cred_path,
            "resume_tokens": set(),
        }
        return cred_path, queue

    def revoke(self, plugin_id: str) -> None:
        """Revoke one external plugin's attach credentials without killing processes."""
        slot = self._slots.pop(plugin_id, None)
        if slot is None:
            return
        cred_path: Path = slot["cred_path"]
        if cred_path.exists() and not cred_path.is_symlink():
            with contextlib.suppress(OSError):
                cred_path.unlink()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        transport = StreamTransport(reader, writer)
        try:
            line = await asyncio.wait_for(transport.read(), timeout=10.0)
            if line is None:
                await transport.close()
                return
            frame = decode_frame(line)
            if not isinstance(frame, RequestFrame) or frame.method not in (
                "attach",
                "attach.resume",
            ):
                await transport.write(
                    encode_frame(
                        ErrorFrame(
                            id=getattr(frame, "id", "protocol"),
                            code="INVALID_REQUEST",
                            message="first UDS frame must be attach or attach.resume",
                        )
                    )
                )
                await transport.close()
                return

            if frame.method == "attach.resume":
                attach_params = frame.params.get("attach") or {}
                resume_token = str(frame.params.get("resume_token") or "")
            else:
                attach_params = frame.params
                resume_token = ""

            if not isinstance(attach_params, Mapping):
                await transport.write(
                    encode_frame(
                        ErrorFrame(
                            id=frame.id,
                            code="INVALID_REQUEST",
                            message="attach params must be an object",
                        )
                    )
                )
                await transport.close()
                return

            plugin_id = str(attach_params.get("plugin_id") or "")
            secret = str(attach_params.get("credential") or "")
            proto_ver = attach_params.get("protocol_version")
            slot = self._slots.get(plugin_id)
            if slot is None or not hmac.compare_digest(secret, slot["credential"]):
                await transport.write(
                    encode_frame(
                        ErrorFrame(
                            id=frame.id,
                            code="CAPABILITY_DENIED",
                            message="invalid UDS attach credentials",
                        )
                    )
                )
                await transport.close()
                return

            if proto_ver != PROTOCOL_VERSION:
                await transport.write(
                    encode_frame(
                        ErrorFrame(
                            id=frame.id,
                            code="INVALID_REQUEST",
                            message="unsupported protocol version",
                        )
                    )
                )
                await transport.close()
                return

            if frame.method == "attach.resume":
                if not resume_token or resume_token not in slot["resume_tokens"]:
                    await transport.write(
                        encode_frame(
                            ErrorFrame(
                                id=frame.id,
                                code="CONFLICT",
                                message="invalid or expired resume_token",
                            )
                        )
                    )
                    await transport.close()
                    return

            new_resume_token = secrets.token_urlsafe(24)
            slot["resume_tokens"].add(new_resume_token)
            await transport.write(
                encode_frame(
                    ResponseFrame(
                        id=frame.id,
                        result={
                            "connection_id": uuid.uuid4().hex,
                            "host_epoch": self._host_epoch,
                            "resume_token": new_resume_token,
                            "features": [
                                "cancel_v1",
                                "capability_update_v1",
                                "direct_service_v1",
                                "dynamic_tools_v1",
                                "external_attach_v1",
                                "live_config_v1",
                                "plugin_service_v1",
                                "resume_stream_v1",
                                "scoped_host_v1",
                            ],
                        },
                    )
                )
            )
            await slot["queue"].put(transport)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"UDS external attach failed: {exc}")
            with contextlib.suppress(Exception):
                await transport.close()
