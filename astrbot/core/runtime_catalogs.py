"""Runtime-owned catalogs for dynamically declared AstrBot capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field

from astrbot.core.platform.catalog import PlatformCatalog
from astrbot.core.provider.catalog import ProviderCatalog
from astrbot.core.skills.builtin_skill_catalog import BuiltinSkillCatalog
from astrbot.core.star.star import PluginRegistry
from astrbot.core.star.star_handler import HandlerRegistry
from astrbot.core.tools.function_tool_manager import FunctionToolManager


@dataclass(slots=True)
class RuntimeCatalogs:
    """Mutable registrations scoped to one application runtime.

    Decorators attach declarations to classes and functions.  Discovery owners
    materialize those declarations into this object after importing a module.
    No field is shared through module-level mutable state.
    """

    providers: ProviderCatalog = field(default_factory=ProviderCatalog)
    platforms: PlatformCatalog = field(default_factory=PlatformCatalog)
    plugins: PluginRegistry = field(default_factory=PluginRegistry)
    tools: FunctionToolManager = field(default_factory=FunctionToolManager)
    builtin_skills: BuiltinSkillCatalog = field(default_factory=BuiltinSkillCatalog)
    handlers: HandlerRegistry = field(init=False)

    def __post_init__(self) -> None:
        self.handlers = HandlerRegistry(self.plugins)
        self.tools.bind_plugin_lookup(self.plugins)
