"""Builtin protocol schema constants.

本模块定义了 AstrBot SDK v4 协议中所有内置能力的 JSON Schema。
这些 Schema 用于：
1. 验证能力调用的输入参数是否符合预期格式
2. 生成能力描述文档，供插件开发者参考
3. 确保跨进程/跨语言调用时的类型安全

所有 Schema 遵循 JSON Schema 规范，支持基本类型检查、必填字段、数组元素约束等。
"""

from __future__ import annotations

from typing import Any

JSONSchema = dict[str, Any]


def _object_schema(
    *,
    required: tuple[str, ...] = (),
    **properties: Any,
) -> JSONSchema:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }


def _nullable(schema: JSONSchema) -> JSONSchema:
    return {"anyOf": [schema, {"type": "null"}]}


_OPTIONAL_CHAT_PROPERTIES: dict[str, Any] = {
    "system": {"type": "string"},
    "history": {"type": "array", "items": {"type": "object"}},
    "contexts": {"type": "array", "items": {"type": "object"}},
    "provider_id": {"type": "string"},
    "tool_calls_result": {"type": "array", "items": {"type": "object"}},
    "model": {"type": "string"},
    "temperature": {"type": "number"},
    "image_urls": {"type": "array", "items": {"type": "string"}},
    "tools": {"type": "array"},
    "max_steps": {"type": "integer"},
}

