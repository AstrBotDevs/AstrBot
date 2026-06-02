from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrbot.core.computer.computer_client import sync_skills_to_active_sandboxes
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.utils.astrbot_path import get_astrbot_skills_path

_MAP_VERSION = 1
_MAP_FILE_NAME = "neo_skill_map.json"
_SKILL_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_jsonable(model_like: Any) -> dict[str, Any]:
    if isinstance(model_like, dict):
        return model_like
    if hasattr(model_like, "model_dump"):
        dumped = model_like.model_dump()
        if isinstance(dumped, dict):
            return dumped
    return {}


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, text

    data: dict[str, str] = {}
    for line in lines[1:end_idx]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip('"').strip("'")
        if key in {"name", "description"} and value:
            data[key] = value

    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return data, body


def _derive_description(markdown_body: str) -> str:
    lines = markdown_body.splitlines()

    heading_idx = None
    for i, line in enumerate(lines):
        normalized = line.strip().lower()
        if normalized in {"## 描述", "## description"}:
            heading_idx = i
            break

    if heading_idx is not None:
        for line in lines[heading_idx + 1 :]:
            text = line.strip()
            if not text:
                continue
            if text.startswith("#"):
                break
            return text

    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        return text

    return ""


def _ensure_skill_frontmatter(markdown: str, *, skill_name: str, skill_key: str) -> str:
    frontmatter, body = _parse_frontmatter(markdown)

    name = frontmatter.get("name") or skill_name
    name = " ".join(str(name).split())
    description = frontmatter.get("description") or _derive_description(body)
    if not description:
        description = f"Synced skill for `{skill_key}`."

    description = " ".join(description.split())

    header = f"---\nname: {name}\ndescription: {description}\n---\n\n"
    body = body.strip("\n")
    return f"{header}{body}\n"


@dataclass
class NeoSkillSyncResult:
    skill_key: str
    local_skill_name: str
    release_id: str
    candidate_id: str
    payload_ref: str
    map_path: str
    synced_at: str


