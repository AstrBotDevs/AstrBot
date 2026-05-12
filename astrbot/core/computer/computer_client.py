import asyncio
import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from astrbot.api import logger
from astrbot.core.computer.cua_registry import CuaSandboxRegistry
from astrbot.core.computer.cua_sandbox_provider import CuaSandboxProvider
from astrbot.core.computer.sandbox_manager import SANDBOX_LEASE_SECONDS, SandboxManager
from astrbot.core.skills.skill_manager import SANDBOX_SKILLS_ROOT, SkillManager
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_skills_path,
    get_astrbot_temp_path,
)

from .booters.base import ComputerBooter
from .booters.local import LocalBooter

session_booter: dict[str, ComputerBooter] = {}
local_booter: ComputerBooter | None = None
_MANAGED_SKILLS_FILE = ".astrbot_managed_skills.json"
cua_registry = CuaSandboxRegistry()
CUA_LEASE_SECONDS = SANDBOX_LEASE_SECONDS
_cua_boot_locks: dict[str, asyncio.Lock] = {}


@dataclass(slots=True)
class _CUAIdleState:
    expires_at: float
    task: asyncio.Task


cua_idle_state: dict[str, _CUAIdleState] = {}


sandbox_manager: SandboxManager


def _sync_sandbox_manager_refs() -> None:
    sandbox_manager.registry = cua_registry
    sandbox_manager.session_booter = session_booter
    sandbox_manager.idle_state = cua_idle_state
    sandbox_manager.boot_locks = _cua_boot_locks


def _save_cua_registry() -> None:
    _sync_sandbox_manager_refs()
    sandbox_manager.save_registry()


def _get_cua_idle_timeout(context: Context, session_id: str) -> float:
    _sync_sandbox_manager_refs()
    return sandbox_manager.providers["cua"].get_idle_timeout(context, session_id)


def _clear_cua_idle_state(sandbox_id: str) -> None:
    _sync_sandbox_manager_refs()
    sandbox_manager.clear_idle_state(sandbox_id)


def _cua_boot_lock(sandbox_id: str) -> asyncio.Lock:
    _sync_sandbox_manager_refs()
    return sandbox_manager._sandbox_boot_lock(sandbox_id)


def _drop_cua_boot_lock(sandbox_id: str) -> None:
    _sync_sandbox_manager_refs()
    sandbox_manager.drop_boot_lock(sandbox_id)


def _schedule_cua_idle_cleanup(sandbox_id: str, timeout: float) -> None:
    _sync_sandbox_manager_refs()
    sandbox_manager.schedule_idle_cleanup(sandbox_id, timeout)


def _cua_sandbox_has_active_lease(sandbox_id: str) -> bool:
    _sync_sandbox_manager_refs()
    return sandbox_manager.sandbox_has_active_lease(sandbox_id)


def _cua_sandbox_controlled_by_other_session(sandbox_id: str, session_id: str) -> bool:
    _sync_sandbox_manager_refs()
    return sandbox_manager.sandbox_controlled_by_other_session(sandbox_id, session_id)


def _acquire_cua_sandbox_lease(sandbox_id: str, session_id: str) -> bool:
    _sync_sandbox_manager_refs()
    return sandbox_manager.acquire_lease(sandbox_id, session_id)


async def _booter_available(booter: ComputerBooter) -> bool:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.booter_available(booter)


def renew_cua_sandbox_lease(sandbox_id: str, session_id: str, *, ttl: float) -> bool:
    _sync_sandbox_manager_refs()
    return sandbox_manager.acquire_lease(sandbox_id, session_id, ttl=ttl)


