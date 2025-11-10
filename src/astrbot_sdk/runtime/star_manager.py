import yaml
import importlib
import functools
from pathlib import Path
from loguru import logger
from .stars.registry import star_handlers_registry, star_map, star_registry
from ..runtime.api.context import Context
from ..api.star.star import StarMetadata


class StarManager:
    def __init__(self, context: Context) -> None:
        self.context = context

    def discover_star(self, root_dir: Path | None = None):
        """
        Discover star via plugin.yaml.

        Args:
            root_dir (Path | None): The root directory to search for plugin.yaml. Defaults to None, which means the current working directory.
        """
        if root_dir is None:
            root_dir = Path.cwd().relative_to(Path.cwd())
        else:
            root_dir = Path.cwd().joinpath(root_dir).resolve()
        path = root_dir / "plugin.yaml"
        if not path.exists():
            logger.warning("No plugin.yaml found in the current directory.")
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Try to find logo.png
        logo_path = None
        if Path(root_dir / "logo.png").exists():
            logo_path = str(root_dir / "logo.png")

        # Validate required fields
        star_name = data.get("name")
        if not star_name:
            logger.error("Plugin name is required in plugin.yaml.")
            return []

        # Load components
        components = data.get("components", [])
        full_name_list = []
        for comp in components:
            class_ = comp.get("class", "")
            print(f"Loading component: {class_}")
            if not class_:
                logger.warning(f"Component without class found: {comp}")
                continue
            module_path, class_name = class_.rsplit(":", 1)
            if not module_path:
                logger.warning(f"Invalid component without module: {comp}")
                continue
            # dynamically register the component
            try:
                # we need edit the module path to be relative to the root_dir
                root_dir_dot = str(root_dir).replace("/", ".").lstrip(".")
                if root_dir_dot:
                    module_path = f"{root_dir_dot}.{module_path}"
                module_type = importlib.import_module(module_path)
                logger.info(f"Successfully loaded component module: {module_path}")
                component_cls = getattr(module_type, class_name)
                # Instantiate the component with context
                ccls = component_cls(self.context)

                # add to full name list
                for h in star_handlers_registry._handlers:
                    if h.handler_full_name.startswith(f"{class_}."):
                        # bind the instance
                        h.handler = functools.partial(h.handler, ccls)
                        full_name_list.append(h.handler_full_name)

            except Exception as e:
                logger.error(f"Failed to load component {module_path}: {e}")
                continue

        # Register the star metadata
        star_module_path = f"{star_name}.main"
        star_metadata = StarMetadata(
            name=data.get("name"),
            author=data.get("author"),
            desc=data.get("desc"),
            version=data.get("version"),
            repo=data.get("repo"),
            module_path=star_module_path,
            root_dir_name=root_dir.name,
            reserved=False,
            star_handler_full_names=full_name_list,
            display_name=data.get("display_name"),
            logo_path=logo_path,
        )
        star_map[star_module_path] = star_metadata
        star_registry.append(star_metadata)

        logger.info(f"Discovered {len(star_handlers_registry)} star handlers:")
        for md in star_handlers_registry:
            logger.info(
                f" - {md.handler_full_name} with {len(md.event_filters)} filters"
            )
