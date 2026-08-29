import asyncio
import json
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT, SkillManager
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter, resolve_windows_shell

if TYPE_CHECKING:
    from astrbot.core.execution_context import CoreExecutionContext
    from astrbot.core.star.star import PluginRegistry


_MANAGED_SKILLS_FILE = ".astrbot_managed_skills.json"


@dataclass(slots=True)
class _CUAIdleState:
    expires_at: float
    task: asyncio.Task[None]


def _get_cua_idle_timeout(config: dict) -> float:
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    value = sandbox_cfg.get("cua_idle_timeout", 0)
    try:
        timeout = float(value)
    except TypeError, ValueError:
        return 0.0
    return max(timeout, 0.0)


class _ComputerRuntimeState:
    """Internal mutable state shared by the computer runtime operations.

    The public :class:`ComputerRuntime` below owns this state for one
    :class:`RuntimeServices` value.  It deliberately has no process-global
    fallback, so independent AstrBot runtimes cannot share sandboxes, locks,
    or CUA idle tasks.
    """

    def __init__(self) -> None:
        self._session_booters: dict[str, ComputerBooter] = {}
        self._session_booter_types: dict[str, str] = {}
        self._session_booter_locks: dict[str, asyncio.Lock] = {}
        self._cua_idle_states: dict[str, _CUAIdleState] = {}
        self._local_booter: ComputerBooter | None = None
        self._terminated = False

    def get_session_booter(self, session_id: str) -> ComputerBooter | None:
        """Return the existing session booter without creating one."""
        return self._session_booters.get(session_id)

    def _ensure_active(self) -> None:
        if self._terminated:
            raise RuntimeError("Computer runtime has been terminated.")

    def _clear_cua_idle_state(self, session_id: str) -> None:
        state = self._cua_idle_states.pop(session_id, None)
        if state is not None and not state.task.done():
            state.task.cancel()

    def _schedule_cua_idle_cleanup(self, session_id: str, timeout: float) -> None:
        self._clear_cua_idle_state(session_id)
        if timeout <= 0:
            return
        expires_at = time.monotonic() + timeout

        async def _expire_when_idle() -> None:
            try:
                remaining = expires_at - time.monotonic()
                if remaining > 0:
                    await asyncio.sleep(remaining)

                state = self._cua_idle_states.get(session_id)
                if state is None or state.expires_at != expires_at:
                    return

                booter = self._session_booters.get(session_id)
                if booter is not None:
                    try:
                        await booter.shutdown()
                    except asyncio.CancelledError:
                        raise
                    except Exception as shutdown_err:  # noqa: BLE001
                        logger.warning(
                            "[Computer] Failed to shutdown idle CUA sandbox for session %s: %s",
                            session_id,
                            shutdown_err,
                        )
                    finally:
                        self._session_booters.pop(session_id, None)
                        self._session_booter_types.pop(session_id, None)
            except asyncio.CancelledError:
                raise
            finally:
                state = self._cua_idle_states.get(session_id)
                if state is not None and state.expires_at == expires_at:
                    self._cua_idle_states.pop(session_id, None)

        task = asyncio.create_task(_expire_when_idle())
        self._cua_idle_states[session_id] = _CUAIdleState(
            expires_at=expires_at,
            task=task,
        )

    @staticmethod
    async def _shutdown_booter(booter: ComputerBooter, booter_type: str) -> None:
        if booter_type == "shipyard_neo":
            await booter.shutdown(delete_sandbox=True)
        else:
            await booter.shutdown()


def _list_local_skill_dirs(skills_root: Path) -> list[Path]:
    skills: list[Path] = []
    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            skills.append(entry)
    return skills


