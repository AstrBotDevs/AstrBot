import json
import shutil
import uuid
from pathlib import Path

from astrbot.api import logger
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


def _list_local_skill_dirs(skills_root: Path) -> list[Path]:
    skills: list[Path] = []
    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            skills.append(entry)
    return skills


def _discover_bay_credentials(endpoint: str) -> str:
    """Try to auto-discover Bay API key from credentials.json.

    Search order:
    1. BAY_DATA_DIR env var
    2. Mono-repo relative path: ../pkgs/bay/ (dev layout)
    3. Current working directory

    Returns:
        API key string, or empty string if not found.
    """
    import os

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
                logger.info(
                    "[Computer] Auto-discovered Bay API key from %s (prefix=%s)",
                    cred_path,
                    api_key[:12] + "..." if len(api_key) > 12 else api_key,
                )
                return api_key
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("[Computer] Failed to read %s: %s", cred_path, exc)

    logger.debug("[Computer] No Bay credentials.json found in search paths")
    return ""


def _build_sync_and_scan_command() -> str:
    script = f"""
import json
import shutil
import zipfile
from pathlib import Path

root = Path({SANDBOX_SKILLS_ROOT!r})
zip_path = root / "skills.zip"
tmp_extract = Path(f"{{root}}_tmp_extract")
managed_file = root / {_MANAGED_SKILLS_FILE!r}


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
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip().lower() == "description":
            return value.strip().strip('"').strip("'")
    return ""


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
                "path": f"{SANDBOX_SKILLS_ROOT}/{{skill_dir.name}}/SKILL.md",
            }}
        )
    return skills


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
print(
    json.dumps(
        {{
            "managed_skills": current_managed,
            "skills": collect_skills(),
        }},
        ensure_ascii=False,
    )
)
""".strip()
    return (
        "if command -v python3 >/dev/null 2>&1; then PYBIN=python3; "
        "elif command -v python >/dev/null 2>&1; then PYBIN=python; "
        "else echo 'python not found in sandbox' >&2; exit 127; fi; "
        "$PYBIN - <<'PY'\n"
        f"{script}\n"
        "PY"
    )


def _shell_exec_succeeded(result: dict) -> bool:
    if "success" in result:
        return bool(result.get("success"))
    exit_code = result.get("exit_code")
    return exit_code in (0, None)


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


async def _sync_skills_to_sandbox(booter: ComputerBooter) -> None:
    skills_root = Path(get_astrbot_skills_path())
    if not skills_root.is_dir():
        return
    local_skill_dirs = _list_local_skill_dirs(skills_root)

    temp_dir = Path(get_astrbot_temp_path())
    temp_dir.mkdir(parents=True, exist_ok=True)
    zip_base = temp_dir / "skills_bundle"
    zip_path = zip_base.with_suffix(".zip")

    try:
        if local_skill_dirs:
            if zip_path.exists():
                zip_path.unlink()
            shutil.make_archive(str(zip_base), "zip", str(skills_root))
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

        sync_result = await booter.shell.exec(_build_sync_and_scan_command())
        if not _shell_exec_succeeded(sync_result):
            raise RuntimeError(
                "Failed to apply sandbox skill sync strategy: "
                f"stderr={sync_result.get('stderr', '')}"
            )
        payload = _decode_sync_payload(str(sync_result.get("stdout", "") or ""))
        _update_sandbox_skills_cache(payload)
        managed = payload.get("managed_skills", []) if isinstance(payload, dict) else []
        logger.info(
            "[Computer] Sandbox skill sync complete: managed=%d",
            len(managed),
        )
    finally:
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

    sandbox_cfg = config.get("provider_settings", {}).get("sandbox", {})
    booter_type = sandbox_cfg.get("booter", "shipyard_neo")

    if session_id in session_booter:
        booter = session_booter[session_id]
        if not await booter.available():
            # rebuild
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
