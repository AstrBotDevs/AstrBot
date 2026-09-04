import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from astrbot.api import logger
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT, SkillManager
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter, resolve_windows_shell

session_booter: dict[str, ComputerBooter] = {}
session_boot_inflight: dict[str, asyncio.Future[ComputerBooter]] = {}
session_boot_creators: dict[str, asyncio.Task] = {}
session_boot_candidates: dict[str, tuple[ComputerBooter, str]] = {}
local_booter: ComputerBooter | None = None
computer_shutdown_started = False
computer_runtime_generation = 0
COMPUTER_BOOT_DRAIN_TIMEOUT_SECONDS = 30.0
COMPUTER_SHUTDOWN_TIMEOUT_SECONDS = 15.0
_abandoned_shutdown_tasks: set[asyncio.Task] = set()
_MANAGED_SKILLS_FILE = ".astrbot_managed_skills.json"


@dataclass(slots=True)
class _CUAIdleState:
    expires_at: float
    task: asyncio.Task


cua_idle_state: dict[str, _CUAIdleState] = {}


def _get_cua_idle_timeout(config: dict) -> float:
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    value = sandbox_cfg.get("cua_idle_timeout", 0)
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(timeout, 0.0)


def _clear_cua_idle_state(session_id: str) -> None:
    state = cua_idle_state.pop(session_id, None)
    if state is not None and not state.task.done():
        state.task.cancel()


def _schedule_cua_idle_cleanup(session_id: str, timeout: float) -> None:
    _clear_cua_idle_state(session_id)
    if timeout <= 0:
        return
    expires_at = time.monotonic() + timeout

    async def _expire_when_idle() -> None:
        try:
            remaining = expires_at - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)

            state = cua_idle_state.get(session_id)
            if state is None or state.expires_at != expires_at:
                return

            booter = session_booter.get(session_id)
            if booter is not None and cua_idle_state.get(session_id) is state:
                try:
                    await booter.shutdown()
                except Exception as shutdown_err:
                    logger.warning(
                        "[Computer] Failed to shutdown idle CUA sandbox for session %s: %s",
                        session_id,
                        shutdown_err,
                    )
                finally:
                    session_booter.pop(session_id, None)
        except asyncio.CancelledError:
            raise
        finally:
            state = cua_idle_state.get(session_id)
            if state is not None and state.expires_at == expires_at:
                cua_idle_state.pop(session_id, None)

    task = asyncio.create_task(_expire_when_idle())
    cua_idle_state[session_id] = _CUAIdleState(expires_at=expires_at, task=task)


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
    from astrbot.core.star.star import star_registry

    skills_root = Path(get_astrbot_skills_path())
    try:
        skill_manager = SkillManager(skills_root=str(skills_root))
    except OSError as exc:
        logger.warning("[Computer] Failed to initialize skill manager: %s", exc)
        return []

    active_plugin_root_names = {
        plugin.root_dir_name
        for plugin in star_registry
        if plugin.activated and plugin.root_dir_name
    }
    sync_dirs: list[tuple[str, Path]] = []
    for skill in skill_manager.list_skills(
        active_only=False,
        runtime="local",
        show_sandbox_path=False,
    ):
        if skill.source_type == "sandbox_only":
            continue
        if (
            skill.source_type == "plugin"
            and skill.plugin_name not in active_plugin_root_names
        ):
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


