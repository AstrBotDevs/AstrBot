from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import AstrBotError

from astrbot.core import logger
from astrbot.core.skills.skill_manager import (
    _parse_frontmatter_description,
)
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .runtime_store import (
    SdkHttpRoute,
    SdkPluginRecord,
    SdkRegisteredSkill,
)

if TYPE_CHECKING:
    from .plugin_bridge import SdkPluginBridge


class SdkRegistryManager:
    def __init__(self, *, bridge: SdkPluginBridge) -> None:
        self.bridge = bridge

    def list_plugins(self) -> list[dict[str, Any]]:
        records = sorted(
            self.bridge._records.values(), key=lambda item: item.load_order
        )
        items = [self.bridge._record_to_dashboard_item(record) for record in records]
        for plugin_id, issues in sorted(self.bridge._discovery_issues.items()):
            if plugin_id in self.bridge._records:
                continue
            items.append(self.bridge._failed_issue_to_dashboard_item(plugin_id, issues))
        return items

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, Any] | None:
        record = self.bridge._records.get(plugin_id)
        if record is not None:
            manifest = record.plugin.manifest_data
            support_platforms = manifest.get("support_platforms")
            return {
                "name": plugin_id,
                "display_name": str(manifest.get("display_name") or plugin_id),
                "description": str(
                    manifest.get("desc") or manifest.get("description") or ""
                ),
                "author": str(manifest.get("author") or ""),
                "version": str(manifest.get("version") or "0.0.0"),
                "enabled": record.state not in {"disabled", "failed"},
                "support_platforms": [
                    str(item) for item in support_platforms if isinstance(item, str)
                ]
                if isinstance(support_platforms, list)
                else [],
                "astrbot_version": (
                    str(manifest.get("astrbot_version"))
                    if manifest.get("astrbot_version") is not None
                    else None
                ),
                "runtime_kind": "sdk",
                "issues": [dict(item) for item in record.issues],
            }
        for plugin in self.bridge.star_context.get_all_stars():
            if plugin.name == plugin_id:
                return {
                    "name": plugin.name,
                    "display_name": plugin.display_name,
                    "description": plugin.desc,
                    "author": plugin.author,
                    "version": plugin.version,
                    "enabled": plugin.activated,
                    "support_platforms": list(plugin.support_platforms),
                    "astrbot_version": plugin.astrbot_version,
                    "runtime_kind": "legacy",
                }
        if plugin_id in self.bridge._discovery_issues:
            issue = self.bridge._discovery_issues[plugin_id][0]
            return {
                "name": plugin_id,
                "display_name": plugin_id,
                "description": str(issue.get("message", "")),
                "author": "",
                "version": "0.0.0",
                "enabled": False,
                "support_platforms": [],
                "astrbot_version": None,
                "runtime_kind": "sdk",
                "issues": [
                    dict(item) for item in self.bridge._discovery_issues[plugin_id]
                ],
            }
        return None

    def list_plugin_metadata(self) -> list[dict[str, Any]]:
        metadata = []
        for plugin in self.bridge.star_context.get_all_stars():
            metadata.append(
                {
                    "name": plugin.name,
                    "display_name": plugin.display_name,
                    "description": plugin.desc,
                    "author": plugin.author,
                    "version": plugin.version,
                    "enabled": plugin.activated,
                    "support_platforms": list(plugin.support_platforms),
                    "astrbot_version": plugin.astrbot_version,
                    "runtime_kind": "legacy",
                }
            )
        for plugin_id in sorted(self.bridge._records.keys()):
            plugin_metadata = self.get_plugin_metadata(plugin_id)
            if plugin_metadata is not None:
                metadata.append(plugin_metadata)
        for plugin_id in sorted(self.bridge._discovery_issues.keys()):
            if plugin_id in self.bridge._records:
                continue
            plugin_metadata = self.get_plugin_metadata(plugin_id)
            if plugin_metadata is not None:
                metadata.append(plugin_metadata)
        return metadata

    def register_skill(
        self,
        *,
        plugin_id: str,
        name: str,
        path: str,
        description: str = "",
    ) -> dict[str, str]:
        record = self.bridge._records.get(plugin_id)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown SDK plugin: {plugin_id}")

        skill_name = str(name).strip()
        if not skill_name or not self.bridge.SDK_SKILL_NAME_RE.fullmatch(skill_name):
            raise AstrBotError.invalid_input(
                "skill.register requires a name matching [A-Za-z0-9._-]+"
            )

        path_text = str(path).strip()
        if not path_text:
            raise AstrBotError.invalid_input("skill.register requires path")

        plugin_root = record.plugin.plugin_dir.resolve()
        requested_path = Path(path_text)
        resolved_path = (
            requested_path.resolve()
            if requested_path.is_absolute()
            else (plugin_root / requested_path).resolve()
        )

        skill_dir = resolved_path if resolved_path.is_dir() else resolved_path.parent
        skill_md_path = (
            resolved_path / "SKILL.md" if resolved_path.is_dir() else resolved_path
        )
        if skill_md_path.name != "SKILL.md" or not skill_md_path.is_file():
            raise AstrBotError.invalid_input(
                "skill.register path must point to a skill directory containing SKILL.md or to SKILL.md itself"
            )
        if not skill_dir.is_dir():
            raise AstrBotError.invalid_input(
                "skill.register resolved skill_dir is not a directory"
            )
        if not skill_md_path.is_relative_to(plugin_root):
            raise AstrBotError.invalid_input(
                "skill.register path must stay inside the plugin directory"
            )

        normalized_description = str(description).strip()
        if not normalized_description:
            try:
                normalized_description = _parse_frontmatter_description(
                    skill_md_path.read_text(encoding="utf-8")
                )
            except Exception:
                normalized_description = ""

        record.skills[skill_name] = SdkRegisteredSkill(
            name=skill_name,
            description=normalized_description,
            skill_dir=skill_dir,
            skill_md_path=skill_md_path,
        )
        self.bridge._publish_plugin_skills(plugin_id)
        return {
            "name": skill_name,
            "description": normalized_description,
            "path": str(skill_md_path),
            "skill_dir": str(skill_dir),
        }

    def unregister_skill(self, *, plugin_id: str, name: str) -> bool:
        record = self.bridge._records.get(plugin_id)
        if record is None:
            raise AstrBotError.invalid_input(f"Unknown SDK plugin: {plugin_id}")
        removed = record.skills.pop(str(name).strip(), None) is not None
        if removed:
            self.bridge._publish_plugin_skills(plugin_id)
        return removed

    def list_registered_skills(self, plugin_id: str) -> list[dict[str, str]]:
        record = self.bridge._records.get(plugin_id)
        if record is None:
            return []
        return [
            record.skills[name].to_registry_payload()
            for name in sorted(record.skills.keys())
        ]

    def publish_plugin_skills_impl(self, plugin_id: str) -> None:
        record = self.bridge._records.get(plugin_id)
        manager = self.bridge._make_skill_manager()
        if record is None or not record.skills:
            manager.remove_sdk_plugin_skills(plugin_id)
            return
        manager.replace_sdk_plugin_skills(
            plugin_id,
            [skill.to_registry_payload() for skill in record.skills.values()],
        )

    async def clear_plugin_skills(
        self,
        *,
        plugin_id: str,
        record: SdkPluginRecord | Any | None,
        reason: str,
    ) -> None:
        if record is None or not getattr(record, "skills", None):
            return
        record.skills.clear()
        self.bridge._publish_plugin_skills(plugin_id)
        try:
            from astrbot.core.computer.computer_client import (
                sync_skills_to_active_sandboxes,
            )

            await sync_skills_to_active_sandboxes()
        except Exception as exc:
            logger.warning(
                "Failed to sync skills after SDK plugin %s %s: %s",
                plugin_id,
                reason,
                exc,
            )

    def register_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
        handler_capability: str,
        description: str,
    ) -> None:
        normalized_route = self.bridge._normalize_http_route(route)
        normalized_methods = self.bridge._normalize_http_methods(methods)
        if not handler_capability:
            raise AstrBotError.invalid_input(
                "http.register_api requires handler_capability"
            )
        self.bridge._ensure_http_route_available(
            plugin_id=plugin_id,
            route=normalized_route,
            methods=normalized_methods,
        )
        route_entry = SdkHttpRoute(
            plugin_id=plugin_id,
            route=normalized_route,
            methods=normalized_methods,
            handler_capability=handler_capability,
            description=description,
        )
        plugin_routes = [
            entry
            for entry in self.bridge._http_routes.get(plugin_id, [])
            if not (
                entry.route == normalized_route and entry.methods == normalized_methods
            )
        ]
        plugin_routes.append(route_entry)
        self.bridge._http_routes[plugin_id] = plugin_routes
        logger.info(
            "SDK HTTP route registered: plugin=%s route=%s methods=%s handler=%s",
            plugin_id,
            route_entry.route,
            ",".join(route_entry.methods),
            handler_capability,
        )

    def unregister_http_api(
        self,
        *,
        plugin_id: str,
        route: str,
        methods: list[str],
    ) -> None:
        normalized_route = self.bridge._normalize_http_route(route)
        normalized_methods = {method.upper() for method in methods if method}
        updated: list[SdkHttpRoute] = []
        for entry in self.bridge._http_routes.get(plugin_id, []):
            if entry.route != normalized_route:
                updated.append(entry)
                continue
            if not normalized_methods:
                continue
            remaining = tuple(
                method for method in entry.methods if method not in normalized_methods
            )
            if remaining:
                updated.append(
                    SdkHttpRoute(
                        plugin_id=entry.plugin_id,
                        route=entry.route,
                        methods=remaining,
                        handler_capability=entry.handler_capability,
                        description=entry.description,
                    )
                )
        if updated:
            self.bridge._http_routes[plugin_id] = updated
        else:
            self.bridge._http_routes.pop(plugin_id, None)

    def list_http_apis(self, plugin_id: str) -> list[dict[str, Any]]:
        return [
            {
                "route": entry.route,
                "methods": list(entry.methods),
                "handler_capability": entry.handler_capability,
                "description": entry.description,
            }
            for entry in self.bridge._http_routes.get(plugin_id, [])
        ]

    def dashboard_public_base_url(self) -> str:
        dashboard_config_source = self.bridge._get_dashboard_config()
        dashboard_config = dashboard_config_source.get("dashboard", {})
        if not isinstance(dashboard_config, dict):
            dashboard_config = {}
        ssl_config = dashboard_config.get("ssl", {})
        if not isinstance(ssl_config, dict):
            ssl_config = {}

        port = (
            os.environ.get("DASHBOARD_PORT")
            or os.environ.get("ASTRBOT_DASHBOARD_PORT")
            or dashboard_config.get("port", 6185)
        )
        host = (
            os.environ.get("DASHBOARD_HOST")
            or os.environ.get("ASTRBOT_DASHBOARD_HOST")
            or dashboard_config.get("host", "0.0.0.0")
        )
        ssl_enabled = self.bridge._parse_env_bool(
            os.environ.get("DASHBOARD_SSL_ENABLE")
            or os.environ.get("ASTRBOT_DASHBOARD_SSL_ENABLE"),
            bool(ssl_config.get("enable", False)),
        )
        scheme = "https" if ssl_enabled else "http"
        host_text = str(host).strip() or "localhost"
        if host_text in {"0.0.0.0", "::", "[::]"}:
            host_text = "localhost"
        if ":" in host_text and not host_text.startswith("["):
            host_text = f"[{host_text}]"
        return f"{scheme}://{host_text}:{int(port)}"

    async def dispatch_http_request(
        self,
        route: str,
        method: str,
    ) -> dict[str, Any] | None:
        resolved = self.bridge._resolve_http_route(route, method)
        if resolved is None:
            return None
        record, route_entry = resolved
        if record.session is None:
            raise AstrBotError.invalid_input("SDK HTTP route worker is unavailable")
        from quart import request as quart_request

        text_body = await quart_request.get_data(as_text=True)
        form_payload = (await quart_request.form).to_dict(flat=False)
        upload_dir = Path(get_astrbot_data_path()) / "temp" / "sdk_http_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_payloads: list[dict[str, Any]] = []
        request_files = await quart_request.files
        for field_name in request_files:
            for storage in request_files.getlist(field_name):
                original_name = str(storage.filename or "").strip()
                suffix = Path(original_name).suffix
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    dir=upload_dir,
                    suffix=suffix,
                )
                temp_path = Path(temp_file.name)
                temp_file.close()
                storage.save(temp_path)
                file_payloads.append(
                    {
                        "field_name": str(field_name),
                        "filename": original_name,
                        "content_type": str(storage.content_type or ""),
                        "path": str(temp_path),
                        "size": temp_path.stat().st_size,
                    }
                )
        payload = {
            "method": method.upper(),
            "route": route_entry.route,
            "path": quart_request.path,
            "query": quart_request.args.to_dict(flat=False),
            "headers": dict(quart_request.headers),
            "form": form_payload,
            "files": file_payloads,
            "json_body": await quart_request.get_json(silent=True),
            "text_body": text_body,
        }
        output = await record.session.invoke_capability(
            route_entry.handler_capability,
            payload,
            request_id=f"sdk_http_{record.plugin_id}_{uuid.uuid4().hex}",
        )
        if not isinstance(output, dict):
            raise AstrBotError.invalid_input("SDK HTTP handler must return an object")
        return output
