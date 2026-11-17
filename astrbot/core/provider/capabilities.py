"""Provider capabilities shared by input processing and agent runtimes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.provider import Provider


def supports_modality(provider: Provider, modality: str) -> bool:
    """Check declared model capabilities, including the legacy empty-list setting.

    Args:
        provider: Model whose declared capabilities should be inspected.
        modality: Required input modality, such as image.

    Returns:
        Whether the model declares support or uses the legacy unrestricted list.
    """
    modalities = provider.provider_config.get("modalities", None)
    if modalities == []:
        return True  # Empty list from migration is treated as unconfigured for backward compatibility
    return isinstance(modalities, list) and modality in modalities