async def _boot_managed_cua_sandbox(
    context: Context,
    session_id: str,
    sandbox_id: str,
    cua_kwargs: dict,
) -> ComputerBooter:
    from .booters.cua import CuaBooter

    uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
    client = CuaBooter(**cua_kwargs)
    started_at = time.monotonic()
    logger.info(
        "[Computer] CUA managed sandbox boot start: sandbox_id=%s session_id=%s boot_session_id=%s image=%s os_type=%s local=%s ttl=%s",
        sandbox_id,
        session_id,
        uuid_str,
        cua_kwargs.get("image"),
        cua_kwargs.get("os_type"),
        cua_kwargs.get("local"),
        cua_kwargs.get("ttl"),
    )
    try:
        await client.boot(uuid_str)
        logger.info(
            "[Computer] CUA managed sandbox boot connected: sandbox_id=%s session_id=%s elapsed_ms=%d",
            sandbox_id,
            session_id,
            int((time.monotonic() - started_at) * 1000),
        )
        await _sync_skills_to_sandbox(client)
    except Exception:
        logger.warning(
            "[Computer] CUA managed sandbox boot failed: sandbox_id=%s session_id=%s elapsed_ms=%d",
            sandbox_id,
            session_id,
            int((time.monotonic() - started_at) * 1000),
            exc_info=True,
        )
        try:
            await client.shutdown()
        except Exception as shutdown_error:
            logger.warning(
                "Failed to shutdown sandbox after boot error for session %s: %s",
                session_id,
                shutdown_error,
            )
        raise
    logger.info(
        "[Computer] CUA managed sandbox boot done: sandbox_id=%s session_id=%s elapsed_ms=%d",
        sandbox_id,
        session_id,
        int((time.monotonic() - started_at) * 1000),
    )
    return client


async def _boot_managed_cua_sandbox_hook(
    context: Context,
    session_id: str,
    sandbox_id: str,
    cua_kwargs: dict,
) -> ComputerBooter:
    return await _boot_managed_cua_sandbox(context, session_id, sandbox_id, cua_kwargs)


sandbox_manager = SandboxManager(
    registry=cua_registry,
    providers={"cua": CuaSandboxProvider(boot_hook=_boot_managed_cua_sandbox_hook)},
)
_sync_sandbox_manager_refs()


async def _get_or_create_cua_booter(
    context: Context, session_id: str, sandbox_cfg: dict
) -> ComputerBooter:
    _sync_sandbox_manager_refs()
    _ = sandbox_cfg
    config = sandbox_manager.providers["cua"].build_create_config(context, session_id)
    logger.info(
        f"[Computer] CUA config: image={config['image']}, "
        f"os_type={config['os_type']}, ttl={config['ttl']}"
    )
    return await sandbox_manager.get_or_create_booter(context, session_id, "cua")


