"""Session-scoped storage for incoming platform attachments."""

import asyncio
import shutil
import uuid
from pathlib import Path

from astrbot.core.message.components import (
    BaseMessageComponent,
    Image,
    Node,
    Nodes,
    Reply,
)
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
from astrbot.core.workspace import normalize_umo_for_workspace


def platform_files_root(umo: str | None = None) -> Path:
    """Return the attachment root, optionally restricted to one session.

    Args:
        umo: Final unified message origin, or None for all platform attachments.

    Returns:
        Absolute attachment directory using the workspace naming convention.

    Raises:
        ValueError: If the normalized session name targets a parent directory.
    """
    root = Path(get_astrbot_temp_path()) / "platform_files"
    if umo is not None:
        name = normalize_umo_for_workspace(umo)
        if name in {".", ".."}:
            raise ValueError("Invalid platform attachment session name.")
        root /= name
    return root.resolve(strict=False)


async def retain_platform_file(path: str, umo: str) -> str:
    """Copy an incoming attachment into its final session directory.

    Args:
        path: Existing local attachment, possibly owned by an adapter or cache.
        umo: Final unified message origin after session isolation is applied.

    Returns:
        Absolute retained path. Already localized attachments keep their path.

    Raises:
        OSError: If the source cannot be read or the destination cannot be written.
    """
    source = Path(path).resolve(strict=True)
    root = platform_files_root(umo)
    if source.is_relative_to(root):
        return str(source)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{uuid.uuid4().hex}{source.suffix[:20]}"
    copy_task = asyncio.create_task(
        asyncio.to_thread(shutil.copyfile, source, destination)
    )
    try:
        # Do not move shared adapter caches or files owned by external platforms.
        await asyncio.shield(copy_task)
    except asyncio.CancelledError:
        # A worker thread cannot be cancelled; finish it before deleting its output.
        try:
            await copy_task
        finally:
            destination.unlink(missing_ok=True)
        raise
    except OSError:
        destination.unlink(missing_ok=True)
        raise
    return str(destination)


def update_platform_image_path(
    image: Image, path: str, message_chain: list[BaseMessageComponent]
) -> None:
    """Update an image and repeated references directly in the message segments.

    Args:
        image: Image whose original reference has just been localized.
        path: Retained local image path.
        message_chain: Current message, including quoted or forwarded segments.
    """
    source_ref = image.url or image.file
    pending = list(message_chain)
    while pending:
        component = pending.pop()
        if isinstance(component, Reply) and component.chain:
            pending.extend(component.chain)
        elif isinstance(component, Node):
            pending.extend(component.content)
        elif isinstance(component, Nodes):
            pending.extend(component.nodes)
        elif (
            isinstance(component, Image)
            and (component.url or component.file) == source_ref
        ):
            component.file = component.path = component.url = path
    # A newly resolved quote may not belong to the message chain yet.
    image.file = image.path = image.url = path
