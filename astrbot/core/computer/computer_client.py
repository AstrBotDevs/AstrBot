import json
import shutil
import uuid
from pathlib import Path

from astrbot.api import logger
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.provider.register import llm_tools
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT, SkillManager
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter
from .sandbox_manager import SandboxManager
from .sandbox_models import SandboxStatus
from .sandbox_provider import SandboxProvider
from .sandbox_registry import SandboxRegistry

local_booter: LocalBooter | None = None
sandbox_registry = SandboxRegistry()
sandbox_manager = SandboxManager(registry=sandbox_registry, providers={})
_MANAGED_SKILLS_FILE = ".astrbot_managed_skills.json"

# Tracks tools registered per provider so core can remove them on unregister.
_provider_tools: dict[str, list[FunctionTool]] = {}


def _sandbox_provider_info(provider_id: str, provider: SandboxProvider) -> dict:
    return {
        "provider_id": provider_id,
        "capabilities": sorted(getattr(provider, "capabilities", set())),
        "tool_names": sorted(getattr(provider, "tool_names", set())),
        "system_prompt": str(getattr(provider, "system_prompt", "") or ""),
    }


def _has_managed_sandboxes_for_provider(provider_id: str) -> bool:
    return any(
        record.get("managed") and record.get("provider") == provider_id
        for record in sandbox_manager.registry.list_sandboxes()
    )


def register_sandbox_provider(
    provider: SandboxProvider,
    *,
    replace: bool = False,
    tools: list[FunctionTool] | None = None,
) -> None:
    """Register a plugin-provided sandbox runtime.

    Args:
        provider: The sandbox provider instance.
        replace: If ``True``, replace an existing provider with the same ID.
        tools: Optional list of provider-specific tools to register with the
            global LLM tool manager. Core will automatically unregister these
            tools when the provider is unregistered.
    """
    if not provider.provider_id:
        raise ValueError("Sandbox provider_id must be a non-empty string.")
    if provider.provider_id in sandbox_manager.providers and not replace:
        raise RuntimeError(
            f"Sandbox provider {provider.provider_id} is already registered"
        )

    # Clean up previous tools when replacing.
    if replace and provider.provider_id in sandbox_manager.providers:
        _unregister_provider_tools(provider.provider_id)

    sandbox_manager.providers[provider.provider_id] = provider

    if tools:
        registered: list[FunctionTool] = []
        for tool in tools:
            tool.sandbox_provider_id = provider.provider_id
            llm_tools.func_list.append(tool)
            registered.append(tool)
        _provider_tools[provider.provider_id] = registered
        logger.info(
            "Sandbox provider %s registered with %d tool(s)",
            provider.provider_id,
            len(registered),
        )
    else:
        logger.info("Sandbox provider %s registered", provider.provider_id)


def unregister_sandbox_provider(provider_id: str, *, force: bool = False) -> None:
    if not force and _has_managed_sandboxes_for_provider(provider_id):
        raise RuntimeError(
            f"Sandbox provider {provider_id} has active managed sandboxes; "
            "destroy them or pass force=True before unregistering."
        )

    if force:
        # Synchronously clear registry and memory state for this provider's
        # sandboxes.  Async destroy_booter is best-effort via background task.
        _cleanup_provider_sandboxes_sync(provider_id)

    _unregister_provider_tools(provider_id)
    sandbox_manager.providers.pop(provider_id, None)


def _unregister_provider_tools(provider_id: str) -> None:
    registered = _provider_tools.pop(provider_id, [])
    for tool in registered:
        llm_tools.remove_func(tool.name)
    from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

    FunctionToolExecutor.clear_runtime_computer_tools_cache(provider_id)
    if registered:
        logger.info(
            "Unregistered %d tool(s) for sandbox provider %s",
            len(registered),
            provider_id,
        )