LLM_CHAT_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_CHAT_OUTPUT_SCHEMA = _object_schema(required=("text",), text={"type": "string"})
LLM_CHAT_RAW_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_CHAT_RAW_OUTPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
    usage=_nullable({"type": "object"}),
    finish_reason=_nullable({"type": "string"}),
    tool_calls={"type": "array", "items": {"type": "object"}},
    role=_nullable({"type": "string"}),
    reasoning_content=_nullable({"type": "string"}),
    reasoning_signature=_nullable({"type": "string"}),
)
LLM_STREAM_CHAT_INPUT_SCHEMA = _object_schema(
    required=("prompt",),
    prompt={"type": "string"},
    **_OPTIONAL_CHAT_PROPERTIES,
)
LLM_STREAM_CHAT_OUTPUT_SCHEMA = _object_schema(
    required=("text",), text={"type": "string"}
)
MEMORY_SEARCH_INPUT_SCHEMA = _object_schema(
    required=("query",), query={"type": "string"}
)
MEMORY_SEARCH_OUTPUT_SCHEMA = _object_schema(
    required=("items",),
    items={"type": "array", "items": {"type": "object"}},
)
MEMORY_SAVE_INPUT_SCHEMA = _object_schema(
    required=("key", "value"),
    key={"type": "string"},
    value={"type": "object"},
)
MEMORY_SAVE_OUTPUT_SCHEMA = _object_schema()
MEMORY_GET_INPUT_SCHEMA = _object_schema(required=("key",), key={"type": "string"})
MEMORY_GET_OUTPUT_SCHEMA = _object_schema(
    required=("value",),
    value=_nullable({"type": "object"}),
)
MEMORY_DELETE_INPUT_SCHEMA = _object_schema(
    required=("key",),
    key={"type": "string"},
)
MEMORY_DELETE_OUTPUT_SCHEMA = _object_schema()
MEMORY_SAVE_WITH_TTL_INPUT_SCHEMA = _object_schema(
    required=("key", "value", "ttl_seconds"),
    key={"type": "string"},
    value={"type": "object"},
    ttl_seconds={"type": "integer", "minimum": 1},
)
MEMORY_SAVE_WITH_TTL_OUTPUT_SCHEMA = _object_schema()
MEMORY_GET_MANY_INPUT_SCHEMA = _object_schema(
    required=("keys",),
    keys={"type": "array", "items": {"type": "string"}},
)
MEMORY_GET_MANY_OUTPUT_SCHEMA = _object_schema(
    required=("items",),
    items={
        "type": "array",
        "items": _object_schema(
            required=("key", "value"),
            key={"type": "string"},
            value=_nullable({"type": "object"}),
        ),
    },
)
MEMORY_DELETE_MANY_INPUT_SCHEMA = _object_schema(
    required=("keys",),
    keys={"type": "array", "items": {"type": "string"}},
)
MEMORY_DELETE_MANY_OUTPUT_SCHEMA = _object_schema(
    required=("deleted_count",),
    deleted_count={"type": "integer"},
)
MEMORY_STATS_INPUT_SCHEMA = _object_schema()
MEMORY_STATS_OUTPUT_SCHEMA = _object_schema(
    total_items={"type": "integer"},
    total_bytes=_nullable({"type": "integer"}),
    plugin_id=_nullable({"type": "string"}),
    ttl_entries=_nullable({"type": "integer"}),
)
SYSTEM_GET_DATA_DIR_INPUT_SCHEMA = _object_schema()
SYSTEM_GET_DATA_DIR_OUTPUT_SCHEMA = _object_schema(
    required=("path",),
    path={"type": "string"},
)
SYSTEM_TEXT_TO_IMAGE_INPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
    return_url={"type": "boolean"},
)
SYSTEM_TEXT_TO_IMAGE_OUTPUT_SCHEMA = _object_schema(
    required=("result",),
    result={"type": "string"},
)
SYSTEM_HTML_RENDER_INPUT_SCHEMA = _object_schema(
    required=("tmpl", "data"),
    tmpl={"type": "string"},
    data={"type": "object"},
    return_url={"type": "boolean"},
    options=_nullable({"type": "object"}),
)
SYSTEM_HTML_RENDER_OUTPUT_SCHEMA = _object_schema(
    required=("result",),
    result={"type": "string"},
)
SYSTEM_SESSION_WAITER_REGISTER_INPUT_SCHEMA = _object_schema(
    required=("session_key",),
    session_key={"type": "string"},
)
SYSTEM_SESSION_WAITER_REGISTER_OUTPUT_SCHEMA = _object_schema()
SYSTEM_SESSION_WAITER_UNREGISTER_INPUT_SCHEMA = _object_schema(
    required=("session_key",),
    session_key={"type": "string"},
)
SYSTEM_SESSION_WAITER_UNREGISTER_OUTPUT_SCHEMA = _object_schema()
DB_GET_INPUT_SCHEMA = _object_schema(required=("key",), key={"type": "string"})
DB_GET_OUTPUT_SCHEMA = _object_schema(
    required=("value",),
    value=_nullable({}),
)
DB_SET_INPUT_SCHEMA = _object_schema(
    required=("key", "value"),
    key={"type": "string"},
    value={},
)
DB_SET_OUTPUT_SCHEMA = _object_schema()
DB_DELETE_INPUT_SCHEMA = _object_schema(required=("key",), key={"type": "string"})
DB_DELETE_OUTPUT_SCHEMA = _object_schema()
DB_LIST_INPUT_SCHEMA = _object_schema(prefix=_nullable({"type": "string"}))
DB_LIST_OUTPUT_SCHEMA = _object_schema(
    required=("keys",),
    keys={"type": "array", "items": {"type": "string"}},
)
DB_GET_MANY_INPUT_SCHEMA = _object_schema(
    required=("keys",),
    keys={"type": "array", "items": {"type": "string"}},
)
DB_GET_MANY_OUTPUT_SCHEMA = _object_schema(
    required=("items",),
    items={
        "type": "array",
        "items": _object_schema(
            required=("key", "value"),
            key={"type": "string"},
            value=_nullable({}),
        ),
    },
)
DB_SET_MANY_INPUT_SCHEMA = _object_schema(
    required=("items",),
    items={
        "type": "array",
        "items": _object_schema(
            required=("key", "value"),
            key={"type": "string"},
            value={},
        ),
    },
)
DB_SET_MANY_OUTPUT_SCHEMA = _object_schema()
DB_WATCH_INPUT_SCHEMA = _object_schema(prefix=_nullable({"type": "string"}))
DB_WATCH_OUTPUT_SCHEMA = _object_schema()
SESSION_REF_SCHEMA = _object_schema(
    required=("conversation_id",),
    conversation_id={"type": "string"},
    platform=_nullable({"type": "string"}),
    raw=_nullable({"type": "object"}),
)
SYSTEM_EVENT_REACT_INPUT_SCHEMA = _object_schema(
    required=("emoji",),
    target=_nullable(SESSION_REF_SCHEMA),
    emoji={"type": "string"},
)
SYSTEM_EVENT_REACT_OUTPUT_SCHEMA = _object_schema(
    required=("supported",),
    supported={"type": "boolean"},
)
SYSTEM_EVENT_SEND_TYPING_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_SEND_TYPING_OUTPUT_SCHEMA = _object_schema(
    required=("supported",),
    supported={"type": "boolean"},
)
SYSTEM_EVENT_SEND_STREAMING_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
    use_fallback={"type": "boolean"},
)
SYSTEM_EVENT_SEND_STREAMING_OUTPUT_SCHEMA = _object_schema(
    required=("supported",),
    supported={"type": "boolean"},
    stream_id=_nullable({"type": "string"}),
)
SYSTEM_EVENT_SEND_STREAMING_CHUNK_INPUT_SCHEMA = _object_schema(
    required=("stream_id", "chain"),
    stream_id={"type": "string"},
    chain={"type": "array", "items": {"type": "object"}},
)
SYSTEM_EVENT_SEND_STREAMING_CHUNK_OUTPUT_SCHEMA = _object_schema()
SYSTEM_EVENT_SEND_STREAMING_CLOSE_INPUT_SCHEMA = _object_schema(
    required=("stream_id",),
    stream_id={"type": "string"},
)
SYSTEM_EVENT_SEND_STREAMING_CLOSE_OUTPUT_SCHEMA = _object_schema(
    required=("supported",),
    supported={"type": "boolean"},
)
PLATFORM_SEND_INPUT_SCHEMA = _object_schema(
    required=("session", "text"),
    session={"type": "string"},
    target=_nullable(SESSION_REF_SCHEMA),
    text={"type": "string"},
)
PLATFORM_SEND_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_SEND_IMAGE_INPUT_SCHEMA = _object_schema(
    required=("session", "image_url"),
    session={"type": "string"},
    target=_nullable(SESSION_REF_SCHEMA),
    image_url={"type": "string"},
)
PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_SEND_CHAIN_INPUT_SCHEMA = _object_schema(
    required=("session", "chain"),
    session={"type": "string"},
    target=_nullable(SESSION_REF_SCHEMA),
    chain={"type": "array", "items": {"type": "object"}},
)
PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_SEND_BY_SESSION_INPUT_SCHEMA = _object_schema(
    required=("session", "chain"),
    session={"type": "string"},
    chain={"type": "array", "items": {"type": "object"}},
)
PLATFORM_SEND_BY_SESSION_OUTPUT_SCHEMA = _object_schema(
    required=("message_id",),
    message_id={"type": "string"},
)
PLATFORM_GET_GROUP_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
    target=_nullable(SESSION_REF_SCHEMA),
)
PLATFORM_GET_GROUP_OUTPUT_SCHEMA = _object_schema(
    required=("group",),
    group=_nullable({"type": "object"}),
)
PLATFORM_GET_MEMBERS_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
    target=_nullable(SESSION_REF_SCHEMA),
)
PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA = _object_schema(
    required=("members",),
    members={"type": "array", "items": {"type": "object"}},
)
SESSION_PLUGIN_IS_ENABLED_INPUT_SCHEMA = _object_schema(
    required=("session", "plugin_name"),
    session={"type": "string"},
    plugin_name={"type": "string"},
)
SESSION_PLUGIN_IS_ENABLED_OUTPUT_SCHEMA = _object_schema(
    required=("enabled",),
    enabled={"type": "boolean"},
)
SESSION_PLUGIN_FILTER_HANDLERS_INPUT_SCHEMA = _object_schema(
    required=("session", "handlers"),
    session={"type": "string"},
    handlers={"type": "array", "items": {"type": "object"}},
)
SESSION_PLUGIN_FILTER_HANDLERS_OUTPUT_SCHEMA = _object_schema(
    required=("handlers",),
    handlers={"type": "array", "items": {"type": "object"}},
)
SESSION_SERVICE_IS_LLM_ENABLED_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
)
SESSION_SERVICE_IS_LLM_ENABLED_OUTPUT_SCHEMA = _object_schema(
    required=("enabled",),
    enabled={"type": "boolean"},
)
SESSION_SERVICE_SET_LLM_STATUS_INPUT_SCHEMA = _object_schema(
    required=("session", "enabled"),
    session={"type": "string"},
    enabled={"type": "boolean"},
)
SESSION_SERVICE_SET_LLM_STATUS_OUTPUT_SCHEMA = _object_schema()
SESSION_SERVICE_IS_TTS_ENABLED_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
)
SESSION_SERVICE_IS_TTS_ENABLED_OUTPUT_SCHEMA = _object_schema(
    required=("enabled",),
    enabled={"type": "boolean"},
)
SESSION_SERVICE_SET_TTS_STATUS_INPUT_SCHEMA = _object_schema(
    required=("session", "enabled"),
    session={"type": "string"},
    enabled={"type": "boolean"},
)
SESSION_SERVICE_SET_TTS_STATUS_OUTPUT_SCHEMA = _object_schema()
HTTP_REGISTER_API_INPUT_SCHEMA = _object_schema(
    required=("route", "methods", "handler_capability"),
    route={"type": "string"},
    methods={"type": "array", "items": {"type": "string"}},
    handler_capability={"type": "string"},
    description={"type": "string"},
)
HTTP_REGISTER_API_OUTPUT_SCHEMA = _object_schema()
HTTP_UNREGISTER_API_INPUT_SCHEMA = _object_schema(
    required=("route", "methods"),
    route={"type": "string"},
    methods={"type": "array", "items": {"type": "string"}},
)
HTTP_UNREGISTER_API_OUTPUT_SCHEMA = _object_schema()
HTTP_LIST_APIS_INPUT_SCHEMA = _object_schema()
HTTP_LIST_APIS_OUTPUT_SCHEMA = _object_schema(
    required=("apis",),
    apis={"type": "array", "items": {"type": "object"}},
)
METADATA_GET_PLUGIN_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
METADATA_GET_PLUGIN_OUTPUT_SCHEMA = _object_schema(
    required=("plugin",),
    plugin=_nullable({"type": "object"}),
)
METADATA_LIST_PLUGINS_INPUT_SCHEMA = _object_schema()
METADATA_LIST_PLUGINS_OUTPUT_SCHEMA = _object_schema(
    required=("plugins",),
    plugins={"type": "array", "items": {"type": "object"}},
)
METADATA_GET_PLUGIN_CONFIG_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
METADATA_GET_PLUGIN_CONFIG_OUTPUT_SCHEMA = _object_schema(
    required=("config",),
    config=_nullable({"type": "object"}),
)

