import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]

LLM_CONTRACT_NAMES = frozenset(
    {
        "ToolCallsResult",
        "ProviderRequest",
        "TokenUsage",
        "LLMResponse",
        "LLMSource",
        "LLMCitation",
    },
)
MODEL_SDK_MODULE_PREFIXES = ("openai", "anthropic", "google.genai")


def _imports(path: Path) -> set[str]:
    """Return absolute import targets used by one source file.

    ``ast.ImportFrom.module`` intentionally omits the package prefix for
    relative imports. Architecture fitness tests need the resolved target so a
    boundary cannot be bypassed with ``from ..provider import ...``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    relative = path.relative_to(ROOT).with_suffix("")
    package_parts = list(relative.parts[:-1])
    if path.name == "__init__.py":
        package_parts = list(relative.parts)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    modules.add(node.module)
                continue

            parent_count = node.level - 1
            if parent_count > len(package_parts):
                continue
            base_parts = package_parts[: len(package_parts) - parent_count]
            if node.module:
                base_parts.extend(node.module.split("."))
            if base_parts:
                modules.add(".".join(base_parts))
    return modules


def _is_module_or_child(module: str, parent: str) -> bool:
    return module == parent or module.startswith(f"{parent}.")


class _SyncConfigSaveInAsyncFunctionVisitor(ast.NodeVisitor):
    """Collect direct synchronous config saves from async function bodies."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Attribute) and node.func.attr == "save_config":
            self.calls.append((node.lineno, node.col_offset))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        # Each async function is visited independently by the outer visitor.
        return

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        # A nested synchronous function body does not execute in the async scope.
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
        # A lambda body likewise belongs to its own synchronous scope.
        return


class _AsyncSaveConfigFitnessVisitor(ast.NodeVisitor):
    """Find synchronous config persistence calls in every async function."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        body_visitor = _SyncConfigSaveInAsyncFunctionVisitor()
        for statement in node.body:
            body_visitor.visit(statement)
        self.calls.extend(body_visitor.calls)

        # Continue through nested scopes so nested async functions are checked too.
        self.generic_visit(node)


def _sync_config_saves_in_async_functions(tree: ast.AST) -> list[tuple[int, int]]:
    visitor = _AsyncSaveConfigFitnessVisitor()
    visitor.visit(tree)
    return visitor.calls


def test_import_boundaries_exclude_generated_files() -> None:
    for path in (ROOT / "astrbot").rglob("*.py"):
        if "generated" in path.parts:
            continue
        modules = _imports(path)
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("astrbot/api/"):
            assert not any(module.startswith("astrbot.dashboard") for module in modules)
            assert not any(
                ".platform.sources." in module or ".provider.sources." in module
                for module in modules
            )
        if relative.startswith("astrbot/core/"):
            assert not any(
                module == "astrbot.api" or module.startswith("astrbot.api.")
                for module in modules
            )
        if (
            relative.startswith("astrbot/core/")
            and "/platform/sources/" not in relative
            and "/provider/sources/" not in relative
        ):
            assert not any(
                ".platform.sources." in module or ".provider.sources." in module
                for module in modules
            )
        if relative.startswith("astrbot/builtin_stars/"):
            assert not any(
                ".platform.sources." in module or ".provider.sources." in module
                for module in modules
            )


def test_builtin_stars_may_depend_on_the_plugin_sdk() -> None:
    imports = _imports(ROOT / "astrbot" / "builtin_stars" / "astrbot" / "main.py")
    assert "astrbot.api" in imports


def test_import_scanner_resolves_relative_imports() -> None:
    imports = _imports(ROOT / "astrbot" / "core" / "agent" / "runners" / "base.py")

    assert "astrbot.core.agent.llm_types" in imports


def test_agent_runtime_does_not_import_provider_implementation_layers() -> None:
    """Agent code owns LLM contracts and cannot depend on provider internals."""
    agent_runtime_paths = [
        *(ROOT / "astrbot" / "core" / "agent").rglob("*.py"),
        ROOT / "astrbot" / "core" / "astr_main_agent.py",
    ]
    for path in agent_runtime_paths:
        modules = _imports(path)
        assert not any(
            _is_module_or_child(module, "astrbot.core.provider") for module in modules
        ), path.relative_to(ROOT)


def test_llm_contracts_are_owned_by_agent_without_provider_re_exports() -> None:
    """The LLM request/response contract has one agent-owned home."""
    contracts = importlib.import_module("astrbot.core.agent.llm_types")
    provider_entities = importlib.import_module("astrbot.core.provider.entities")

    for name in LLM_CONTRACT_NAMES:
        contract = getattr(contracts, name)
        assert contract.__module__ == "astrbot.core.agent.llm_types"
        assert not hasattr(provider_entities, name), name


def test_llm_contract_modules_do_not_import_model_sdks() -> None:
    """Shared contracts must stay independent from adapter SDK type objects."""
    for relative in (
        "astrbot/core/agent/llm_types.py",
        "astrbot/core/provider/entities.py",
    ):
        modules = _imports(ROOT / relative)
        assert not any(
            _is_module_or_child(module, prefix)
            for module in modules
            for prefix in MODEL_SDK_MODULE_PREFIXES
        ), relative


def test_importing_llm_contract_modules_does_not_load_model_sdks(
    tmp_path: Path,
) -> None:
    """Contract imports remain SDK-free in a fresh Python process."""
    environment = {
        **os.environ,
        "ASTRBOT_ROOT": str(tmp_path / "runtime-root"),
    }
    code = f"""