def _cleanup_provider_sandboxes_sync(provider_id: str) -> None:
    """Synchronous cleanup of a provider's managed sandboxes on unregister.

    Registry records and in-memory state are removed immediately.  If a booter
    is alive and an event loop is running, an async destroy_booter task is
    spawned as a best-effort cleanup.
    """
    import asyncio

    for record in list(sandbox_manager.registry.list_sandboxes()):
        if not record.get("managed") or record.get("provider") != provider_id:
            continue
        sandbox_id = record["sandbox_id"]
        if record.get("retention_policy") == "persistent":
            sandbox_manager.session_booter.pop(sandbox_id, None)
            sandbox_manager.clear_idle_state(sandbox_id)
            sandbox_manager.drop_boot_lock(sandbox_id)
            continue
        booter = sandbox_manager.session_booter.pop(sandbox_id, None)
        sandbox_manager.clear_idle_state(sandbox_id)
        sandbox_manager.registry.delete_sandbox(sandbox_id)
        sandbox_manager.drop_boot_lock(sandbox_id)
        if booter is not None:
            try:
                loop = asyncio.get_running_loop()
                provider = sandbox_manager.providers.get(provider_id)
                if provider is not None:
                    loop.create_task(_safe_destroy_booter(provider, booter, record))
            except RuntimeError:
                pass  # no running event loop
    try:
        sandbox_manager.registry.save()
    except Exception as exc:
        logger.warning(
            "[Computer] Failed to save registry after force-unregister: %s",
            exc,
        )
    from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor

    FunctionToolExecutor.clear_runtime_computer_tools_cache(provider_id)
    logger.info(
        "Force-unregistered sandbox provider %s: sandboxes cleaned up",
        provider_id,
    )


async def cleanup_sandbox_provider(provider_id: str) -> None:
    """Destroy all sandboxes owned by a provider before unregistering it."""
    provider = sandbox_manager.providers.get(provider_id)
    removed = 0
    preserved = 0
    handled_sandbox_ids: set[str] = set()

    def _pop_live_booter(sandbox_id: str):
        booter = sandbox_manager.session_booter.pop(sandbox_id, None)
        sandbox_manager.clear_idle_state(sandbox_id)
        sandbox_manager.drop_boot_lock(sandbox_id)
        return booter

    for record in list(sandbox_manager.registry.list_sandboxes()):
        if not record.get("managed") or record.get("provider") != provider_id:
            continue
        sandbox_id = record["sandbox_id"]
        handled_sandbox_ids.add(sandbox_id)
        booter = _pop_live_booter(sandbox_id)
        if record.get("retention_policy") == "persistent":
            preserved += 1
            continue
        if booter is not None and provider is not None:
            await _safe_destroy_booter(provider, booter, record)
        sandbox_manager.registry.delete_sandbox(sandbox_id)
        removed += 1

    for sandbox_id, booter in list(sandbox_manager.session_booter.items()):
        booter_provider = getattr(booter, "provider_id", None)
        if str(booter_provider or "") != provider_id:
            continue
        if sandbox_id in handled_sandbox_ids:
            continue
        record = sandbox_manager.registry.get_sandbox(sandbox_id) or {
            "sandbox_id": sandbox_id,
            "provider": provider_id,
            "managed": True,
            "retention_policy": "temporary",
        }
        sandbox_manager.session_booter.pop(sandbox_id, None)
        sandbox_manager.clear_idle_state(sandbox_id)
        sandbox_manager.drop_boot_lock(sandbox_id)
        if provider is not None:
            await _safe_destroy_booter(provider, booter, record)
        if sandbox_manager.registry.get_sandbox(sandbox_id) is not None:
            sandbox_manager.registry.delete_sandbox(sandbox_id)
        removed += 1
    try:
        await sandbox_manager.save_registry_async()
    except Exception as exc:
        logger.warning(
            "[Computer] Failed to save registry after provider cleanup: %s",
            exc,
        )
    logger.info(
        "Provider sandbox cleanup completed: provider=%s removed_temporary=%d preserved_persistent=%d",
        provider_id,
        removed,
        preserved,
    )


def detach_sandbox_provider(provider_id: str) -> None:
    """Remove a provider and its registered tools without touching sandboxes."""
    _unregister_provider_tools(provider_id)
    sandbox_manager.providers.pop(provider_id, None)


async def _safe_destroy_booter(
    provider: SandboxProvider, booter: ComputerBooter, record: dict
) -> None:
    try:
        await provider.destroy_booter(booter, record)
    except Exception as exc:
        logger.warning(
            "Background destroy_booter failed for sandbox %s: %s",
            record.get("sandbox_id"),
            exc,
        )


async def _safe_shutdown_booter(booter: ComputerBooter, record: dict) -> None:
    try:
        await booter.shutdown()
    except Exception as exc:
        logger.warning(
            "Background shutdown failed for sandbox %s: %s",
            record.get("sandbox_id"),
            exc,
        )


def get_sandbox_provider_info(provider_id: str) -> dict | None:
    provider = sandbox_manager.providers.get(provider_id)
    if provider is None:
        return None
    return _sandbox_provider_info(provider_id, provider)