def _discover_bay_credentials(endpoint: str) -> str:
    """Try to auto-discover Bay API key from credentials.json.

    Search order:
    1. BAY_DATA_DIR env var
    2. Mono-repo relative path: ../pkgs/bay/ (dev layout)
    3. Current working directory

    Returns:
        API key string, or empty string if not found.
    """
    candidates: list[Path] = []

    # 1. BAY_DATA_DIR env var
    bay_data_dir = os.environ.get("BAY_DATA_DIR")
    if bay_data_dir:
        candidates.append(Path(bay_data_dir) / "credentials.json")

    # 2. Mono-repo layout: AstrBot/../pkgs/bay/credentials.json
    astrbot_root = Path(__file__).resolve().parents[3]  # astrbot/core/computer/ → root
    candidates.append(astrbot_root.parent / "pkgs" / "bay" / "credentials.json")

    # 3. Current working directory
    candidates.append(Path.cwd() / "credentials.json")

    for cred_path in candidates:
        if not cred_path.is_file():
            continue
        try:
            data = json.loads(cred_path.read_text())
            api_key = data.get("api_key", "")
            if api_key:
                # Optionally verify endpoint matches
                cred_endpoint = data.get("endpoint", "")
                if (
                    cred_endpoint
                    and endpoint
                    and cred_endpoint.rstrip("/") != endpoint.rstrip("/")
                ):
                    logger.warning(
                        "[Computer] credentials.json endpoint mismatch: "
                        "file=%s, configured=%s — using key anyway",
                        cred_endpoint,
                        endpoint,
                    )
                masked_key = f"{api_key[:4]}..." if len(api_key) >= 6 else "redacted"
                logger.info(
                    "[Computer] Auto-discovered Bay API key from %s (prefix=%s)",
                    cred_path,
                    masked_key,
                )
                return api_key
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("[Computer] Failed to read %s: %s", cred_path, exc)

    logger.debug("[Computer] No Bay credentials.json found in search paths")
    return ""


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
            # Force forward slashes for sandbox compatibility.
            remote_zip = (Path(SANDBOX_SKILLS_ROOT) / "skills.zip").as_posix()
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
    if computer_shutdown_started:
        raise RuntimeError("Computer runtime is shutting down.")
    boot_generation = computer_runtime_generation

    config = context.get_config(umo=session_id)
    # Import lazily because the computer tool package imports ``get_booter``.
    from astrbot.core.tools.computer_tools.util import resolve_computer_use_runtime

    runtime = resolve_computer_use_runtime(config.get("provider_settings", {}))
    if runtime == "local":
        return get_local_booter()
    if runtime == "none":
        raise RuntimeError("Sandbox runtime is disabled by configuration.")

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard_neo")
    cua_idle_timeout = _get_cua_idle_timeout(config) if booter_type == "cua" else 0.0
    existing_boot = session_boot_inflight.get(session_id)
    if existing_boot is not None:
        return await asyncio.shield(existing_boot)

    boot_future: asyncio.Future[ComputerBooter] = (
        asyncio.get_running_loop().create_future()
    )
    # The creator raises directly; consume the future exception as well so a
    # failed first boot without concurrent waiters does not emit an unhandled
    # Future warning.
    boot_future.add_done_callback(
        lambda future: None if future.cancelled() else future.exception()
    )
    session_boot_inflight[session_id] = boot_future
    creator_task = asyncio.current_task()
    if creator_task is not None:
        session_boot_creators[session_id] = creator_task
    client: ComputerBooter | None = None
    try:
        current = session_booter.get(session_id)
        if current is not None and await current.available():
            boot_future.set_result(current)
            return current
        if current is not None:
            try:
                if current.__class__.__name__ == "ShipyardNeoBooter":
                    await current.shutdown(delete_sandbox=True)
                else:
                    await current.shutdown()
            except Exception as exc:
                logger.warning(
                    "[Computer] Failed to shut down stale sandbox for session %s: %s",
                    session_id,
                    exc,
                )
            _clear_cua_idle_state(session_id)
            session_booter.pop(session_id, None)

        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        # Keep boot diagnostics free of configuration values (notably CUA API
        # keys) and as a single rendered message so lightweight logger hooks
        # can safely consume it too.
        logger.info(
            f"[Computer] Initializing booter: type={booter_type}, session={session_id}"
        )
        if booter_type == "shipyard":
            from .booters.shipyard import ShipyardBooter

            client = ShipyardBooter(
                endpoint_url=sandbox_cfg.get("shipyard_endpoint", ""),
                access_token=sandbox_cfg.get("shipyard_access_token", ""),
                ttl=sandbox_cfg.get("shipyard_ttl", 3600),
                session_num=sandbox_cfg.get("shipyard_max_sessions", 10),
            )
        elif booter_type == "shipyard_neo":
            from .booters.shipyard_neo import ShipyardNeoBooter

            endpoint = sandbox_cfg.get("shipyard_neo_endpoint", "")
            token = sandbox_cfg.get("shipyard_neo_access_token", "")
            if not token:
                token = _discover_bay_credentials(endpoint)
            client = ShipyardNeoBooter(
                endpoint_url=endpoint,
                access_token=token,
                profile=sandbox_cfg.get("shipyard_neo_profile", "python-default"),
                ttl=sandbox_cfg.get("shipyard_neo_ttl", 3600),
            )
        elif booter_type == "cua":
            from .booters.cua import CuaBooter, build_cua_booter_kwargs

            client = CuaBooter(**build_cua_booter_kwargs(sandbox_cfg))
        elif booter_type == "boxlite":
            from .booters.boxlite import BoxliteBooter

            client = BoxliteBooter()
        else:
            raise ValueError(f"Unknown booter type: {booter_type}")

        session_boot_candidates[session_id] = (client, booter_type)
        await client.boot(uuid_str)
        await _sync_skills_to_sandbox(client)
        if computer_shutdown_started or boot_generation != computer_runtime_generation:
            raise RuntimeError("Computer runtime is shutting down.")
        session_boot_candidates.pop(session_id, None)
        session_booter[session_id] = client
        if booter_type == "cua":
            _schedule_cua_idle_cleanup(session_id, cua_idle_timeout)
        boot_future.set_result(client)
        return client
    except BaseException as exc:
        candidate = session_boot_candidates.get(session_id)
        if client is not None and candidate is not None and candidate[0] is client:
            session_boot_candidates.pop(session_id, None)
            await _shutdown_managed_booter(
                session_id,
                client,
                booter_type=booter_type,
            )
        _clear_cua_idle_state(session_id)
        if not boot_future.done():
            boot_future.set_exception(exc)
        raise
    finally:
        candidate = session_boot_candidates.get(session_id)
        if candidate is not None and candidate[0] is client:
            session_boot_candidates.pop(session_id, None)
        if session_boot_creators.get(session_id) is creator_task:
            session_boot_creators.pop(session_id, None)
        if session_boot_inflight.get(session_id) is boot_future:
            session_boot_inflight.pop(session_id, None)


