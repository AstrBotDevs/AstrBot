from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp

from astrbot.core import logger
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.context import Context
from astrbot.core.star.plugin_search import (
    search_plugin_market_records,
    search_plugin_records,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path, get_astrbot_temp_path

from .model import ExtensionKind, InstallCandidate
from .orchestrator import ExtensionAdapter


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_ssh_git_url(value: str) -> bool:
    if value.startswith("git@"):
        host_path = value.split("@", maxsplit=1)[-1]
        return ":" in host_path and "/" in host_path
    parsed = urlparse(value)
    return parsed.scheme in {"ssh", "git"} and bool(parsed.netloc)


def _is_git_repository_locator(value: str) -> bool:
    return _is_http_url(value) or _is_ssh_git_url(value)


def _candidate_match(text: str, query: str) -> bool:
    if not query:
        return True
    return query.lower() in text.lower()


class PluginAdapter(ExtensionAdapter):
    kind = ExtensionKind.PLUGIN
    provider = "git"

    def __init__(self, context: Context) -> None:
        self.context = context

    def _get_market_cache_candidates(self, query: str) -> list[InstallCandidate]:
        cache_path = Path(get_astrbot_data_path()) / "plugins.json"
        if not cache_path.exists():
            return []
        try:
            cache_obj = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to parse plugin market cache: %s", exc)
            return []

        raw_data: Any = cache_obj.get("data", cache_obj)
        if not isinstance(raw_data, (dict, list)):
            logger.warning(
                "Unexpected plugin market cache format: data_type=%s path=%s",
                type(raw_data).__name__,
                cache_path,
            )
            return []

        candidates: list[InstallCandidate] = []
        matched_records = search_plugin_market_records(raw_data, query)
        for item in matched_records:
            name = str(item.get("name", "") or item.get("display_name", "")).strip()
            desc = str(item.get("desc", "") or item.get("description", "")).strip()
            repo = str(item.get("repo", "")).strip()
            author = str(item.get("author", "")).strip()
            identifier = repo or name
            if not identifier:
                continue
            keyword_blob = " ".join([name, desc, repo, author]).strip()
            if not _candidate_match(keyword_blob, query):
                continue
            candidates.append(
                InstallCandidate(
                    kind=self.kind,
                    provider=self.provider,
                    identifier=identifier,
                    name=name or identifier,
                    description=desc,
                    version=str(item.get("version", "")),
                    source="plugin_market_cache",
                    install_payload={
                        "repo": repo or identifier,
                        "author": author,
                    },
                )
            )
        logger.debug(
            "Loaded plugin market cache candidates: total_items=%d matched=%d query=%s",
            len(raw_data),
            len(candidates),
            query,
        )
        return candidates

    async def search(self, query: str) -> list[InstallCandidate]:
        installed_records = []
        for plugin in self.context.get_all_stars():
            repo = plugin.repo or ""
            if not repo:
                continue
            installed_records.append(
                {
                    "name": plugin.name,
                    "display_name": getattr(plugin, "display_name", "") or "",
                    "desc": plugin.desc,
                    "author": plugin.author,
                    "repo": repo,
                    "version": plugin.version,
                    "source": "installed",
                }
            )

        installed_matches = search_plugin_records(installed_records, query)
        seen = {
            (
                self.provider,
                str(item.get("repo", "") or item.get("name", "")),
            )
            for item in installed_matches
        }
        candidates: list[InstallCandidate] = []
        for candidate in self._get_market_cache_candidates(query):
            key = (candidate.provider, candidate.identifier)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)

        return candidates

    async def install(self, candidate: InstallCandidate) -> dict[str, Any]:
        plugin_manager = self.context._star_manager  # noqa: SLF001
        if plugin_manager is None:
            raise RuntimeError("plugin manager is not initialized")

        metadata = dict(candidate.install_payload.get("metadata", {}))
        repo_url = (
            str(candidate.install_payload.get("repo", "")).strip()
            or candidate.identifier
        )
        if not _is_git_repository_locator(repo_url):
            raise ValueError("plugin install target must be a git repository URL")

        plugin_info = await plugin_manager.install_plugin(
            repo_url=repo_url,
            proxy=str(metadata.get("proxy", "") or ""),
            ignore_version_check=bool(metadata.get("ignore_version_check", False)),
        )
        return {
            "kind": self.kind.value,
            "provider": self.provider,
            "target": repo_url,
            "plugin_info": plugin_info or {},
        }


class SkillAdapter(ExtensionAdapter):
    kind = ExtensionKind.SKILL
    provider = "local"

    def __init__(self, context: Context) -> None:
        self.context = context
        self.skill_manager = SkillManager()

    async def search(self, query: str) -> list[InstallCandidate]:
        skills = self.skill_manager.list_skills(
            active_only=False,
            runtime="local",
            show_sandbox_path=False,
        )
        candidates: list[InstallCandidate] = []
        for skill in skills:
            blob = " ".join([skill.name, skill.description, skill.path])
            if not _candidate_match(blob, query):
                continue
            candidates.append(
                InstallCandidate(
                    kind=self.kind,
                    provider=self.provider,
                    identifier=skill.name,
                    name=skill.name,
                    description=skill.description,
                    source="local_skill",
                    install_payload={"skill_name": skill.name, "path": skill.path},
                )
            )
        return candidates

    async def _download_zip(self, url: str) -> Path:
        temp_dir = Path(get_astrbot_temp_path())
        temp_dir.mkdir(parents=True, exist_ok=True)
        dest = (
            temp_dir
            / f"skill_install_{os.getpid()}_{Path(urlparse(url).path).name or 'skill.zip'}"
        )
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                content = await response.read()
                dest.write_bytes(content)
        return dest

    async def install(self, candidate: InstallCandidate) -> dict[str, Any]:
        metadata = dict(candidate.install_payload.get("metadata", {}))
        target = (
            str(candidate.install_payload.get("target", "")).strip()
            or candidate.identifier
        )
        target_path = Path(target)

        if candidate.source == "local_skill":
            self.skill_manager.set_skill_active(candidate.identifier, True)
            return {
                "kind": self.kind.value,
                "provider": self.provider,
                "target": candidate.identifier,
                "skill_name": candidate.identifier,
                "status": "activated",
            }

        zip_path: Path | None = None
        if target_path.exists():
            zip_path = target_path
        elif _is_http_url(target):
            zip_path = await self._download_zip(target)
        else:
            fallback = str(metadata.get("zip_path", "")).strip()
            if fallback:
                zip_path = Path(fallback)

        if zip_path is None or not zip_path.exists():
            raise FileNotFoundError(
                "skill install target must be an existing zip path or HTTP URL"
            )

        try:
            skill_name = self.skill_manager.install_skill_from_zip(
                str(zip_path),
                overwrite=True,
            )
            return {
                "kind": self.kind.value,
                "provider": self.provider,
                "target": str(zip_path),
                "skill_name": skill_name,
                "status": "installed",
            }
        finally:
            if _is_http_url(target) and zip_path.exists():
                try:
                    zip_path.unlink()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to cleanup downloaded skill zip %s: %s", zip_path, exc
                    )


class McpTodoAdapter(ExtensionAdapter):
    kind = ExtensionKind.MCP
    provider = "todo"

    async def search(self, query: str) -> list[InstallCandidate]:
        _ = query
        return []

    async def install(self, candidate: InstallCandidate) -> dict[str, Any]:
        _ = candidate
        raise NotImplementedError(
            "TODO: MCP auto install is reserved for a later version."
        )