def _collect_sync_skill_dirs(
    skill_manager: SkillManager | None = None,
    plugins: PluginRegistry | None = None,
) -> list[tuple[str, Path]]:
    """Collect local, plugin, and builtin Skills that should be synced."""
    skills_root = Path(get_astrbot_skills_path())

    try:
        skill_manager = skill_manager or SkillManager(skills_root=str(skills_root))
    except OSError as exc:
        logger.warning("[Computer] Failed to initialize skill manager: %s", exc)
        return []

    plugin_by_root: dict[str, object] = {}
    ambiguous_plugin_roots: set[str] = set()
    if plugins is not None:
        for metadata in plugins.all():
            root_dir_name = metadata.root_dir_name
            if not root_dir_name:
                continue
            if root_dir_name in plugin_by_root:
                ambiguous_plugin_roots.add(root_dir_name)
                continue
            plugin_by_root[root_dir_name] = metadata
    active_plugin_root_names = {
        root_dir_name
        for root_dir_name, metadata in plugin_by_root.items()
        if root_dir_name not in ambiguous_plugin_roots
        and getattr(metadata, "activated", False)
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
    """Build the combined sync command used by the sandbox skill flow."""
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


def _update_sandbox_skills_cache(
    payload: dict | None,
    skill_manager: SkillManager | None = None,
) -> None:
    if not isinstance(payload, dict):
        return
    skills = payload.get("skills", [])
    if not isinstance(skills, list):
        return
    (skill_manager or SkillManager()).set_sandbox_skills_cache(skills)


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


async def _sync_skills_to_sandbox(
    booter: ComputerBooter,
    skill_manager: SkillManager | None = None,
    plugins: PluginRegistry | None = None,
) -> None:
    """Sync local skills to sandbox and refresh cache.

    The flow keeps two explicit phases: apply filesystem changes, then scan
    metadata for cache refresh.
    """
    sync_skill_dirs = _collect_sync_skill_dirs(skill_manager, plugins)

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
            remote_zip = PurePosixPath(SANDBOX_SKILLS_ROOT) / "skills.zip"
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

        # Split the sync into two observable phases: apply filesystem mutation,
        # then scan metadata for cache refresh.
        await _apply_skills_to_sandbox(booter)
        payload = await _scan_sandbox_skills(booter)
        _update_sandbox_skills_cache(payload, skill_manager)
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


class ComputerRuntime(_ComputerRuntimeState):
    """Runtime-owned computer sandbox capability."""

    def __init__(self) -> None:
        super().__init__()
        self._skill_manager: SkillManager | None = None
        self._plugins: PluginRegistry | None = None

    def bind_skill_manager(
        self,
        skill_manager: SkillManager,
        plugins: PluginRegistry,
    ) -> None:
        """Bind the lifecycle-owned Skill inventory after plugin loading."""
        self._skill_manager = skill_manager
        self._plugins = plugins

    async def get_booter(
        self,
        context: CoreExecutionContext,
        session_id: str,
    ) -> ComputerBooter:
        """Return the configured local or sandbox booter for one session."""
        self._ensure_active()
        lock = self._session_booter_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            config = context.get_config(umo=session_id)

            runtime = config.get("provider_settings", {}).get(
                "computer_use_runtime", "local"
            )
            if runtime == "local":
                return self.get_local_booter()
            if runtime == "none":
                raise RuntimeError("Sandbox runtime is disabled by configuration.")

            sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
            booter_type = sandbox_cfg.get("booter", "shipyard_neo")
            cua_idle_timeout = (
                _get_cua_idle_timeout(config) if booter_type == "cua" else 0.0
            )

            booter = self._session_booters.get(session_id)
            if booter is not None and not await booter.available():
                # Clean up old booters before rebuilding so remote resources
                # (containers, volumes, and networks) are not leaked.
                try:
                    await self._shutdown_booter(
                        booter,
                        self._session_booter_types.get(session_id, booter_type),
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as shutdown_err:  # noqa: BLE001
                    logger.warning(
                        "[Computer] Error shutting down stale booter for session %s: %s",
                        session_id,
                        shutdown_err,
                    )
                self._clear_cua_idle_state(session_id)
                self._session_booters.pop(session_id, None)
                self._session_booter_types.pop(session_id, None)
                booter = None

            if booter is None:
                uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
                logger.info(
                    "[Computer] Initializing booter: type=%s, session=%s",
                    booter_type,
                    session_id,
                )
                if booter_type == "shipyard_neo":
                    from .booters.shipyard_neo import ShipyardNeoBooter

                    endpoint = sandbox_cfg.get("shipyard_neo_endpoint", "")
                    token = sandbox_cfg.get("shipyard_neo_access_token", "")
                    ttl = sandbox_cfg.get("shipyard_neo_ttl", 3600)
                    profile = sandbox_cfg.get(
                        "shipyard_neo_profile",
                        "python-default",
                    )

                    # Auto-discover a token only when configuration did not provide one.
                    if not token:
                        token = _discover_bay_credentials(endpoint)

                    logger.info(
                        "[Computer] Shipyard Neo config: endpoint=%s, profile=%s, ttl=%s",
                        endpoint,
                        profile,
                        ttl,
                    )
                    client = ShipyardNeoBooter(
                        endpoint_url=endpoint,
                        access_token=token,
                        profile=profile,
                        ttl=ttl,
                    )
                elif booter_type == "cua":
                    from .booters.cua import CuaBooter, build_cua_booter_kwargs

                    cua_kwargs = build_cua_booter_kwargs(sandbox_cfg)
                    logger.info(
                        "[Computer] CUA config: image=%s, os_type=%s, ttl=%s",
                        cua_kwargs["image"],
                        cua_kwargs["os_type"],
                        cua_kwargs["ttl"],
                    )
                    client = CuaBooter(**cua_kwargs)
                else:
                    raise ValueError(f"Unknown booter type: {booter_type}")

                try:
                    await client.boot(uuid_str)
                    logger.info(
                        "[Computer] Sandbox booted successfully: type=%s, session=%s",
                        booter_type,
                        session_id,
                    )
                    await _sync_skills_to_sandbox(
                        client,
                        self._skill_manager,
                        self._plugins,
                    )
                except asyncio.CancelledError:
                    try:
                        await self._shutdown_booter(client, booter_type)
                    except asyncio.CancelledError:
                        raise
                    except Exception as shutdown_error:  # noqa: BLE001
                        logger.warning(
                            "Failed to shutdown cancelled sandbox boot for session %s: %s",
                            session_id,
                            shutdown_error,
                        )
                    self._clear_cua_idle_state(session_id)
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Error booting sandbox for session %s: %s", session_id, exc
                    )
                    try:
                        await self._shutdown_booter(client, booter_type)
                    except asyncio.CancelledError:
                        raise
                    except Exception as shutdown_error:  # noqa: BLE001
                        logger.warning(
                            "Failed to shutdown sandbox after boot error for session %s: %s",
                            session_id,
                            shutdown_error,
                        )
                    self._clear_cua_idle_state(session_id)
                    raise

                self._session_booters[session_id] = client
                self._session_booter_types[session_id] = booter_type
                booter = client

            if booter_type == "cua":
                self._schedule_cua_idle_cleanup(session_id, cua_idle_timeout)
            return booter

    def get_local_booter(self) -> ComputerBooter:
        """Return this runtime's lazily constructed local booter."""
        self._ensure_active()
        if self._local_booter is None:
            self._local_booter = LocalBooter()
            if sys.platform == "win32":
                logger.info(
                    "[Computer] Windows local runtime shell: %s",
                    resolve_windows_shell(),
                )
        return self._local_booter

    async def sync_skills_to_active_sandboxes(self) -> None:
        """Best-effort skills synchronization for all active sandbox sessions."""
        self._ensure_active()
        logger.info(
            "[Computer] Syncing skills to %d active sandbox(es)",
            len(self._session_booters),
        )
        for session_id, booter in list(self._session_booters.items()):
            try:
                if not await booter.available():
                    continue
                await _sync_skills_to_sandbox(
                    booter,
                    self._skill_manager,
                    self._plugins,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to sync skills to sandbox for session %s: %s",
                    session_id,
                    exc,
                )

    async def terminate(self) -> None:
        """Cancel idle cleanup and terminate every booter owned by this runtime."""
        if self._terminated:
            return
        self._terminated = True

        idle_tasks = [state.task for state in self._cua_idle_states.values()]
        self._cua_idle_states.clear()
        for task in idle_tasks:
            if not task.done():
                task.cancel()
        if idle_tasks:
            await asyncio.gather(*idle_tasks, return_exceptions=True)

        booters = list(self._session_booters.items())
        booter_types = self._session_booter_types.copy()
        self._session_booters.clear()
        self._session_booter_types.clear()
        self._session_booter_locks.clear()
        for session_id, booter in booters:
            try:
                await self._shutdown_booter(
                    booter,
                    booter_types.get(session_id, ""),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to terminate sandbox for session %s: %s",
                    session_id,
                    exc,
                )

        local_booter, self._local_booter = self._local_booter, None
        if local_booter is not None:
            try:
                await local_booter.shutdown()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to terminate local computer runtime: %s", exc)