async def create_cua_sandbox(
    context: Context,
    session_id: str,
    sandbox_name: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.create_sandbox(
        context, session_id, "cua", sandbox_name
    )


async def create_sandbox(
    context: Context,
    session_id: str,
    provider: str = "cua",
    sandbox_name: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.create_sandbox(
        context, session_id, provider, sandbox_name
    )


async def create_cua_sandbox_uncontrolled(
    context: Context,
    session_id: str,
    sandbox_name: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.create_sandbox_uncontrolled(
        context, session_id, "cua", sandbox_name
    )


async def create_sandbox_uncontrolled(
    context: Context,
    session_id: str,
    provider: str = "cua",
    sandbox_name: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.create_sandbox_uncontrolled(
        context, session_id, provider, sandbox_name
    )


def list_cua_sandboxes() -> list[dict]:
    _sync_sandbox_manager_refs()
    return sandbox_manager.list_sandboxes()


def list_sandboxes() -> list[dict]:
    _sync_sandbox_manager_refs()
    return sandbox_manager.list_sandboxes()


def set_default_cua_sandbox(sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.set_default_sandbox(sandbox_id)


def set_default_sandbox(sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.set_default_sandbox(sandbox_id)


def update_cua_sandbox_config(
    sandbox_id: str,
    *,
    sandbox_name: str | None = None,
    idle_timeout: int | float | None,
    expires_at: int | float | None,
    retention_policy: str,
) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.update_sandbox_config(
        sandbox_id,
        sandbox_name=sandbox_name,
        idle_timeout=idle_timeout,
        expires_at=expires_at,
        retention_policy=retention_policy,
    )


def update_sandbox_config(
    sandbox_id: str,
    *,
    sandbox_name: str | None = None,
    idle_timeout: int | float | None,
    expires_at: int | float | None,
    retention_policy: str,
) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.update_sandbox_config(
        sandbox_id,
        sandbox_name=sandbox_name,
        idle_timeout=idle_timeout,
        expires_at=expires_at,
        retention_policy=retention_policy,
    )


async def reconcile_cua_sandboxes_on_startup() -> None:
    _sync_sandbox_manager_refs()
    await sandbox_manager.reconcile_on_startup()


async def cleanup_managed_cua_sandboxes() -> None:
    _sync_sandbox_manager_refs()
    await sandbox_manager.cleanup_managed_sandboxes()


def get_current_cua_sandbox(session_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.get_current_sandbox(session_id)


def get_current_sandbox(session_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.get_current_sandbox(session_id)


def switch_current_cua_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.switch_current_sandbox(session_id, sandbox_id)


async def switch_current_cua_sandbox_checked(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.switch_current_sandbox_checked(session_id, sandbox_id)


def switch_current_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.switch_current_sandbox(session_id, sandbox_id)


async def switch_current_sandbox_checked(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.switch_current_sandbox_checked(session_id, sandbox_id)


def release_current_cua_sandbox(
    session_id: str,
    sandbox_id: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.release_current_sandbox(session_id, sandbox_id)


def release_current_sandbox(
    session_id: str,
    sandbox_id: str | None = None,
) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.release_current_sandbox(session_id, sandbox_id)


def takeover_cua_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.takeover_sandbox(session_id, sandbox_id)


def takeover_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return sandbox_manager.takeover_sandbox(session_id, sandbox_id)


async def destroy_cua_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.destroy_sandbox(session_id, sandbox_id)


async def destroy_sandbox(session_id: str, sandbox_id: str) -> dict:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.destroy_sandbox(session_id, sandbox_id)


async def get_cua_sandbox_observer_booter_by_id(sandbox_id: str) -> ComputerBooter:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.get_observer_booter_by_id(sandbox_id)


async def get_sandbox_observer_booter_by_id(sandbox_id: str) -> ComputerBooter:
    _sync_sandbox_manager_refs()
    return await sandbox_manager.get_observer_booter_by_id(sandbox_id)


async def copy_file_between_cua_sandboxes(
    *,
    session_id: str,
    source_sandbox_id: str,
    source_path: str,
    target_sandbox_id: str,
    target_path: str,
    temp_dir: str | Path | None = None,
) -> dict:
    source_record = cua_registry.get_sandbox(source_sandbox_id)
    if source_record is None or not source_record.get("managed"):
        raise RuntimeError(f"Source sandbox {source_sandbox_id} not found")
    target_record = cua_registry.get_sandbox(target_sandbox_id)
    if target_record is None or not target_record.get("managed"):
        raise RuntimeError(f"Target sandbox {target_sandbox_id} not found")
    if not _acquire_cua_sandbox_lease(target_sandbox_id, session_id):
        raise RuntimeError(f"Target sandbox {target_sandbox_id} is busy")

    source_booter = session_booter.get(source_sandbox_id)
    target_booter = session_booter.get(target_sandbox_id)
    if source_booter is None or not await _booter_available(source_booter):
        raise RuntimeError(f"Source sandbox {source_sandbox_id} is not running")
    if target_booter is None or not await _booter_available(target_booter):
        raise RuntimeError(f"Target sandbox {target_sandbox_id} is not running")

    relay_root = (
        Path(temp_dir) if temp_dir is not None else Path(get_astrbot_temp_path())
    )
    relay_root.mkdir(parents=True, exist_ok=True)
    fd, relay_path = tempfile.mkstemp(
        prefix="cua-relay-", suffix=".tmp", dir=relay_root
    )
    os.close(fd)
    relay_file = Path(relay_path)
    try:
        await source_booter.download_file(source_path, str(relay_file))
        upload_result = await target_booter.upload_file(str(relay_file), target_path)
        if not upload_result.get("success", False):
            raise RuntimeError(str(upload_result.get("message") or "upload failed"))
        cua_registry.touch_sandbox(source_sandbox_id)
        cua_registry.touch_sandbox(target_sandbox_id)
        _save_cua_registry()
        return {
            "source_sandbox_id": source_sandbox_id,
            "source_path": source_path,
            "target_sandbox_id": target_sandbox_id,
            "target_path": target_path,
            "upload": upload_result,
        }
    finally:
        relay_file.unlink(missing_ok=True)


async def get_cua_observer_booter(context: Context, session_id: str) -> ComputerBooter:
    config = context.get_config(umo=session_id)
    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    current_sandbox_id = cua_registry.get_current_sandbox_id(session_id)
    if current_sandbox_id is None:
        return await _get_or_create_cua_booter(context, session_id, sandbox_cfg)
    booter = session_booter.get(current_sandbox_id)
    if booter is None or not await _booter_available(booter):
        booter = await _get_or_create_cua_booter(context, session_id, sandbox_cfg)
        current_sandbox_id = getattr(booter, "sandbox_id", current_sandbox_id)
    cua_registry.touch_sandbox(current_sandbox_id)
    _save_cua_registry()
    _schedule_cua_idle_cleanup(
        current_sandbox_id,
        _get_cua_idle_timeout(context, session_id),
    )
    return booter


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

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard_neo")

    if booter_type == "cua":
        return await _get_or_create_cua_booter(context, session_id, sandbox_cfg)

    if session_id in session_booter:
        booter = session_booter[session_id]
        if not await booter.available():
            # Clean up old booter before rebuilding so sandbox resources
            # on Bay (containers, volumes, networks) are not leaked.
            # Only ShipyardNeoBooter supports delete_sandbox; other booters
            # (local, boxlite, cua, etc.) are not backed by a remote sandbox
            # manager and don't need it.
            try:
                if booter_type == "shipyard_neo":
                    await booter.shutdown(delete_sandbox=True)
                else:
                    await booter.shutdown()
            except Exception as shutdown_err:
                logger.warning(
                    "[Computer] Error shutting down stale booter for session %s: %s",
                    session_id,
                    shutdown_err,
                )
            session_booter.pop(session_id, None)
    if session_id not in session_booter:
        uuid_str = uuid.uuid5(uuid.NAMESPACE_DNS, session_id).hex
        logger.info(
            f"[Computer] Initializing booter: type={booter_type}, session={session_id}"
        )
        if booter_type == "shipyard":
            from .booters.shipyard import ShipyardBooter

            ep = sandbox_cfg.get("shipyard_endpoint", "")
            token = sandbox_cfg.get("shipyard_access_token", "")
            ttl = sandbox_cfg.get("shipyard_ttl", 3600)
            max_sessions = sandbox_cfg.get("shipyard_max_sessions", 10)

            client = ShipyardBooter(
                endpoint_url=ep, access_token=token, ttl=ttl, session_num=max_sessions
            )
        elif booter_type == "shipyard_neo":
            from .booters.shipyard_neo import ShipyardNeoBooter

            ep = sandbox_cfg.get("shipyard_neo_endpoint", "")
            token = sandbox_cfg.get("shipyard_neo_access_token", "")
            ttl = sandbox_cfg.get("shipyard_neo_ttl", 3600)
            profile = sandbox_cfg.get("shipyard_neo_profile", "python-default")

            # Auto-discover token from Bay's credentials.json if not configured
            if not token:
                token = _discover_bay_credentials(ep)

            logger.info(
                f"[Computer] Shipyard Neo config: endpoint={ep}, profile={profile}, ttl={ttl}"
            )
            client = ShipyardNeoBooter(
                endpoint_url=ep,
                access_token=token,
                profile=profile,
                ttl=ttl,
            )
        elif booter_type == "cua":
            from .booters.cua import CuaBooter, build_cua_booter_kwargs

            cua_kwargs = build_cua_booter_kwargs(sandbox_cfg)
            logger.info(
                f"[Computer] CUA config: image={cua_kwargs['image']}, "
                f"os_type={cua_kwargs['os_type']}, ttl={cua_kwargs['ttl']}"
            )
            client = CuaBooter(**cua_kwargs)
        elif booter_type == "boxlite":
            from .booters.boxlite import BoxliteBooter

            client = BoxliteBooter()
        else:
            raise ValueError(f"Unknown booter type: {booter_type}")

        try:
            await client.boot(uuid_str)
            logger.info(
                f"[Computer] Sandbox booted successfully: type={booter_type}, session={session_id}"
            )
            await _sync_skills_to_sandbox(client)
        except Exception as e:
            logger.error(f"Error booting sandbox for session {session_id}: {e}")
            try:
                if booter_type == "shipyard_neo":
                    await client.shutdown(delete_sandbox=True)
                else:
                    await client.shutdown()
            except Exception as shutdown_error:
                logger.warning(
                    "Failed to shutdown sandbox after boot error for session %s: %s",
                    session_id,
                    shutdown_error,
                )
            raise e

        session_booter[session_id] = client
    return session_booter[session_id]


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
    return local_booter
