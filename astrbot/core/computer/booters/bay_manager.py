"""Manage Bay container lifecycle for zero-config Shipyard Neo integration.

When no Bay endpoint is configured, AstrBot can automatically start a Bay
container using the Docker socket (like BoxliteBooter does for Ship
containers).
"""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from typing import Any

import aiodocker
import aiohttp

from astrbot.api import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BAY_IMAGE = "ghcr.io/astrbotdevs/shipyard-neo-bay:latest"
BAY_CONTAINER_NAME = "astrbot-bay"
BAY_LABEL = "astrbot.bay.managed"
BAY_PORT = 8114
HEALTH_TIMEOUT_S = 60
HEALTH_POLL_INTERVAL_S = 2


class BayContainerManager:
    """Start / reuse / stop a Bay container via Docker Engine API."""

    def __init__(
        self,
        image: str = BAY_IMAGE,
        host_port: int = BAY_PORT,
    ) -> None:
        self._image = image
        self._host_port = host_port
        self._docker: aiodocker.Docker | None = None
        self._container: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ensure_running(self) -> str:
        """Make sure a Bay container is running. Returns the endpoint URL.

        If a container labelled ``astrbot.bay.managed`` already exists
        and is running, it will be reused.  Otherwise a new container is
        created from *self._image*.
        """
        try:
            self._docker = aiodocker.Docker()
        except Exception as exc:
            raise RuntimeError(
                "Failed to connect to Docker daemon. "
                "Ensure Docker is installed and running, or configure "
                "an explicit Bay endpoint instead of auto-start mode."
            ) from exc

        # 1. Look for an existing managed container
        existing = await self._find_managed_container()
        if existing is not None:
            state = existing["State"]
            if state.get("Running"):
                cid = existing["Id"][:12]
                logger.info("[BayManager] Reusing existing Bay container: %s", cid)
                self._container = await self._docker.containers.get(existing["Id"])
                return f"http://127.0.0.1:{self._host_port}"
            else:
                # Container exists but stopped — restart it
                logger.info("[BayManager] Restarting stopped Bay container")
                container = await self._docker.containers.get(existing["Id"])
                await container.start()
                self._container = container
                return f"http://127.0.0.1:{self._host_port}"

        # 2. Pull image if needed
        await self._pull_image_if_needed()

        # 3. Create and start container
        logger.info(
            "[BayManager] Starting Bay container: image=%s, port=%d",
            self._image,
            self._host_port,
        )
        config = {
            "Image": self._image,
            "Labels": {BAY_LABEL: "true"},
            "Env": [
                "BAY_SERVER__HOST=0.0.0.0",
                f"BAY_SERVER__PORT={BAY_PORT}",
                "BAY_DATA_DIR=/app/data",
                # allow_anonymous=false → auto-provisions API key
                "BAY_SECURITY__ALLOW_ANONYMOUS=false",
            ],
            "HostConfig": {
                "PortBindings": {
                    f"{BAY_PORT}/tcp": [{"HostPort": str(self._host_port)}],
                },
                "Binds": [
                    # Bay needs Docker socket to create sandbox containers
                    "/var/run/docker.sock:/var/run/docker.sock",
                ],
                "RestartPolicy": {"Name": "unless-stopped"},
            },
        }
        self._container = await self._docker.containers.create_or_replace(
            BAY_CONTAINER_NAME, config
        )
        await self._container.start()
        logger.info("[BayManager] Bay container started: %s", BAY_CONTAINER_NAME)

        return f"http://127.0.0.1:{self._host_port}"

    async def wait_healthy(self, timeout: int = HEALTH_TIMEOUT_S) -> None:
        """Block until Bay's ``/health`` endpoint returns 200."""
        url = f"http://127.0.0.1:{self._host_port}/health"
        deadline = asyncio.get_event_loop().time() + timeout
        last_error: str = ""

        async with aiohttp.ClientSession() as session:
            while asyncio.get_event_loop().time() < deadline:
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=3)
                    ) as resp:
                        if resp.status == 200:
                            logger.info("[BayManager] Bay is healthy")
                            return
                        last_error = f"HTTP {resp.status}"
                except Exception as exc:
                    last_error = str(exc)

                await asyncio.sleep(HEALTH_POLL_INTERVAL_S)

        raise TimeoutError(
            f"Bay did not become healthy within {timeout}s (last error: {last_error})"
        )

    async def read_credentials(self) -> str:
        """Read auto-provisioned API key from Bay container.

        Bay writes ``credentials.json`` to its data directory when
        ``allow_anonymous=false`` and no explicit API key is set.
        """
        if self._container is None:
            return ""

        try:
            # Read credentials.json from container filesystem
            tar_stream = await self._container.get_archive("/app/data/credentials.json")
            # get_archive returns (tar_data, stat)
            tar_data = tar_stream

            if isinstance(tar_data, dict):
                raw = tar_data.get("data", b"")
            elif isinstance(tar_data, tuple):
                # (stream, stat_info)
                raw = b""
                stream = tar_data[0]
                if hasattr(stream, "read"):
                    raw = await stream.read()
                elif isinstance(stream, bytes):
                    raw = stream
                else:
                    # It might be a chunked response
                    chunks = []
                    async for chunk in stream:
                        chunks.append(chunk)
                    raw = b"".join(chunks)
            else:
                raw = tar_data if isinstance(tar_data, bytes) else b""

            if not raw:
                logger.debug("[BayManager] Empty tar response from container")
                return ""

            tario = io.BytesIO(raw)
            with tarfile.open(fileobj=tario) as tar:
                for member in tar.getmembers():
                    f = tar.extractfile(member)
                    if f:
                        creds = json.loads(f.read().decode("utf-8"))
                        api_key = creds.get("api_key", "")
                        if api_key:
                            masked = (
                                f"{api_key[:8]}..."
                                if len(api_key) >= 10
                                else "redacted"
                            )
                            logger.info(
                                "[BayManager] Auto-discovered Bay API key: %s",
                                masked,
                            )
                        return api_key
        except Exception as exc:
            logger.debug(
                "[BayManager] Failed to read credentials from container: %s", exc
            )

        return ""

    async def close_client(self) -> None:
        """Close the Docker client without stopping the container.

        The Bay container stays running for reuse by future sessions.
        """
        if self._docker is not None:
            await self._docker.close()
            self._docker = None

    async def stop(self) -> None:
        """Stop and remove the managed Bay container."""
        if self._container is not None:
            try:
                await self._container.stop()
                await self._container.delete(force=True)
                logger.info("[BayManager] Bay container stopped and removed")
            except Exception as exc:
                logger.debug("[BayManager] Error stopping Bay container: %s", exc)
            finally:
                self._container = None

        await self.close_client()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _find_managed_container(self) -> dict | None:
        """Find an existing container with our management label."""
        assert self._docker is not None
        containers = await self._docker.containers.list(
            all=True,
            filters=json.dumps({"label": [f"{BAY_LABEL}=true"]}),
        )
        if containers:
            # Inspect first match to get full state
            return await containers[0].show()
        return None

    async def _pull_image_if_needed(self) -> None:
        """Pull the Bay image if it doesn't exist locally."""
        assert self._docker is not None
        try:
            await self._docker.images.inspect(self._image)
            logger.debug("[BayManager] Image %s already exists", self._image)
        except aiodocker.exceptions.DockerError:
            logger.info("[BayManager] Pulling image %s ...", self._image)
            # Pull with progress logging
            await self._docker.images.pull(self._image)
            logger.info("[BayManager] Image %s pulled successfully", self._image)