import importlib
import sys

for module in (
    "astrbot.core.agent.llm_types",
    "astrbot.core.provider.entities",
):
    importlib.import_module(module)

prefixes = {MODEL_SDK_MODULE_PREFIXES!r}
loaded = [
    module
    for module in sys.modules
    if any(module == prefix or module.startswith(f"{{prefix}}.") for prefix in prefixes)
]
assert not loaded, loaded
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_runtime_entry_points_use_the_shared_application_runner() -> None:
    """Both process entry points must delegate runtime construction centrally."""
    main_path = ROOT / "main.py"
    cli_run_path = ROOT / "astrbot" / "cli" / "commands" / "cmd_run.py"

    for path in (main_path, cli_run_path):
        modules = _imports(path)
        assert "astrbot.application" in modules
        assert not any(module.startswith("astrbot.core") for module in modules)
        assert "run_application" in path.read_text(encoding="utf-8")


def test_core_execution_context_replaces_legacy_star_context_module() -> None:
    """Core execution dependencies must not remain behind a plugin SDK alias."""
    execution_context = ROOT / "astrbot" / "core" / "execution_context.py"
    legacy_context = ROOT / "astrbot" / "core" / "star" / "context.py"

    assert execution_context.exists()
    assert not legacy_context.exists()

    for path in (ROOT / "astrbot" / "core").rglob("*.py"):
        assert "astrbot.core.star.context" not in _imports(path), path.relative_to(ROOT)


def test_plugin_sdk_has_no_legacy_context_or_service_locator_aliases() -> None:
    """Plugins receive capabilities, never the legacy broad context surface."""
    plugin_sdk = importlib.import_module("astrbot.api.star")

    assert plugin_sdk.PluginContext is not None
    assert not hasattr(plugin_sdk, "Context")
    assert not hasattr(plugin_sdk, "StarTools")
    assert not (ROOT / "astrbot" / "core" / "star" / "star_tools.py").exists()


def test_webchat_runtime_state_is_not_owned_by_adapter_modules() -> None:
    """WebChat queues are runtime services, never adapter import singletons."""
    legacy_queue_module = (
        ROOT
        / "astrbot"
        / "core"
        / "platform"
        / "sources"
        / "webchat"
        / "webchat_queue_mgr.py"
    )
    assert not legacy_queue_module.exists()

    queue_source = (
        ROOT / "astrbot" / "core" / "webchat" / "queue_manager.py"
    ).read_text(encoding="utf-8")
    assert "webchat_queue_mgr" not in queue_source
    assert "= WebChatQueueManager()" not in queue_source