BUILTIN_CAPABILITY_SCHEMAS: dict[str, dict[str, JSONSchema]] = {
    "llm.chat": {"input": LLM_CHAT_INPUT_SCHEMA, "output": LLM_CHAT_OUTPUT_SCHEMA},
    "llm.chat_raw": {
        "input": LLM_CHAT_RAW_INPUT_SCHEMA,
        "output": LLM_CHAT_RAW_OUTPUT_SCHEMA,
    },
    "llm.stream_chat": {
        "input": LLM_STREAM_CHAT_INPUT_SCHEMA,
        "output": LLM_STREAM_CHAT_OUTPUT_SCHEMA,
    },
    "memory.search": {
        "input": MEMORY_SEARCH_INPUT_SCHEMA,
        "output": MEMORY_SEARCH_OUTPUT_SCHEMA,
    },
    "memory.save": {
        "input": MEMORY_SAVE_INPUT_SCHEMA,
        "output": MEMORY_SAVE_OUTPUT_SCHEMA,
    },
    "memory.get": {
        "input": MEMORY_GET_INPUT_SCHEMA,
        "output": MEMORY_GET_OUTPUT_SCHEMA,
    },
    "memory.delete": {
        "input": MEMORY_DELETE_INPUT_SCHEMA,
        "output": MEMORY_DELETE_OUTPUT_SCHEMA,
    },
    "memory.save_with_ttl": {
        "input": MEMORY_SAVE_WITH_TTL_INPUT_SCHEMA,
        "output": MEMORY_SAVE_WITH_TTL_OUTPUT_SCHEMA,
    },
    "memory.get_many": {
        "input": MEMORY_GET_MANY_INPUT_SCHEMA,
        "output": MEMORY_GET_MANY_OUTPUT_SCHEMA,
    },
    "memory.delete_many": {
        "input": MEMORY_DELETE_MANY_INPUT_SCHEMA,
        "output": MEMORY_DELETE_MANY_OUTPUT_SCHEMA,
    },
    "memory.stats": {
        "input": MEMORY_STATS_INPUT_SCHEMA,
        "output": MEMORY_STATS_OUTPUT_SCHEMA,
    },
    "db.get": {"input": DB_GET_INPUT_SCHEMA, "output": DB_GET_OUTPUT_SCHEMA},
    "db.set": {"input": DB_SET_INPUT_SCHEMA, "output": DB_SET_OUTPUT_SCHEMA},
    "db.delete": {"input": DB_DELETE_INPUT_SCHEMA, "output": DB_DELETE_OUTPUT_SCHEMA},
    "db.list": {"input": DB_LIST_INPUT_SCHEMA, "output": DB_LIST_OUTPUT_SCHEMA},
    "db.get_many": {
        "input": DB_GET_MANY_INPUT_SCHEMA,
        "output": DB_GET_MANY_OUTPUT_SCHEMA,
    },
    "db.set_many": {
        "input": DB_SET_MANY_INPUT_SCHEMA,
        "output": DB_SET_MANY_OUTPUT_SCHEMA,
    },
    "db.watch": {"input": DB_WATCH_INPUT_SCHEMA, "output": DB_WATCH_OUTPUT_SCHEMA},
    "platform.send": {
        "input": PLATFORM_SEND_INPUT_SCHEMA,
        "output": PLATFORM_SEND_OUTPUT_SCHEMA,
    },
    "platform.send_image": {
        "input": PLATFORM_SEND_IMAGE_INPUT_SCHEMA,
        "output": PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA,
    },
    "platform.send_chain": {
        "input": PLATFORM_SEND_CHAIN_INPUT_SCHEMA,
        "output": PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA,
    },
    "platform.send_by_session": {
        "input": PLATFORM_SEND_BY_SESSION_INPUT_SCHEMA,
        "output": PLATFORM_SEND_BY_SESSION_OUTPUT_SCHEMA,
    },
    "platform.get_group": {
        "input": PLATFORM_GET_GROUP_INPUT_SCHEMA,
        "output": PLATFORM_GET_GROUP_OUTPUT_SCHEMA,
    },
    "platform.get_members": {
        "input": PLATFORM_GET_MEMBERS_INPUT_SCHEMA,
        "output": PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA,
    },
    "session.plugin.is_enabled": {
        "input": SESSION_PLUGIN_IS_ENABLED_INPUT_SCHEMA,
        "output": SESSION_PLUGIN_IS_ENABLED_OUTPUT_SCHEMA,
    },
    "session.plugin.filter_handlers": {
        "input": SESSION_PLUGIN_FILTER_HANDLERS_INPUT_SCHEMA,
        "output": SESSION_PLUGIN_FILTER_HANDLERS_OUTPUT_SCHEMA,
    },
    "session.service.is_llm_enabled": {
        "input": SESSION_SERVICE_IS_LLM_ENABLED_INPUT_SCHEMA,
        "output": SESSION_SERVICE_IS_LLM_ENABLED_OUTPUT_SCHEMA,
    },
    "session.service.set_llm_status": {
        "input": SESSION_SERVICE_SET_LLM_STATUS_INPUT_SCHEMA,
        "output": SESSION_SERVICE_SET_LLM_STATUS_OUTPUT_SCHEMA,
    },
    "session.service.is_tts_enabled": {
        "input": SESSION_SERVICE_IS_TTS_ENABLED_INPUT_SCHEMA,
        "output": SESSION_SERVICE_IS_TTS_ENABLED_OUTPUT_SCHEMA,
    },
    "session.service.set_tts_status": {
        "input": SESSION_SERVICE_SET_TTS_STATUS_INPUT_SCHEMA,
        "output": SESSION_SERVICE_SET_TTS_STATUS_OUTPUT_SCHEMA,
    },
    "http.register_api": {
        "input": HTTP_REGISTER_API_INPUT_SCHEMA,
        "output": HTTP_REGISTER_API_OUTPUT_SCHEMA,
    },
    "http.unregister_api": {
        "input": HTTP_UNREGISTER_API_INPUT_SCHEMA,
        "output": HTTP_UNREGISTER_API_OUTPUT_SCHEMA,
    },
    "http.list_apis": {
        "input": HTTP_LIST_APIS_INPUT_SCHEMA,
        "output": HTTP_LIST_APIS_OUTPUT_SCHEMA,
    },
    "metadata.get_plugin": {
        "input": METADATA_GET_PLUGIN_INPUT_SCHEMA,
        "output": METADATA_GET_PLUGIN_OUTPUT_SCHEMA,
    },
    "metadata.list_plugins": {
        "input": METADATA_LIST_PLUGINS_INPUT_SCHEMA,
        "output": METADATA_LIST_PLUGINS_OUTPUT_SCHEMA,
    },
    "metadata.get_plugin_config": {
        "input": METADATA_GET_PLUGIN_CONFIG_INPUT_SCHEMA,
        "output": METADATA_GET_PLUGIN_CONFIG_OUTPUT_SCHEMA,
    },
    "system.get_data_dir": {
        "input": SYSTEM_GET_DATA_DIR_INPUT_SCHEMA,
        "output": SYSTEM_GET_DATA_DIR_OUTPUT_SCHEMA,
    },
    "system.text_to_image": {
        "input": SYSTEM_TEXT_TO_IMAGE_INPUT_SCHEMA,
        "output": SYSTEM_TEXT_TO_IMAGE_OUTPUT_SCHEMA,
    },
    "system.html_render": {
        "input": SYSTEM_HTML_RENDER_INPUT_SCHEMA,
        "output": SYSTEM_HTML_RENDER_OUTPUT_SCHEMA,
    },
    "system.session_waiter.register": {
        "input": SYSTEM_SESSION_WAITER_REGISTER_INPUT_SCHEMA,
        "output": SYSTEM_SESSION_WAITER_REGISTER_OUTPUT_SCHEMA,
    },
    "system.session_waiter.unregister": {
        "input": SYSTEM_SESSION_WAITER_UNREGISTER_INPUT_SCHEMA,
        "output": SYSTEM_SESSION_WAITER_UNREGISTER_OUTPUT_SCHEMA,
    },
    "system.event.react": {
        "input": SYSTEM_EVENT_REACT_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_REACT_OUTPUT_SCHEMA,
    },
    "system.event.send_typing": {
        "input": SYSTEM_EVENT_SEND_TYPING_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_SEND_TYPING_OUTPUT_SCHEMA,
    },
    "system.event.send_streaming": {
        "input": SYSTEM_EVENT_SEND_STREAMING_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_SEND_STREAMING_OUTPUT_SCHEMA,
    },
    "system.event.send_streaming_chunk": {
        "input": SYSTEM_EVENT_SEND_STREAMING_CHUNK_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_SEND_STREAMING_CHUNK_OUTPUT_SCHEMA,
    },
    "system.event.send_streaming_close": {
        "input": SYSTEM_EVENT_SEND_STREAMING_CLOSE_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_SEND_STREAMING_CLOSE_OUTPUT_SCHEMA,
    },
}