async def sync_skills_to_active_sandboxes() -> None:
    """Best-effort skills synchronization for all active sandbox sessions."""
    logger.info(
        "[Computer] Syncing skills to %d active sandbox(es)", len(session_booter)
    )
    for session_id, booter in list(session_booter.items()):
        try:
            if not await booter.available():
                continue
            await _sync_skills_to_sandbox(booter)
        except Exception as e:
            logger.warning(
                "Failed to sync skills to sandbox for session %s: %s",
                session_id,
                e,
            )


def get_local_booter() -> ComputerBooter:
    global local_booter
    if local_booter is None:
        local_booter = LocalBooter()
        if sys.platform == "win32":
            logger.info(
                "[Computer] Windows local runtime shell: %s",
                resolve_windows_shell(),
            )
    return local_booter


def _observe_abandoned_shutdown(task: asyncio.Task) -> None:
    """Retain and consume a shutdown task that ignored cancellation."""
    _abandoned_shutdown_tasks.discard(task)
    if task.cancelled():
        return
    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return
    if exception is not None:
        logger.warning(
            "[Computer] An abandoned resource shutdown later failed: %s",
            exception,
        )


def _track_shutdown_task(coro) -> asyncio.Task:
    """Start a cleanup task that survives cancellation of its current waiter."""
    task = asyncio.create_task(coro)
    _abandoned_shutdown_tasks.add(task)
    task.add_done_callback(_observe_abandoned_shutdown)
    return task


async def _await_with_hard_timeout(coro, timeout: float) -> bool:
    """Wait at most ``timeout`` even if the coroutine suppresses cancellation."""
    task = asyncio.create_task(coro)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout)
    except BaseException:
        task.cancel()
        _abandoned_shutdown_tasks.add(task)
        task.add_done_callback(_observe_abandoned_shutdown)
        raise
    if task not in done:
        task.cancel()
        _abandoned_shutdown_tasks.add(task)
        task.add_done_callback(_observe_abandoned_shutdown)
        return False
    await task
    return True


async def shutdown_local_booter() -> None:
    """Shut down managed local computer resources without creating a booter."""
    global local_booter
    if local_booter is None:
        return
    booter = local_booter
    local_booter = None
    try:
        completed = await _await_with_hard_timeout(
            booter.shutdown(),
            COMPUTER_SHUTDOWN_TIMEOUT_SECONDS,
        )
        if not completed:
            logger.warning("[Computer] Timed out shutting down the local runtime")
    except Exception as exc:
        logger.warning("[Computer] Failed to shut down local booter: %s", exc)