def test_agent_follow_up_state_is_runtime_owned() -> None:
    """Active Agent runs cannot live in a module-level follow-up registry."""
    legacy_module = (
        ROOT / "astrbot" / "core" / "pipeline" / "process_stage" / "follow_up.py"
    )
    coordinator_source = (
        ROOT / "astrbot" / "core" / "agent" / "follow_up.py"
    ).read_text(encoding="utf-8")

    assert not legacy_module.exists()
    assert "_ACTIVE_AGENT_RUNNERS" not in coordinator_source
    assert "_FOLLOW_UP_ORDER_STATE" not in coordinator_source


def test_function_tool_catalog_is_not_owned_by_provider_modules() -> None:
    """Tool discovery is a core capability, not a provider registration path."""
    legacy_module = ROOT / "astrbot" / "core" / "provider" / "func_tool_manager.py"
    catalog_module = ROOT / "astrbot" / "core" / "tools" / "function_tool_manager.py"

    assert not legacy_module.exists()
    assert catalog_module.exists()

    for path in (ROOT / "astrbot").rglob("*.py"):
        assert not any(
            _is_module_or_child(module, "astrbot.core.provider.func_tool_manager")
            for module in _imports(path)
        ), path.relative_to(ROOT)


def test_request_llm_has_no_legacy_function_tool_manager_parameter() -> None:
    """Event LLM requests expose the current ToolSet-only API."""
    event_module = ROOT / "astrbot" / "core" / "platform" / "astr_message_event.py"
    tree = ast.parse(event_module.read_text(encoding="utf-8"))

    request_llm = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "request_llm"
    )
    parameter_names = [arg.arg for arg in request_llm.args.args]
    assert "func_tool_manager" not in parameter_names
    assert "tool_set" in parameter_names


def test_totp_runtime_state_has_no_module_singleton() -> None:
    """TOTP replay and rotation state belongs to one RuntimeServices instance."""
    totp_path = ROOT / "astrbot" / "core" / "utils" / "totp.py"
    tree = ast.parse(totp_path.read_text(encoding="utf-8"))
    forbidden_names = {
        "_last_totp_timecode",
        "_totp_replay_lock",
        "_totp_pending_secret",
        "_totp_rotation_verified",
    }

    assigned_names = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else (node.target,))
        if isinstance(target, ast.Name)
    }
    assert not forbidden_names & assigned_names

    runtime_services = (ROOT / "astrbot" / "core" / "runtime_services.py").read_text(
        encoding="utf-8"
    )
    assert "totp_runtime_state: TotpRuntimeState" in runtime_services
    assert "totp_runtime_state = TotpRuntimeState()" in runtime_services
    assert "totp_runtime_state=totp_runtime_state" in runtime_services


def test_runtime_mutable_registries_are_not_module_singletons() -> None:
    """Runtime registries may be declared in modules but not constructed there."""
    registry_types = {
        "astrbot/core/runtime_catalogs.py": {"RuntimeCatalogs"},
        "astrbot/core/provider/catalog.py": {"ProviderCatalog"},
        "astrbot/core/platform/catalog.py": {"PlatformCatalog"},
        "astrbot/core/star/star.py": {"PluginRegistry"},
        "astrbot/core/star/star_handler.py": {"HandlerRegistry"},
        "astrbot/core/agent/follow_up.py": {"FollowUpCoordinator"},
        "astrbot/core/utils/active_event_registry.py": {"ActiveEventRegistry"},
        "astrbot/core/utils/llm_metadata.py": {"LLMMetadataCatalog"},
        "astrbot/core/utils/session_lock.py": {"SessionLockManager"},
        "astrbot/core/tools/function_tool_manager.py": {"FunctionToolManager"},
    }

    for relative, forbidden_constructors in registry_types.items():
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in tree.body:
            value = None
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
            if not isinstance(value, ast.Call):
                continue
            constructor = value.func
            if isinstance(constructor, ast.Name):
                assert constructor.id not in forbidden_constructors, relative