__all__ = [
    "BUILTIN_CAPABILITY_SCHEMAS",
    "DB_DELETE_INPUT_SCHEMA",
    "DB_DELETE_OUTPUT_SCHEMA",
    "DB_GET_INPUT_SCHEMA",
    "DB_GET_MANY_INPUT_SCHEMA",
    "DB_GET_MANY_OUTPUT_SCHEMA",
    "DB_GET_OUTPUT_SCHEMA",
    "DB_LIST_INPUT_SCHEMA",
    "DB_LIST_OUTPUT_SCHEMA",
    "DB_SET_INPUT_SCHEMA",
    "DB_SET_MANY_INPUT_SCHEMA",
    "DB_SET_MANY_OUTPUT_SCHEMA",
    "DB_SET_OUTPUT_SCHEMA",
    "DB_WATCH_INPUT_SCHEMA",
    "DB_WATCH_OUTPUT_SCHEMA",
    "HTTP_LIST_APIS_INPUT_SCHEMA",
    "HTTP_LIST_APIS_OUTPUT_SCHEMA",
    "HTTP_REGISTER_API_INPUT_SCHEMA",
    "HTTP_REGISTER_API_OUTPUT_SCHEMA",
    "HTTP_UNREGISTER_API_INPUT_SCHEMA",
    "HTTP_UNREGISTER_API_OUTPUT_SCHEMA",
    "JSONSchema",
    "LLM_CHAT_INPUT_SCHEMA",
    "LLM_CHAT_OUTPUT_SCHEMA",
    "LLM_CHAT_RAW_INPUT_SCHEMA",
    "LLM_CHAT_RAW_OUTPUT_SCHEMA",
    "LLM_STREAM_CHAT_INPUT_SCHEMA",
    "LLM_STREAM_CHAT_OUTPUT_SCHEMA",
    "MEMORY_DELETE_INPUT_SCHEMA",
    "MEMORY_DELETE_MANY_INPUT_SCHEMA",
    "MEMORY_DELETE_MANY_OUTPUT_SCHEMA",
    "MEMORY_DELETE_OUTPUT_SCHEMA",
    "MEMORY_GET_INPUT_SCHEMA",
    "MEMORY_GET_MANY_INPUT_SCHEMA",
    "MEMORY_GET_MANY_OUTPUT_SCHEMA",
    "MEMORY_GET_OUTPUT_SCHEMA",
    "MEMORY_SAVE_INPUT_SCHEMA",
    "MEMORY_SAVE_OUTPUT_SCHEMA",
    "MEMORY_SAVE_WITH_TTL_INPUT_SCHEMA",
    "MEMORY_SAVE_WITH_TTL_OUTPUT_SCHEMA",
    "MEMORY_SEARCH_INPUT_SCHEMA",
    "MEMORY_SEARCH_OUTPUT_SCHEMA",
    "MEMORY_STATS_INPUT_SCHEMA",
    "MEMORY_STATS_OUTPUT_SCHEMA",
    "METADATA_GET_PLUGIN_CONFIG_INPUT_SCHEMA",
    "METADATA_GET_PLUGIN_CONFIG_OUTPUT_SCHEMA",
    "METADATA_GET_PLUGIN_INPUT_SCHEMA",
    "METADATA_GET_PLUGIN_OUTPUT_SCHEMA",
    "METADATA_LIST_PLUGINS_INPUT_SCHEMA",
    "METADATA_LIST_PLUGINS_OUTPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_INPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA",
    "PLATFORM_GET_GROUP_INPUT_SCHEMA",
    "PLATFORM_GET_GROUP_OUTPUT_SCHEMA",
    "PLATFORM_SEND_CHAIN_INPUT_SCHEMA",
    "PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_INPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_OUTPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_INPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA",
    "PLATFORM_SEND_INPUT_SCHEMA",
    "PLATFORM_SEND_OUTPUT_SCHEMA",
    "SESSION_PLUGIN_FILTER_HANDLERS_INPUT_SCHEMA",
    "SESSION_PLUGIN_FILTER_HANDLERS_OUTPUT_SCHEMA",
    "SESSION_PLUGIN_IS_ENABLED_INPUT_SCHEMA",
    "SESSION_PLUGIN_IS_ENABLED_OUTPUT_SCHEMA",
    "SESSION_REF_SCHEMA",
    "SESSION_SERVICE_IS_LLM_ENABLED_INPUT_SCHEMA",
    "SESSION_SERVICE_IS_LLM_ENABLED_OUTPUT_SCHEMA",
    "SESSION_SERVICE_IS_TTS_ENABLED_INPUT_SCHEMA",
    "SESSION_SERVICE_IS_TTS_ENABLED_OUTPUT_SCHEMA",
    "SESSION_SERVICE_SET_LLM_STATUS_INPUT_SCHEMA",
    "SESSION_SERVICE_SET_LLM_STATUS_OUTPUT_SCHEMA",
    "SESSION_SERVICE_SET_TTS_STATUS_INPUT_SCHEMA",
    "SESSION_SERVICE_SET_TTS_STATUS_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_REACT_INPUT_SCHEMA",
    "SYSTEM_EVENT_REACT_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_OUTPUT_SCHEMA",
]