def get_current_sandbox_provider_id(session_id: str) -> str | None:
    current_sandbox_id = sandbox_manager.registry.get_current_sandbox_id(session_id)
    if not current_sandbox_id:
        return None
    current_record = sandbox_manager.registry.get_sandbox(current_sandbox_id)
    if current_record is None:
        return None
    if current_record.get("status") in {
        SandboxStatus.STOPPING,
        SandboxStatus.STOPPED,
        SandboxStatus.ERROR,
    }:
        return None
    provider_id = str(current_record.get("provider") or "").strip()
    return provider_id or None


def list_sandbox_providers() -> list[dict]:
    return [
        _sandbox_provider_info(provider_id, provider)
        for provider_id, provider in sorted(sandbox_manager.providers.items())
    ]


async def cleanup_managed_sandboxes() -> None:
    await sandbox_manager.cleanup_managed_sandboxes()


def _list_local_skill_dirs(skills_root: Path) -> list[Path]:
    skills: list[Path] = []
    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            skills.append(entry)
    return skills


def _collect_sync_skill_dirs() -> list[tuple[str, Path]]:
    """Collect local and plugin-provided skills that should be synced."""
    skills_root = Path(get_astrbot_skills_path())
    if not skills_root.is_dir():
        return []

    try:
        skill_manager = SkillManager(skills_root=str(skills_root))
    except OSError as exc:
        logger.warning("[Computer] Failed to initialize skill manager: %s", exc)
        return []

    sync_dirs: list[tuple[str, Path]] = []
    for skill in skill_manager.list_skills(
        active_only=False,
        runtime="local",
        show_sandbox_path=False,
    ):
        if skill.source_type == "sandbox_only":
            continue
        skill_md = Path(skill.path)
        if not skill_md.is_file():
            continue
        sync_dirs.append((skill.name, skill_md.parent))
    return sync_dirs


def _normalize_shell_exec_result(result: object) -> dict:
    if isinstance(result, dict):
        return result
    return {"exit_code": 0, "stdout": "", "stderr": ""}


def _build_python_exec_command(script: str) -> str:
    return (
        "if command -v python3 >/dev/null 2>&1; then PYBIN=python3; "
        "elif command -v python >/dev/null 2>&1; then PYBIN=python; "
        "else echo 'python not found in sandbox' >&2; exit 127; fi; "
        "$PYBIN - <<'PY'\n"
        f"{script}\n"
        "PY"
    )


def _build_apply_sync_command() -> str:
    """Build shell command for sync stage only.

    This stage mutates sandbox files (managed skill replacement) but does not scan
    metadata. Keeping it separate allows callers to preserve old behavior while
    reusing the apply step independently.
    """
    script = f"""
import json
import shutil
import zipfile
from pathlib import Path

root = Path({SANDBOX_SKILLS_ROOT!r})
zip_path = root / "skills.zip"
tmp_extract = Path(f"{{root}}_tmp_extract")
managed_file = root / {_MANAGED_SKILLS_FILE!r}


def remove_tree(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def load_managed_skills() -> list[str]:
    if not managed_file.exists():
        return []
    try:
        payload = json.loads(managed_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("managed_skills", [])
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


root.mkdir(parents=True, exist_ok=True)
for managed_name in load_managed_skills():
    remove_tree(root / managed_name)

current_managed: list[str] = []
if zip_path.exists():
    remove_tree(tmp_extract)
    tmp_extract.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmp_extract)
    for entry in sorted(tmp_extract.iterdir()):
        if not entry.is_dir():
            continue
        target = root / entry.name
        remove_tree(target)
        shutil.copytree(entry, target)
        current_managed.append(entry.name)

remove_tree(tmp_extract)
remove_tree(zip_path)
managed_file.write_text(
    json.dumps({{"managed_skills": current_managed}}, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps({{"managed_skills": current_managed}}, ensure_ascii=False))
""".strip()
    return _build_python_exec_command(script)