def test_dashboard_webchat_services_do_not_import_platform_source_runtime() -> None:
    """Dashboard transports use core WebChat primitives, not adapter internals."""
    for filename in (
        "chat_service.py",
        "live_chat_service.py",
        "open_api_service.py",
    ):
        modules = _imports(ROOT / "astrbot" / "dashboard" / "services" / filename)
        assert not any(
            _is_module_or_child(module, "astrbot.core.platform.sources.webchat")
            for module in modules
        ), filename


def test_dashboard_layers_do_not_import_concrete_adapter_sources() -> None:
    """Dashboard API and services must consume runtime ports and catalogs only."""
    dashboard_root = ROOT / "astrbot" / "dashboard"
    for section in ("api", "services"):
        for path in (dashboard_root / section).rglob("*.py"):
            modules = _imports(path)
            assert not any(
                _is_module_or_child(module, "astrbot.core.platform.sources")
                or _is_module_or_child(module, "astrbot.core.provider.sources")
                for module in modules
            ), path.relative_to(ROOT)


def test_async_functions_must_use_async_config_persistence() -> None:
    """Async paths must preserve config write revisions through save_config_async."""
    violations: list[str] = []

    for path in (ROOT / "astrbot").rglob("*.py"):
        if "generated" in path.parts:
            continue
        calls = _sync_config_saves_in_async_functions(
            ast.parse(path.read_text(encoding="utf-8"))
        )
        relative = path.relative_to(ROOT).as_posix()
        violations.extend(
            f"{relative}:{line}:{column + 1} calls .save_config() in async def"
            for line, column in calls
        )

    assert not violations, "\n".join(violations)


def test_async_config_persistence_fitness_visits_nested_async_functions() -> None:
    tree = ast.parse(
        """\
async def outer(config):
    config.save_config_async()
    config.save_config()
    def sync_helper():
        config.save_config()
        async def nested(config):
            config.save_config()
    async def sibling(config):
        config.save_config()
"""
    )

    assert _sync_config_saves_in_async_functions(tree) == [(3, 4), (7, 12), (9, 8)]


def _runtime_imports(path: Path) -> set[str]:
    """Return absolute imports that execute at runtime, skipping TYPE_CHECKING."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    relative = path.relative_to(ROOT).with_suffix("")
    package_parts = list(relative.parts[:-1])
    if path.name == "__init__.py":
        package_parts = list(relative.parts)

    def is_type_checking(test: ast.AST) -> bool:
        return isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"

    class Visitor(ast.NodeVisitor):
        def visit_If(self, node: ast.If) -> None:  # noqa: N802
            if is_type_checking(node.test):
                for statement in node.orelse:
                    self.visit(statement)
                return
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
            modules.update(alias.name for alias in node.names)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
            if node.level == 0:
                if node.module:
                    modules.add(node.module)
                return
            parent_count = node.level - 1
            if parent_count > len(package_parts):
                return
            base_parts = package_parts[: len(package_parts) - parent_count]
            if node.module:
                base_parts.extend(node.module.split("."))
            if base_parts:
                modules.add(".".join(base_parts))

    Visitor().visit(tree)
    return modules


def test_builtin_commands_do_not_import_astrbot_core_at_runtime() -> None:
    root = ROOT / "astrbot" / "builtin_stars" / "builtin_commands"
    violations: list[str] = []
    for path in root.rglob("*.py"):
        for module in _runtime_imports(path):
            if module == "astrbot.core" or module.startswith("astrbot.core."):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")
    assert not violations, "\n".join(violations)


def test_public_sdk_and_core_leaf_imports_remain_available() -> None:
    sdk = importlib.import_module("astrbot.api")
    dashboard_sdk = importlib.import_module("astrbot.api.dashboard")
    leaf = importlib.import_module("astrbot.core.platform.astr_message_event")

    assert sdk.FunctionTool is not None
    assert dashboard_sdk.DashboardJsonAction is not None
    assert leaf.AstrMessageEvent is not None
