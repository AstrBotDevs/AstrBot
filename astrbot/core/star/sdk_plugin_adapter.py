from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from fastapi.responses import FileResponse, JSONResponse, Response

from astrbot.api.web import request as plugin_web_request
from astrbot.core import logger
from astrbot.core.config import AstrBotConfig
from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.filter.regex import RegexFilter
from astrbot.core.star.star import StarMetadata, star_map, star_registry
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    star_handlers_registry,
)

SDK_PLUGIN_MANIFEST = "plugin.yaml"
SDK_PLUGIN_MODULE_SUFFIX = "__sdk_plugin__"
SDK_EVENT_TYPE_TO_ASTRBOT_EVENT = {
    "llm_request": EventType.OnLLMRequestEvent,
    "llm_response": EventType.OnLLMResponseEvent,
    "agent_done": EventType.OnAgentDoneEvent,
    "decorating_result": EventType.OnDecoratingResultEvent,
    "after_message_sent": EventType.OnAfterMessageSentEvent,
}


def _ensure_vendored_sdk_on_path() -> None:
    sdk_src = Path(__file__).resolve().parents[3] / "astrbot-sdk" / "src"
    if sdk_src.exists() and str(sdk_src) not in sys.path:
        sys.path.insert(0, str(sdk_src))


_ensure_vendored_sdk_on_path()

from astrbot_sdk.protocol.descriptors import (  # noqa: E402
    CommandTrigger,
    EventTrigger,
    MessageTrigger,
)
from astrbot_sdk.runtime.loader import (  # noqa: E402
    load_plugin_spec,
    validate_plugin_spec,
)
from astrbot_sdk.testing import PluginHarness  # noqa: E402


@dataclass(slots=True)
class SDKPluginRuntime:
    root_dir_name: str
    module_path: str
    harness: PluginHarness
    registered_web_routes: list[tuple[str, list[str]]]


class SDKPluginStarProxy:
    def __init__(self, harness: PluginHarness) -> None:
        self._harness = harness

    async def terminate(self) -> None:
        await self._harness.stop()