class NeoSkillSyncManager:
    @staticmethod
    def sync_result_to_dict(result: NeoSkillSyncResult) -> dict[str, str]:
        return {
            "skill_key": result.skill_key,
            "local_skill_name": result.local_skill_name,
            "release_id": result.release_id,
            "candidate_id": result.candidate_id,
            "payload_ref": result.payload_ref,
            "map_path": result.map_path,
            "synced_at": result.synced_at,
        }

    def __init__(
        self,
        *,
        skills_root: str | None = None,
        map_path: str | None = None,
    ) -> None:
        self.skills_root = skills_root or get_astrbot_skills_path()
        self.map_path = map_path or str(Path(self.skills_root) / _MAP_FILE_NAME)
        os.makedirs(self.skills_root, exist_ok=True)

    def _load_map(self) -> dict[str, Any]:
        if not os.path.exists(self.map_path):
            return {"version": _MAP_VERSION, "items": {}}
        try:
            with open(self.map_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"version": _MAP_VERSION, "items": {}}
            items = data.get("items", {})
            if not isinstance(items, dict):
                items = {}
            return {"version": int(data.get("version", _MAP_VERSION)), "items": items}
        except Exception:
            return {"version": _MAP_VERSION, "items": {}}

    def _save_map(self, data: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.map_path), exist_ok=True)
        with open(self.map_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def normalize_skill_name(skill_key: str) -> str:
        normalized = _SKILL_NAME_RE.sub("-", skill_key.strip().lower())
        normalized = normalized.strip("._-")
        if not normalized:
            normalized = "skill"
        return f"neo_{normalized}"

    def _resolve_local_skill_name(self, skill_key: str, mapping: dict[str, Any]) -> str:
        items = mapping.get("items", {})
        if not isinstance(items, dict):
            items = {}
        existing = items.get(skill_key)
        if isinstance(existing, dict):
            local_name = existing.get("local_skill_name")
            if isinstance(local_name, str) and local_name:
                return local_name

        base = self.normalize_skill_name(skill_key)
        used_names = {
            str(v.get("local_skill_name"))
            for v in items.values()
            if isinstance(v, dict) and v.get("local_skill_name")
        }
        if base not in used_names:
            return base
        suffix = hashlib.sha1(skill_key.encode("utf-8")).hexdigest()[:8]
        return f"{base}-{suffix}"

    async def _find_release(self, client: Any, *, release_id: str) -> dict[str, Any]:
        offset = 0
        while True:
            page = await client.skills.list_releases(limit=100, offset=offset)
            page_json = _to_jsonable(page)
            items = page_json.get("items", [])
            if not isinstance(items, list):
                items = []
            for item in items:
                if isinstance(item, dict) and item.get("id") == release_id:
                    return item
            total = int(page_json.get("total", 0) or 0)
            offset += len(items)
            if offset >= total or not items:
                break
        raise ValueError(f"Release not found: {release_id}")

    async def _find_active_stable_release(
        self,
        client: Any,
        *,
        skill_key: str,
    ) -> dict[str, Any]:
        page = await client.skills.list_releases(
            skill_key=skill_key,
            active_only=True,
            stage="stable",
            limit=1,
            offset=0,
        )
        page_json = _to_jsonable(page)
        items = page_json.get("items", [])
        if not isinstance(items, list) or not items:
            raise ValueError(
                f"No active stable release found for skill_key: {skill_key}"
            )
        if not isinstance(items[0], dict):
            raise ValueError("Unexpected release payload format.")
        return items[0]

    async def sync_release(
        self,
        client: Any,
        *,
        release_id: str | None = None,
        skill_key: str | None = None,
        require_stable: bool = True,
    ) -> NeoSkillSyncResult:
        if release_id:
            release = await self._find_release(client, release_id=release_id)
        elif skill_key:
            release = await self._find_active_stable_release(
                client, skill_key=skill_key
            )
        else:
            raise ValueError("release_id or skill_key is required for sync.")

        release_id_val = str(release.get("id") or "")
        release_stage_raw = release.get("stage")
        release_stage_value = getattr(release_stage_raw, "value", release_stage_raw)
        release_stage = str(release_stage_value or "").strip().lower()
        skill_key_val = str(release.get("skill_key") or "")
        candidate_id = str(release.get("candidate_id") or "")

        if not release_id_val or not skill_key_val or not candidate_id:
            raise ValueError("Release payload is incomplete.")
        if require_stable and release_stage != "stable":
            raise ValueError(
                "Only stable releases can be synced to local SKILL.md "
                f"(got: {release_stage_raw})."
            )

        candidate = await client.skills.get_candidate(candidate_id)
        candidate_json = _to_jsonable(candidate)
        payload_ref = candidate_json.get("payload_ref")
        if not isinstance(payload_ref, str) or not payload_ref:
            raise ValueError("Candidate payload_ref is missing.")

        payload_resp = await client.skills.get_payload(payload_ref)
        payload_json = _to_jsonable(payload_resp)
        payload = payload_json.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("Skill payload must be a JSON object.")

        skill_markdown = payload.get("skill_markdown")
        if not isinstance(skill_markdown, str) or not skill_markdown.strip():
            raise ValueError(
                "payload.skill_markdown is required for stable sync to local skill."
            )

        mapping = self._load_map()
        local_skill_name = self._resolve_local_skill_name(skill_key_val, mapping)
        skill_dir = Path(self.skills_root) / local_skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        normalized_markdown = _ensure_skill_frontmatter(
            skill_markdown,
            skill_name=local_skill_name,
            skill_key=skill_key_val,
        )

        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(normalized_markdown, encoding="utf-8")

        items = mapping.setdefault("items", {})
        items[skill_key_val] = {
            "local_skill_name": local_skill_name,
            "latest_release_id": release_id_val,
            "latest_candidate_id": candidate_id,
            "latest_payload_ref": payload_ref,
            "updated_at": _now_iso(),
        }
        mapping["version"] = _MAP_VERSION
        self._save_map(mapping)

        # Ensure local skill is visible to AstrBot skill manager.
        SkillManager().set_skill_active(local_skill_name, True)

        # Best-effort synchronization to active sandboxes.
        await sync_skills_to_active_sandboxes()

        return NeoSkillSyncResult(
            skill_key=skill_key_val,
            local_skill_name=local_skill_name,
            release_id=release_id_val,
            candidate_id=candidate_id,
            payload_ref=payload_ref,
            map_path=self.map_path,
            synced_at=_now_iso(),
        )

    async def promote_with_optional_sync(
        self,
        client: Any,
        *,
        candidate_id: str,
        stage: str,
        sync_to_local: bool,
    ) -> dict[str, Any]:
        release = await client.skills.promote_candidate(candidate_id, stage=stage)
        release_json = _to_jsonable(release)

        sync_json: dict[str, Any] | None = None
        rollback_json: dict[str, Any] | None = None
        sync_error: str | None = None

        if stage == "stable" and sync_to_local:
            try:
                sync_result = await self.sync_release(
                    client,
                    release_id=str(release_json.get("id", "")),
                    require_stable=True,
                )
                sync_json = self.sync_result_to_dict(sync_result)
            except Exception as err:
                sync_error = str(err)
                try:
                    rollback = await client.skills.rollback_release(
                        str(release_json.get("id", ""))
                    )
                    rollback_json = _to_jsonable(rollback)
                except Exception as rollback_err:
                    rollback_msg = str(rollback_err)
                    if "no previous release exists" in rollback_msg.lower():
                        rollback_json = {
                            "skipped": True,
                            "reason": rollback_msg,
                        }
                    else:
                        raise RuntimeError(
                            "stable release synced failed and auto rollback also failed; "
                            f"sync_error={sync_error}; rollback_error={rollback_err}"
                        ) from rollback_err

        return {
            "release": release_json,
            "sync": sync_json,
            "rollback": rollback_json,
            "sync_error": sync_error,
        }
