"""SDK bridge package public exports."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .capability_bridge import CoreCapabilityBridge
    from .event_converter import EventConverter
    from .plugin_bridge import SdkPluginBridge
    from .trigger_converter import TriggerConverter
else:
    CoreCapabilityBridge: Any
    EventConverter: Any
    SdkPluginBridge: Any
    TriggerConverter: Any

__all__ = [
    "CoreCapabilityBridge",
    "EventConverter",
    "SdkPluginBridge",
    "TriggerConverter",
]


def __getattr__(name: str) -> Any:
    if name == "CoreCapabilityBridge":
        return import_module(".capability_bridge", __name__).CoreCapabilityBridge
    if name == "EventConverter":
        return import_module(".event_converter", __name__).EventConverter
    if name == "SdkPluginBridge":
        return import_module(".plugin_bridge", __name__).SdkPluginBridge
    if name == "TriggerConverter":
        return import_module(".trigger_converter", __name__).TriggerConverter
    raise AttributeError(name)