def _build_scan_command() -> str:
    """Build shell command for scan stage only.

    This stage is read-oriented: it scans SKILL.md metadata and returns the
    historical payload shape consumed by cache update logic.

    The scan resolves the absolute path of the skills root at runtime so
    that the LLM can reliably ``cat`` skill files regardless of cwd.
    Only the ``description`` field is extracted from frontmatter.
    """
    script = f"""
import json
from pathlib import Path

root = Path({SANDBOX_SKILLS_ROOT!r})
managed_file = root / {_MANAGED_SKILLS_FILE!r}

# Resolve absolute path at runtime so prompts always have a reliable path
root_abs = str(root.resolve())


# NOTE: This parser mirrors skill_manager._parse_frontmatter_description.
# Keep the two implementations in sync when changing parsing logic.
def parse_description(text: str) -> str:
    if not text.startswith("---"):
        return ""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return ""

    frontmatter = "\\n".join(lines[1:end_idx])
    try:
        import yaml
    except ImportError:
        return ""

    try:
        payload = yaml.safe_load(frontmatter) or dict()
    except yaml.YAMLError:
        return ""
    if not isinstance(payload, dict):
        return ""

    description = payload.get("description", "")
    if not isinstance(description, str):
        return ""
    return description.strip()


def load_managed_skills() -> list[str]:
    if not managed_file.exists():
        return []
    try:
        payload = json.loads(managed_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    items = payload.get("managed_skills", [])
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def collect_skills() -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    if not root.exists():
        return skills
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        description = ""
        try:
            text = skill_md.read_text(encoding="utf-8")
            description = parse_description(text)
        except Exception:
            description = ""
        skills.append(
            {{
                "name": skill_dir.name,
                "description": description,
                "path": f"{{root_abs}}/{{skill_dir.name}}/SKILL.md",
            }}
        )
    return skills


print(
    json.dumps(
        {{
            "managed_skills": load_managed_skills(),
            "skills": collect_skills(),
        }},
        ensure_ascii=False,
    )
)
""".strip()
    return _build_python_exec_command(script)


def _build_sync_and_scan_command() -> str:
    """Legacy combined command kept for backward compatibility.

    New code paths should prefer apply + scan split helpers.
    """
    return f"{_build_apply_sync_command()}\n{_build_scan_command()}"


def _shell_exec_succeeded(result: dict) -> bool:
    if "success" in result:
        return bool(result.get("success"))
    exit_code = result.get("exit_code")
    return exit_code in (0, None)


def _format_exec_error_detail(result: dict) -> str:
    """Format shell execution details for better observability.

    Keep the message compact while still surfacing exit code and stderr/stdout.
    """
    exit_code = result.get("exit_code")
    stderr = str(result.get("stderr", "") or "").strip()
    stdout = str(result.get("stdout", "") or "").strip()
    stderr_text = stderr[:500]
    stdout_text = stdout[:300]
    return f"exit_code={exit_code}, stderr={stderr_text!r}, stdout_tail={stdout_text!r}"


def _decode_sync_payload(stdout: str) -> dict | None:
    text = stdout.strip()
    if not text:
        return None
    candidates = [text]
    candidates.extend([line.strip() for line in text.splitlines() if line.strip()])
    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _update_sandbox_skills_cache(payload: dict | None) -> None:
    if not isinstance(payload, dict):
        return
    skills = payload.get("skills", [])
    if not isinstance(skills, list):
        return
    SkillManager().set_sandbox_skills_cache(skills)


async def _apply_skills_to_sandbox(booter: ComputerBooter) -> None:
    """Apply local skill bundle to sandbox filesystem only.

    This function is intentionally limited to file mutation. Metadata scanning is
    executed in a separate phase to keep failure domains clear.
    """
    logger.info("[Computer] Skill sync phase=apply start")
    apply_result = _normalize_shell_exec_result(
        await booter.shell.exec(_build_apply_sync_command())
    )
    if not _shell_exec_succeeded(apply_result):
        detail = _format_exec_error_detail(apply_result)
        logger.error("[Computer] Skill sync phase=apply failed: %s", detail)
        raise RuntimeError(f"Failed to apply sandbox skill sync strategy: {detail}")
    logger.info("[Computer] Skill sync phase=apply done")


async def _scan_sandbox_skills(booter: ComputerBooter) -> dict | None:
    """Scan sandbox skills and return normalized payload for cache update."""
    logger.info("[Computer] Skill sync phase=scan start")
    scan_result = _normalize_shell_exec_result(
        await booter.shell.exec(_build_scan_command())
    )
    if not _shell_exec_succeeded(scan_result):
        detail = _format_exec_error_detail(scan_result)
        logger.error("[Computer] Skill sync phase=scan failed: %s", detail)
        raise RuntimeError(f"Failed to scan sandbox skills after sync: {detail}")

    payload = _decode_sync_payload(str(scan_result.get("stdout", "") or ""))
    if payload is None:
        logger.warning("[Computer] Skill sync phase=scan returned empty payload")
    else:
        logger.info("[Computer] Skill sync phase=scan done")
    return payload