async def _shutdown_managed_booter(
    session_id: str,
    booter: ComputerBooter,
    *,
    booter_type: str | None = None,
) -> None:
    """Best-effort one sandbox shutdown with a hard time bound."""
    try:
        if booter_type == "shipyard_neo" or (
            booter_type is None and booter.__class__.__name__ == "ShipyardNeoBooter"
        ):
            shutdown = booter.shutdown(delete_sandbox=True)
        else:
            shutdown = booter.shutdown()
        completed = await _await_with_hard_timeout(
            shutdown,
            COMPUTER_SHUTDOWN_TIMEOUT_SECONDS,
        )
        if completed:
            return
        logger.warning(
            "[Computer] Timed out shutting down sandbox for session %s",
            session_id,
        )
    except Exception as exc:
        logger.warning(
            "[Computer] Failed to shut down sandbox for session %s: %s",
            session_id,
            exc,
        )


async def shutdown_all_booters() -> None:
    """Shut down every managed computer runtime and prevent new boots.

    A session sandbox is remote state, so stopping only the local booter leaks
    containers after a core stop or restart. This function serializes shutdown
    with in-flight boot operations and best-effort cleans every registered
    sandbox.
    """
    global computer_runtime_generation, computer_shutdown_started
    computer_shutdown_started = True
    computer_runtime_generation += 1
    shutdown_completed = False
    try:
        idle_tasks = [state.task for state in cua_idle_state.values()]
        cua_idle_state.clear()
        for task in idle_tasks:
            task.cancel()
        if idle_tasks:
            _, pending_idle = await asyncio.wait(
                idle_tasks,
                timeout=COMPUTER_SHUTDOWN_TIMEOUT_SECONDS,
            )
            if pending_idle:
                logger.warning(
                    "[Computer] %d idle cleanup task(s) did not stop in time",
                    len(pending_idle),
                )

        inflight = list(session_boot_inflight.values())
        pending_inflight: set[asyncio.Future[ComputerBooter]] = set()
        if inflight:
            _, pending_inflight = await asyncio.wait(
                inflight,
                timeout=COMPUTER_BOOT_DRAIN_TIMEOUT_SECONDS,
            )
        if pending_inflight:
            creator_tasks = {
                task
                for session_id, future in session_boot_inflight.items()
                if future in pending_inflight
                and (task := session_boot_creators.get(session_id)) is not None
            }
            for task in creator_tasks:
                task.cancel()
            if creator_tasks:
                _, stuck_creators = await asyncio.wait(
                    creator_tasks,
                    timeout=COMPUTER_SHUTDOWN_TIMEOUT_SECONDS,
                )
                if stuck_creators:
                    logger.warning(
                        "[Computer] %d sandbox boot task(s) ignored cancellation",
                        len(stuck_creators),
                    )

        candidates: list[tuple[str, tuple[ComputerBooter, str]]] = []
        for session_id, candidate in list(session_boot_candidates.items()):
            if session_boot_candidates.get(session_id) is candidate:
                session_boot_candidates.pop(session_id, None)
                candidates.append((session_id, candidate))
        if candidates:
            candidate_cleanup_tasks = [
                _track_shutdown_task(
                    _shutdown_managed_booter(
                        session_id,
                        candidate,
                        booter_type=booter_type,
                    )
                )
                for session_id, (candidate, booter_type) in candidates
            ]
            await asyncio.gather(
                *(asyncio.shield(task) for task in candidate_cleanup_tasks),
                return_exceptions=True,
            )
        for future in session_boot_inflight.values():
            if not future.done():
                future.set_exception(RuntimeError("Computer runtime shut down."))
        session_boot_candidates.clear()
        session_boot_creators.clear()
        session_boot_inflight.clear()

        booters = list(session_booter.items())
        session_booter.clear()
        if booters:
            booter_cleanup_tasks = [
                _track_shutdown_task(_shutdown_managed_booter(session_id, booter))
                for session_id, booter in booters
            ]
            await asyncio.gather(
                *(asyncio.shield(task) for task in booter_cleanup_tasks),
                return_exceptions=True,
            )
        await shutdown_local_booter()
        shutdown_completed = True
    finally:
        # A cancelled lifecycle shutdown remains fail-closed until explicit
        # initialization calls ``enable_computer_booters``.
        computer_shutdown_started = not shutdown_completed


def enable_computer_booters() -> None:
    """Allow managed computer runtimes to boot after lifecycle initialization."""
    global computer_shutdown_started
    computer_shutdown_started = False