class SDKPluginAdapter:
    def __init__(
        self,
        *,
        plugin_store_path: str,
        plugin_config_path: str,
        star_context: Context | None = None,
    ) -> None:
        self.plugin_store_path = Path(plugin_store_path)
        self.plugin_config_path = Path(plugin_config_path)
        self.plugin_data_path = self.plugin_config_path.parent / "plugin_data"
        self.star_context = star_context
        self._runtimes: dict[str, SDKPluginRuntime] = {}

    @staticmethod
    def is_sdk_plugin_dir(plugin_dir: str | Path) -> bool:
        return (Path(plugin_dir) / SDK_PLUGIN_MANIFEST).is_file()

    @staticmethod
    def module_path_for(root_dir_name: str) -> str:
        return f"data.plugins.{root_dir_name}.{SDK_PLUGIN_MODULE_SUFFIX}"

    def discover_root_dirs(self) -> list[str]:
        if not self.plugin_store_path.is_dir():
            return []
        return sorted(
            path.name
            for path in self.plugin_store_path.iterdir()
            if path.is_dir() and self.is_sdk_plugin_dir(path)
        )

    async def load_all(
        self,
        *,
        specified_dir_name: str | None = None,
        inactivated_plugins: list[str],
    ) -> tuple[bool, dict[str, dict[str, Any]]]:
        failed: dict[str, dict[str, Any]] = {}
        for root_dir_name in self.discover_root_dirs():
            if specified_dir_name and root_dir_name != specified_dir_name:
                continue
            try:
                await self.load_one(
                    root_dir_name,
                    inactivated_plugins=inactivated_plugins,
                )
            except Exception as exc:
                logger.error(
                    "SDK 插件 %s 载入失败: %s",
                    root_dir_name,
                    exc,
                    exc_info=True,
                )
                failed[root_dir_name] = {
                    "name": root_dir_name,
                    "error": str(exc),
                    "traceback": "",
                    "reserved": False,
                }
        return not failed, failed

    async def load_one(
        self,
        root_dir_name: str,
        *,
        inactivated_plugins: list[str],
    ) -> StarMetadata:
        plugin_dir = self.plugin_store_path / root_dir_name
        module_path = self.module_path_for(root_dir_name)
        await self.unload_by_module_path(module_path)

        plugin = load_plugin_spec(plugin_dir)
        validate_plugin_spec(plugin)
        harness = PluginHarness.from_plugin_dir(plugin_dir)
        self._prepare_harness_storage(root_dir_name, harness)
        metadata = self._metadata_from_manifest(
            root_dir_name=root_dir_name,
            module_path=module_path,
            manifest=plugin.manifest_data,
            activated=module_path not in inactivated_plugins,
        )
        metadata.config = self._load_astrbot_config(root_dir_name, plugin_dir)
        star_map[module_path] = metadata
        star_registry.append(metadata)

        if metadata.activated:
            self._sync_astrbot_config_for_sdk_loader(
                root_dir_name=root_dir_name,
                plugin_name=plugin.name,
            )
            await harness.start()
            assert harness.loaded_plugin is not None
            metadata.star_cls_type = SDKPluginStarProxy
            metadata.star_cls = SDKPluginStarProxy(harness)
            self._runtimes[module_path] = SDKPluginRuntime(
                root_dir_name=root_dir_name,
                module_path=module_path,
                harness=harness,
                registered_web_routes=self._register_http_apis(harness),
            )
            metadata.star_handler_full_names = self._register_handlers(
                module_path=module_path,
                plugin_name=plugin.name,
                harness=harness,
            )
        else:
            logger.info("SDK plugin %s is disabled.", metadata.name)
        return metadata

    def _prepare_harness_storage(
        self,
        root_dir_name: str,
        harness: PluginHarness,
    ) -> None:
        router = harness.router
        self.plugin_data_path.mkdir(parents=True, exist_ok=True)
        if hasattr(router, "_system_data_root"):
            router._system_data_root = self.plugin_data_path

        self._restore_harness_db_state(root_dir_name, harness)
        original_execute = router.execute

        async def execute_with_persistence(capability, payload, **kwargs):
            result = await original_execute(capability, payload, **kwargs)
            if str(capability).startswith("db."):
                self._save_harness_db_state(root_dir_name, harness)
            return result

        router.execute = execute_with_persistence

    def _db_state_path(self, root_dir_name: str) -> Path:
        return self.plugin_data_path / root_dir_name / "sdk_db_store.json"

    def _restore_harness_db_state(
        self,
        root_dir_name: str,
        harness: PluginHarness,
    ) -> None:
        state_path = self._db_state_path(root_dir_name)
        if not state_path.exists():
            return
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取 SDK 插件 DB 状态 %s 失败，跳过恢复。", state_path)
            return
        if not isinstance(payload, dict):
            return
        db_store = payload.get("db_store")
        if isinstance(db_store, dict):
            harness.router.db_store.clear()
            harness.router.db_store.update(db_store)

    def _save_harness_db_state(
        self,
        root_dir_name: str,
        harness: PluginHarness,
    ) -> None:
        state_path = self._db_state_path(root_dir_name)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            state_path.write_text(
                json.dumps(
                    {"db_store": harness.router.db_store},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.warning("写入 SDK 插件 DB 状态 %s 失败。", state_path)

    async def unload_by_module_path(self, module_path: str) -> None:
        runtime = self._runtimes.pop(module_path, None)
        if runtime is not None:
            await runtime.harness.stop()
            self._unregister_http_apis(runtime.registered_web_routes)
        if module_path in star_map:
            plugin_name = star_map[module_path].name
            star_map.pop(module_path, None)
            star_registry[:] = [
                item for item in star_registry if item.module_path != module_path
            ]
            for handler in star_handlers_registry.get_handlers_by_module_name(
                module_path
            ):
                logger.info(
                    "移除了 SDK 插件 %s 的处理函数 %s",
                    plugin_name,
                    handler.handler_name,
                )
                star_handlers_registry.remove(handler)

    async def unload_by_plugin_name(self, plugin_name: str) -> bool:
        for module_path, metadata in list(star_map.items()):
            if metadata.name == plugin_name and module_path.endswith(
                f".{SDK_PLUGIN_MODULE_SUFFIX}"
            ):
                await self.unload_by_module_path(module_path)
                return True
        return False

    def _register_http_apis(
        self, harness: PluginHarness
    ) -> list[tuple[str, list[str]]]:
        if self.star_context is None:
            return []

        registered: list[tuple[str, list[str]]] = []
        for entry in harness.router.http_api_store:
            route = str(entry.get("route") or "").strip()
            handler_capability = str(entry.get("handler_capability") or "").strip()
            if not route or not handler_capability:
                continue
            methods = [
                str(method).upper()
                for method in entry.get("methods", [])
                if str(method).strip()
            ]
            if not methods:
                continue
            astrbot_route = self._sdk_route_to_astrbot(route)
            self.star_context.register_web_api(
                astrbot_route,
                self._build_http_api_handler(
                    harness=harness,
                    route=route,
                    handler_capability=handler_capability,
                ),
                methods,
                str(entry.get("description") or ""),
            )
            registered.append((astrbot_route, methods))
            logger.info(
                "Registered SDK HTTP API %s %s -> %s",
                ",".join(methods),
                astrbot_route,
                handler_capability,
            )
        return registered

    def _unregister_http_apis(self, routes: list[tuple[str, list[str]]]) -> None:
        if self.star_context is None or not routes:
            return
        route_set = {(route, tuple(methods)) for route, methods in routes}
        self.star_context.registered_web_apis = [
            item
            for item in self.star_context.registered_web_apis
            if (item[0], tuple(item[2])) not in route_set
        ]

    @staticmethod
    def _sdk_route_to_astrbot(route: str) -> str:
        chunks: list[str] = []
        index = 0
        while index < len(route):
            if route[index] != "{":
                chunks.append(route[index])
                index += 1
                continue
            end = route.find("}", index + 1)
            if end == -1:
                chunks.append(route[index])
                index += 1
                continue
            name = route[index + 1 : end].strip()
            chunks.append(f"<{name}>" if name else "{}")
            index = end + 1
        return "".join(chunks)

    def _build_http_api_handler(
        self,
        *,
        harness: PluginHarness,
        route: str,
        handler_capability: str,
    ):
        async def sdk_http_api_handler(**path_params: Any) -> Any:
            payload = await self._http_request_payload(
                route=route,
                path_params=path_params,
            )
            result = await harness.invoke_capability(
                handler_capability,
                payload,
                request_id=str(payload["request_id"]),
            )
            return self._http_response_from_result(result)

        sdk_http_api_handler.__name__ = handler_capability.rsplit(".", 1)[-1]
        return sdk_http_api_handler

    async def _http_request_payload(
        self,
        *,
        route: str,
        path_params: dict[str, Any],
    ) -> dict[str, Any]:
        body = await plugin_web_request.body()
        json_body = await plugin_web_request.json(default=None)
        form_payload: dict[str, list[str]] = {}
        files_payload: dict[str, list[dict[str, Any]]] = {}

        content_type = (plugin_web_request.content_type or "").lower()
        if (
            "multipart/form-data" in content_type
            or "application/x-www-form-urlencoded" in content_type
        ):
            try:
                form = await plugin_web_request.form()
                form_payload = {
                    key: [str(item) for item in form.getlist(key)]
                    for key in form.keys()
                }
                files = await plugin_web_request.files()
                for key in files.keys():
                    file_items: list[dict[str, Any]] = []
                    for upload in files.getlist(key):
                        content = await upload.read()
                        file_items.append(
                            {
                                "filename": upload.filename,
                                "content_type": upload.content_type,
                                "content": content.hex(),
                                "encoding": "hex",
                            }
                        )
                    files_payload[key] = file_items
            except Exception as exc:
                logger.warning("读取 SDK HTTP 请求表单失败: %s", exc)

        return {
            "request_id": f"sdk-http-{id(plugin_web_request)}",
            "route": route,
            "method": plugin_web_request.method,
            "path": plugin_web_request.path,
            "path_params": dict(path_params),
            "params": dict(path_params),
            "query": {
                key: plugin_web_request.query.getlist(key)
                for key in plugin_web_request.query.keys()
            },
            "headers": dict(plugin_web_request.headers),
            "cookies": dict(plugin_web_request.cookies),
            "username": plugin_web_request.username,
            "body": body.decode("utf-8", errors="replace") if body else "",
            "body_hex": body.hex(),
            "json": json_body,
            "form": form_payload,
            "files": files_payload,
        }

    @staticmethod
    def _http_response_from_result(result: Any) -> Any:
        if not isinstance(result, dict):
            return result

        status_code = int(result.get("status") or result.get("status_code") or 200)
        headers = (
            result.get("headers") if isinstance(result.get("headers"), dict) else None
        )
        media_type = result.get("media_type") or result.get("content_type")
        file_path = result.get("file_path")
        if file_path:
            return FileResponse(
                str(file_path),
                status_code=status_code,
                media_type=str(media_type) if media_type else None,
                filename=result.get("filename"),
                headers=headers,
            )

        raw_body_hex = result.get("body_hex")
        if isinstance(raw_body_hex, str):
            return Response(
                bytes.fromhex(raw_body_hex),
                status_code=status_code,
                media_type=str(media_type) if media_type else None,
                headers=headers,
            )

        body = result.get("body", result.get("data", result))
        if isinstance(body, str):
            return Response(
                body,
                status_code=status_code,
                media_type=str(media_type) if media_type else "text/plain",
                headers=headers,
            )
        return JSONResponse(
            body,
            status_code=status_code,
            headers=headers,
        )

    def _metadata_from_manifest(
        self,
        *,
        root_dir_name: str,
        module_path: str,
        manifest: dict[str, Any],
        activated: bool,
    ) -> StarMetadata:
        return StarMetadata(
            name=str(manifest.get("name") or root_dir_name),
            author=str(manifest.get("author") or "unknown"),
            desc=str(manifest.get("desc") or manifest.get("description") or ""),
            short_desc=str(manifest.get("short_desc") or ""),
            version=str(manifest.get("version") or "0.0.0"),
            repo=str(manifest.get("repo") or ""),
            display_name=str(manifest.get("display_name") or ""),
            support_platforms=[
                str(item)
                for item in manifest.get("support_platforms", [])
                if isinstance(item, str)
            ],
            astrbot_version=(
                str(manifest.get("astrbot_version"))
                if manifest.get("astrbot_version") is not None
                else None
            ),
            pages=[
                dict(item)
                for item in manifest.get("pages", [])
                if isinstance(item, dict)
            ],
            module_path=module_path,
            root_dir_name=root_dir_name,
            reserved=False,
            activated=activated,
        )

    def _load_astrbot_config(
        self,
        root_dir_name: str,
        plugin_dir: Path,
    ) -> AstrBotConfig | None:
        schema_path = plugin_dir / "_conf_schema.json"
        if not schema_path.exists():
            return None
        return AstrBotConfig(
            config_path=str(self.plugin_config_path / f"{root_dir_name}_config.json"),
            schema=yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {},
        )

    def _sync_astrbot_config_for_sdk_loader(
        self,
        *,
        root_dir_name: str,
        plugin_name: str,
    ) -> None:
        source_path = self.plugin_config_path / f"{root_dir_name}_config.json"
        target_path = self.plugin_config_path / f"{plugin_name}_config.json"
        if not source_path.exists():
            return
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8-sig"))
        except Exception:
            logger.warning("读取 SDK 插件配置 %s 失败，跳过同步。", source_path)
            return
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(
                payload if isinstance(payload, dict) else {},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _register_handlers(
        self,
        *,
        module_path: str,
        plugin_name: str,
        harness: PluginHarness,
    ) -> list[str]:
        assert harness.loaded_plugin is not None
        full_names: list[str] = []
        for loaded in harness.loaded_plugin.handlers:
            descriptor = loaded.descriptor
            event_type = self._event_type_for_descriptor(descriptor)
            filters = self._filters_for_descriptor(descriptor)
            if not filters and event_type == EventType.AdapterMessageEvent:
                logger.info(
                    "SDK handler %s 暂未映射到 AstrBot 过滤器，跳过传统流水线注册。",
                    descriptor.id,
                )
                continue
            if event_type == EventType.AdapterMessageEvent:
                handler = self._build_handler(harness, descriptor.id)
            else:
                handler = self._build_event_handler(
                    harness,
                    descriptor.id,
                    self._sdk_event_type_for_descriptor(descriptor),
                )
            metadata = StarHandlerMetadata(
                event_type=event_type,
                handler_full_name=descriptor.id,
                handler_name=descriptor.id.rsplit(".", 1)[-1],
                handler_module_path=module_path,
                handler=handler,
                event_filters=filters,
                desc=descriptor.description or "",
                extras_configs={"priority": descriptor.priority},
                enabled=True,
            )
            for filter_item in filters:
                if isinstance(filter_item, CommandFilter):
                    filter_item.init_handler_md(metadata)
            star_handlers_registry.append(metadata)
            full_names.append(descriptor.id)
            logger.info(
                "Registered SDK handler %s for plugin %s",
                descriptor.id,
                plugin_name,
            )
        return full_names

    def _event_type_for_descriptor(self, descriptor) -> EventType:
        trigger = descriptor.trigger
        if isinstance(trigger, EventTrigger):
            return SDK_EVENT_TYPE_TO_ASTRBOT_EVENT.get(
                trigger.event_type,
                EventType.AdapterMessageEvent,
            )
        return EventType.AdapterMessageEvent

    @staticmethod
    def _sdk_event_type_for_descriptor(descriptor) -> str:
        trigger = descriptor.trigger
        if isinstance(trigger, EventTrigger):
            return trigger.event_type
        return "message"

    def _filters_for_descriptor(self, descriptor) -> list[Any]:
        trigger = descriptor.trigger
        if isinstance(trigger, CommandTrigger):
            return [CommandFilter(trigger.command, alias=set(trigger.aliases))]
        if isinstance(trigger, MessageTrigger) and trigger.regex:
            return [RegexFilter(trigger.regex)]
        return []

    def _build_handler(self, harness: PluginHarness, handler_id: str):
        async def sdk_handler(event: AstrMessageEvent) -> None:
            start_index = len(harness.sent_messages)
            payload = self._event_payload(event)
            await harness.dispatch_event(
                payload, request_id=str(payload["raw"]["trace_id"])
            )
            records = harness.sent_messages[start_index:]
            for record in records:
                chain = self._record_to_chain(record)
                if chain.chain:
                    await event.send(chain)
            if records:
                event.stop_event()

        sdk_handler.__name__ = handler_id.rsplit(".", 1)[-1]
        return sdk_handler

    def _build_event_handler(
        self,
        harness: PluginHarness,
        handler_id: str,
        sdk_event_type: str,
    ):
        async def sdk_event_handler(event: AstrMessageEvent, *args: Any) -> None:
            start_index = len(harness.sent_messages)
            payload = self._event_payload(event)
            payload["type"] = sdk_event_type
            payload["event_type"] = sdk_event_type
            payload["raw"]["event_type"] = sdk_event_type
            payload["raw"]["type"] = sdk_event_type
            self._inject_sdk_event_payload(
                payload=payload,
                sdk_event_type=sdk_event_type,
                event=event,
                args=args,
            )
            summary = await self._invoke_exact_handler(
                harness=harness,
                handler_id=handler_id,
                payload=payload,
            )
            self._apply_sdk_event_summary(
                summary=summary,
                sdk_event_type=sdk_event_type,
                event=event,
                args=args,
            )
            records = harness.sent_messages[start_index:]
            for record in records:
                chain = self._record_to_chain(record)
                if chain.chain:
                    await event.send(chain)
            if bool(summary.get("stop", False)):
                event.stop_event()

        sdk_event_handler.__name__ = handler_id.rsplit(".", 1)[-1]
        return sdk_event_handler

    async def _invoke_exact_handler(
        self,
        *,
        harness: PluginHarness,
        handler_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await harness.start()
        assert harness.loaded_plugin is not None
        for loaded in harness.loaded_plugin.handlers:
            if loaded.descriptor.id == handler_id:
                return await harness._invoke_handler(  # noqa: SLF001
                    loaded,
                    payload,
                    args={},
                    request_id=str(payload["raw"]["trace_id"]),
                )
        raise LookupError(f"SDK handler not found: {handler_id}")

    def _inject_sdk_event_payload(
        self,
        *,
        payload: dict[str, Any],
        sdk_event_type: str,
        event: AstrMessageEvent,
        args: tuple[Any, ...],
    ) -> None:
        if sdk_event_type == "llm_request" and args:
            req = args[0]
            if isinstance(req, ProviderRequest):
                payload["provider_request"] = self._provider_request_payload(req)
        elif sdk_event_type in {"llm_response", "agent_done"}:
            response = self._response_from_event_args(sdk_event_type, args)
            if response is not None:
                payload["llm_response"] = self._llm_response_payload(response)
        elif sdk_event_type in {"decorating_result", "after_message_sent"}:
            result = event.get_result()
            if result is not None:
                payload["event_result"] = self._event_result_payload(result)

    def _apply_sdk_event_summary(
        self,
        *,
        summary: dict[str, Any],
        sdk_event_type: str,
        event: AstrMessageEvent,
        args: tuple[Any, ...],
    ) -> None:
        if sdk_event_type == "llm_request" and args:
            req = args[0]
            payload = summary.get("provider_request")
            if isinstance(req, ProviderRequest) and isinstance(payload, dict):
                self._apply_provider_request_payload(req, payload)
        elif sdk_event_type in {"llm_response", "agent_done"}:
            response = self._response_from_event_args(sdk_event_type, args)
            payload = summary.get("llm_response")
            if response is not None and isinstance(payload, dict):
                self._apply_llm_response_payload(response, payload)
        elif sdk_event_type in {"decorating_result", "after_message_sent"}:
            payload = summary.get("event_result")
            if isinstance(payload, dict):
                self._apply_event_result_payload(event, payload)

        extras = summary.get("sdk_local_extras")
        if isinstance(extras, dict):
            for key, value in extras.items():
                event.set_extra(str(key), value)

    @staticmethod
    def _response_from_event_args(
        sdk_event_type: str,
        args: tuple[Any, ...],
    ) -> LLMResponse | None:
        if sdk_event_type == "llm_response" and args:
            return args[0] if isinstance(args[0], LLMResponse) else None
        if sdk_event_type == "agent_done" and len(args) >= 2:
            return args[1] if isinstance(args[1], LLMResponse) else None
        return None

    def _event_payload(self, event: AstrMessageEvent) -> dict[str, Any]:
        message_type = "group" if event.get_group_id() else "private"
        return {
            "type": "message",
            "event_type": "message",
            "text": event.get_message_str(),
            "session_id": event.unified_msg_origin,
            "user_id": event.get_sender_id(),
            "platform": event.get_platform_id() or event.get_platform_name(),
            "platform_id": event.get_platform_id() or event.get_platform_name(),
            "group_id": event.get_group_id() or None,
            "self_id": event.get_self_id(),
            "sender_name": event.get_sender_name(),
            "is_admin": event.is_admin(),
            "message_type": message_type,
            "raw": {
                "trace_id": f"sdk-{id(event)}",
                "event_type": "message",
                "unified_msg_origin": event.unified_msg_origin,
                "messages": self._message_components_payload(event),
            },
        }

    def _message_components_payload(
        self,
        event: AstrMessageEvent,
    ) -> list[dict[str, Any]]:
        message_obj = getattr(event, "message_obj", None)
        components = getattr(message_obj, "message", None)
        if not isinstance(components, list):
            text = event.get_message_str()
            return [{"type": "text", "data": {"text": text}}] if text else []
        return self._components_payload(components)

    def _components_payload(self, components: list[Any]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for component in components:
            to_dict = getattr(component, "toDict", None)
            if callable(to_dict):
                try:
                    payload = to_dict()
                    if isinstance(payload, dict):
                        payloads.append(payload)
                        continue
                except Exception:
                    pass
            component_type = str(getattr(component, "type", "") or "").lower()
            if component_type in {"plain", "text"}:
                payloads.append(
                    {
                        "type": "text",
                        "data": {"text": str(getattr(component, "text", ""))},
                    }
                )
            elif component_type == "image":
                payloads.append(
                    {
                        "type": "image",
                        "data": {
                            "file": str(getattr(component, "file", "") or ""),
                            "url": str(getattr(component, "url", "") or ""),
                            "path": str(getattr(component, "path", "") or ""),
                        },
                    }
                )
        return payloads

    def _provider_request_payload(self, req: ProviderRequest) -> dict[str, Any]:
        return {
            "prompt": req.prompt,
            "system_prompt": req.system_prompt,
            "session_id": req.session_id,
            "contexts": list(req.contexts or []),
            "image_urls": list(req.image_urls or []),
            "model": req.model,
        }

    @staticmethod
    def _apply_provider_request_payload(
        req: ProviderRequest,
        payload: dict[str, Any],
    ) -> None:
        if "prompt" in payload:
            req.prompt = payload.get("prompt")
        if "system_prompt" in payload:
            req.system_prompt = str(payload.get("system_prompt") or "")
        if "session_id" in payload:
            req.session_id = str(payload.get("session_id") or "")
        if isinstance(payload.get("contexts"), list):
            req.contexts = list(payload["contexts"])
        if isinstance(payload.get("image_urls"), list):
            req.image_urls = [str(item) for item in payload["image_urls"]]
        if "model" in payload:
            req.model = (
                str(payload.get("model")) if payload.get("model") is not None else None
            )

    def _llm_response_payload(self, response: LLMResponse) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": response.completion_text or "",
            "role": response.role,
            "reasoning_content": response.reasoning_content,
            "reasoning_signature": response.reasoning_signature,
            "tool_calls": self._llm_tool_calls_payload(response),
        }
        usage = getattr(response, "usage", None)
        model_dump = getattr(usage, "model_dump", None)
        if callable(model_dump):
            payload["usage"] = model_dump()
        return payload

    @staticmethod
    def _llm_tool_calls_payload(response: LLMResponse) -> list[dict[str, Any]]:
        tool_calls: list[dict[str, Any]] = []
        for index, name in enumerate(response.tools_call_name or []):
            args = (
                response.tools_call_args[index]
                if index < len(response.tools_call_args or [])
                else {}
            )
            tool_id = (
                response.tools_call_ids[index]
                if index < len(response.tools_call_ids or [])
                else ""
            )
            tool_calls.append({"id": tool_id, "name": name, "arguments": args})
        return tool_calls

    @staticmethod
    def _apply_llm_response_payload(
        response: LLMResponse,
        payload: dict[str, Any],
    ) -> None:
        if "text" in payload:
            response.completion_text = str(payload.get("text") or "")
        if "role" in payload and payload.get("role") is not None:
            response.role = str(payload["role"])
        if "reasoning_content" in payload:
            response.reasoning_content = (
                str(payload.get("reasoning_content"))
                if payload.get("reasoning_content") is not None
                else None
            )
        if "reasoning_signature" in payload:
            response.reasoning_signature = (
                str(payload.get("reasoning_signature"))
                if payload.get("reasoning_signature") is not None
                else None
            )

    def _event_result_payload(self, result: MessageEventResult) -> dict[str, Any]:
        return {
            "type": "chain" if result.chain else "empty",
            "chain": self._components_payload(list(result.chain or [])),
        }

    def _apply_event_result_payload(
        self,
        event: AstrMessageEvent,
        payload: dict[str, Any],
    ) -> None:
        chain_payload = payload.get("chain")
        chain = (
            self._payloads_to_chain(chain_payload)
            if isinstance(chain_payload, list)
            else MessageChain()
        )
        result = event.get_result()
        if result is None:
            result = MessageEventResult()
            event.set_result(result)
        result.chain = chain.chain

    def _payloads_to_chain(self, payloads: list[Any]) -> MessageChain:
        chain = MessageChain()
        for item in payloads:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            data = item.get("data") if isinstance(item.get("data"), dict) else {}
            if item_type in {"text", "plain"}:
                chain.chain.append(Plain(str(data.get("text", ""))))
            elif item_type == "image":
                image_source = str(
                    data.get("path") or data.get("file") or data.get("url") or "",
                )
                chain.chain.extend(self._image_chain(image_source).chain)
        return chain

    def _record_to_chain(self, record: Any) -> MessageChain:
        if getattr(record, "kind", "") == "text":
            return MessageChain([Plain(str(getattr(record, "text", "") or ""))])
        if getattr(record, "kind", "") == "image":
            return self._image_chain(str(getattr(record, "image_url", "") or ""))
        if getattr(record, "kind", "") == "chain":
            return self._payloads_to_chain(getattr(record, "chain", []) or [])
        return MessageChain()

    def _image_chain(self, image_url: str) -> MessageChain:
        chain = MessageChain()
        if not image_url:
            return chain
        if image_url.startswith("file://"):
            chain.chain.append(Image.fromFileSystem(image_url.removeprefix("file://")))
        elif image_url.startswith("/"):
            chain.chain.append(Image.fromFileSystem(image_url))
        else:
            chain.chain.append(Image.fromURL(image_url))
        return chain


__all__ = ["SDKPluginAdapter", "SDK_PLUGIN_MANIFEST"]