async def _sync_skills_to_sandbox(booter: ComputerBooter) -> None:
    """Sync local skills to sandbox and refresh cache.

    Backward-compatible orchestrator: keep historical behavior while internally
    splitting into `apply` and `scan` phases.
    """
    sync_skill_dirs = _collect_sync_skill_dirs()

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_base = temp_dir / "skills_bundle"
    zip_path = zip_base.with_suffix(".zip")
    bundle_root = temp_dir / f"skills_bundle_{uuid.uuid4().hex}"

    try:
        if sync_skill_dirs:
            if zip_path.exists():
                zip_path.unlink()
            if bundle_root.exists():
                shutil.rmtree(bundle_root)
            bundle_root.mkdir(parents=True)
            for skill_name, skill_dir in sync_skill_dirs:
                shutil.copytree(skill_dir, bundle_root / skill_name)
            shutil.make_archive(str(zip_base), "zip", str(bundle_root))
            remote_zip = Path(SANDBOX_SKILLS_ROOT) / "skills.zip"
            logger.info("Uploading skills bundle to sandbox...")
            await booter.shell.exec(f"mkdir -p {SANDBOX_SKILLS_ROOT}")
            upload_result = await booter.upload_file(str(zip_path), str(remote_zip))
            if not upload_result.get("success", False):
                raise RuntimeError("Failed to upload skills bundle to sandbox.")
        else:
            logger.info(
                "No local skills found. Keeping sandbox built-ins and refreshing metadata."
            )
            await booter.shell.exec(f"rm -f {SANDBOX_SKILLS_ROOT}/skills.zip")

        # Keep backward-compatible behavior while splitting lifecycle into two
        # observable phases: apply (filesystem mutation) + scan (metadata read).
        await _apply_skills_to_sandbox(booter)
        payload = await _scan_sandbox_skills(booter)
        _update_sandbox_skills_cache(payload)
        managed = payload.get("managed_skills", []) if isinstance(payload, dict) else []
        logger.info(
            "[Computer] Sandbox skill sync complete: managed=%d",
            len(managed),
        )
    finally:
        if bundle_root.exists():
            try:
                shutil.rmtree(bundle_root)
            except Exception:
                logger.warning(f"Failed to remove temp skills bundle: {bundle_root}")
        if zip_path.exists():
            try:
                zip_path.unlink()
            except Exception:
                logger.warning(f"Failed to remove temp skills zip: {zip_path}")


async def get_booter(
    context: Context,
    session_id: str,
) -> ComputerBooter:
    config = context.get_config(umo=session_id)

    runtime = config.get("provider_settings", {}).get("computer_use_runtime", "local")
    if runtime == "local":
        return get_local_booter()
    elif runtime == "none":
        raise RuntimeError("Sandbox runtime is disabled by configuration.")

    current_sandbox_id = sandbox_manager.registry.get_current_sandbox_id(session_id)
    if current_sandbox_id:
        current_record = sandbox_manager.registry.get_sandbox(current_sandbox_id)
        if current_record and current_record.get("managed"):
            return await sandbox_manager.get_observer_booter_by_id(
                current_sandbox_id,
                session_id,
                require_lease=True,
                context=context,
            )

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    provider_id = str(sandbox_cfg.get("booter", "")).strip()
    if not provider_id:
        raise ValueError(
            "Sandbox provider is not configured. Install and enable a sandbox provider plugin, then select it in provider_settings.sandbox.booter."
        )

    logger.info(
        f"[Computer] Initializing sandbox provider: provider={provider_id}, session={session_id}"
    )
    if provider_id in sandbox_manager.providers:
        return await sandbox_manager.get_or_create_booter(
            context,
            session_id,
            provider_id,
        )
    raise ValueError(
        f"Unknown sandbox provider: {provider_id}. Install and enable a sandbox provider plugin, then select it in provider_settings.sandbox.booter."
    )


async def sync_skills_to_active_sandboxes() -> None:
    """Best-effort skills synchronization for all active sandbox sessions."""
    active_booters = list(sandbox_manager.session_booter.items())
    logger.info(
        "[Computer] Syncing skills to %d active sandbox(es)", len(active_booters)
    )
    for sandbox_id, booter in active_booters:
        try:
            if not await sandbox_manager.booter_available(booter):
                continue
            await _sync_skills_to_sandbox(booter)
        except Exception as e:
            logger.warning(
                "Failed to sync skills to sandbox for sandbox %s: %s",
                sandbox_id,
                e,
            )


def get_local_booter() -> ComputerBooter:
    global local_booter
    if local_booter is None:
        local_booter = LocalBooter()
    return local_booter
