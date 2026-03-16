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
SYSTEM_FILE_REGISTER_INPUT_SCHEMA = _object_schema(
    required=("path",),
    path={"type": "string"},
    timeout=_nullable({"type": "number"}),
)
SYSTEM_FILE_REGISTER_OUTPUT_SCHEMA = _object_schema(
    required=("token", "url"),
    token={"type": "string"},
    url={"type": "string"},
)
SYSTEM_FILE_HANDLE_INPUT_SCHEMA = _object_schema(
    required=("token",),
    token={"type": "string"},
)
SYSTEM_FILE_HANDLE_OUTPUT_SCHEMA = _object_schema(
    required=("path",),
    path={"type": "string"},
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
SYSTEM_EVENT_LLM_GET_STATE_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_LLM_GET_STATE_OUTPUT_SCHEMA = _object_schema(
    required=("should_call_llm", "requested_llm"),
    should_call_llm={"type": "boolean"},
    requested_llm={"type": "boolean"},
)
SYSTEM_EVENT_LLM_REQUEST_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_LLM_REQUEST_OUTPUT_SCHEMA = _object_schema(
    required=("should_call_llm", "requested_llm"),
    should_call_llm={"type": "boolean"},
    requested_llm={"type": "boolean"},
)
SYSTEM_EVENT_RESULT_GET_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_RESULT_GET_OUTPUT_SCHEMA = _object_schema(
    required=("result",),
    result=_nullable({"type": "object"}),
)
SYSTEM_EVENT_RESULT_SET_INPUT_SCHEMA = _object_schema(
    required=("result",),
    target=_nullable(SESSION_REF_SCHEMA),
    result={"type": "object"},
)
SYSTEM_EVENT_RESULT_SET_OUTPUT_SCHEMA = _object_schema(
    required=("result",),
    result={"type": "object"},
)
SYSTEM_EVENT_RESULT_CLEAR_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_RESULT_CLEAR_OUTPUT_SCHEMA = _object_schema()
SYSTEM_EVENT_HANDLER_WHITELIST_GET_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
)
SYSTEM_EVENT_HANDLER_WHITELIST_GET_OUTPUT_SCHEMA = _object_schema(
    required=("plugin_names",),
    plugin_names=_nullable({"type": "array", "items": {"type": "string"}}),
)
SYSTEM_EVENT_HANDLER_WHITELIST_SET_INPUT_SCHEMA = _object_schema(
    target=_nullable(SESSION_REF_SCHEMA),
    plugin_names=_nullable({"type": "array", "items": {"type": "string"}}),
)
SYSTEM_EVENT_HANDLER_WHITELIST_SET_OUTPUT_SCHEMA = _object_schema(
    required=("plugin_names",),
    plugin_names=_nullable({"type": "array", "items": {"type": "string"}}),
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
PLATFORM_INSTANCE_SCHEMA = _object_schema(
    required=("id", "name", "type", "status"),
    id={"type": "string"},
    name={"type": "string"},
    type={"type": "string"},
    status={"type": "string"},
)
PLATFORM_LIST_INSTANCES_INPUT_SCHEMA = _object_schema()
PLATFORM_LIST_INSTANCES_OUTPUT_SCHEMA = _object_schema(
    required=("platforms",),
    platforms={"type": "array", "items": PLATFORM_INSTANCE_SCHEMA},
)
PLATFORM_ERROR_SCHEMA = _object_schema(
    required=("message", "timestamp"),
    message={"type": "string"},
    timestamp={"type": "string"},
    traceback=_nullable({"type": "string"}),
)
PLATFORM_MANAGER_STATE_SCHEMA = _object_schema(
    required=("id", "name", "type", "status", "errors", "unified_webhook"),
    id={"type": "string"},
    name={"type": "string"},
    type={"type": "string"},
    status={"type": "string"},
    errors={"type": "array", "items": PLATFORM_ERROR_SCHEMA},
    last_error=_nullable(PLATFORM_ERROR_SCHEMA),
    unified_webhook={"type": "boolean"},
)
PLATFORM_STATS_SCHEMA = _object_schema(
    required=(
        "id",
        "type",
        "display_name",
        "status",
        "error_count",
        "unified_webhook",
    ),
    id={"type": "string"},
    type={"type": "string"},
    display_name={"type": "string"},
    status={"type": "string"},
    started_at=_nullable({"type": "string"}),
    error_count={"type": "integer"},
    last_error=_nullable(PLATFORM_ERROR_SCHEMA),
    unified_webhook={"type": "boolean"},
    meta={"type": "object"},
)
PLATFORM_MANAGER_GET_BY_ID_INPUT_SCHEMA = _object_schema(
    required=("platform_id",),
    platform_id={"type": "string"},
)
PLATFORM_MANAGER_GET_BY_ID_OUTPUT_SCHEMA = _object_schema(
    required=("platform",),
    platform=_nullable(PLATFORM_MANAGER_STATE_SCHEMA),
)
PLATFORM_MANAGER_CLEAR_ERRORS_INPUT_SCHEMA = _object_schema(
    required=("platform_id",),
    platform_id={"type": "string"},
)
PLATFORM_MANAGER_CLEAR_ERRORS_OUTPUT_SCHEMA = _object_schema()
PLATFORM_MANAGER_GET_STATS_INPUT_SCHEMA = _object_schema(
    required=("platform_id",),
    platform_id={"type": "string"},
)
PLATFORM_MANAGER_GET_STATS_OUTPUT_SCHEMA = _object_schema(
    required=("stats",),
    stats=_nullable(PLATFORM_STATS_SCHEMA),
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
PERSONA_RECORD_SCHEMA = _object_schema(
    required=("persona_id", "system_prompt", "begin_dialogs", "sort_order"),
    persona_id={"type": "string"},
    system_prompt={"type": "string"},
    begin_dialogs={"type": "array", "items": {"type": "string"}},
    tools=_nullable({"type": "array", "items": {"type": "string"}}),
    skills=_nullable({"type": "array", "items": {"type": "string"}}),
    custom_error_message=_nullable({"type": "string"}),
    folder_id=_nullable({"type": "string"}),
    sort_order={"type": "integer"},
    created_at=_nullable({"type": "string"}),
    updated_at=_nullable({"type": "string"}),
)
PERSONA_CREATE_SCHEMA = _object_schema(
    required=("persona_id", "system_prompt"),
    persona_id={"type": "string"},
    system_prompt={"type": "string"},
    begin_dialogs={"type": "array", "items": {"type": "string"}},
    tools=_nullable({"type": "array", "items": {"type": "string"}}),
    skills=_nullable({"type": "array", "items": {"type": "string"}}),
    custom_error_message=_nullable({"type": "string"}),
    folder_id=_nullable({"type": "string"}),
    sort_order={"type": "integer"},
)
PERSONA_UPDATE_SCHEMA = _object_schema(
    system_prompt=_nullable({"type": "string"}),
    begin_dialogs=_nullable({"type": "array", "items": {"type": "string"}}),
    tools=_nullable({"type": "array", "items": {"type": "string"}}),
    skills=_nullable({"type": "array", "items": {"type": "string"}}),
    custom_error_message=_nullable({"type": "string"}),
)
PERSONA_GET_INPUT_SCHEMA = _object_schema(
    required=("persona_id",),
    persona_id={"type": "string"},
)
PERSONA_GET_OUTPUT_SCHEMA = _object_schema(
    required=("persona",),
    persona=PERSONA_RECORD_SCHEMA,
)
PERSONA_LIST_INPUT_SCHEMA = _object_schema()
PERSONA_LIST_OUTPUT_SCHEMA = _object_schema(
    required=("personas",),
    personas={"type": "array", "items": PERSONA_RECORD_SCHEMA},
)
PERSONA_CREATE_INPUT_SCHEMA = _object_schema(
    required=("persona",),
    persona=PERSONA_CREATE_SCHEMA,
)
PERSONA_CREATE_OUTPUT_SCHEMA = _object_schema(
    required=("persona",),
    persona=PERSONA_RECORD_SCHEMA,
)
PERSONA_UPDATE_INPUT_SCHEMA = _object_schema(
    required=("persona_id", "persona"),
    persona_id={"type": "string"},
    persona=PERSONA_UPDATE_SCHEMA,
)
PERSONA_UPDATE_OUTPUT_SCHEMA = _object_schema(
    required=("persona",),
    persona=_nullable(PERSONA_RECORD_SCHEMA),
)
PERSONA_DELETE_INPUT_SCHEMA = _object_schema(
    required=("persona_id",),
    persona_id={"type": "string"},
)
PERSONA_DELETE_OUTPUT_SCHEMA = _object_schema()
CONVERSATION_RECORD_SCHEMA = _object_schema(
    required=("conversation_id", "session", "platform_id", "history"),
    conversation_id={"type": "string"},
    session={"type": "string"},
    platform_id={"type": "string"},
    history={"type": "array", "items": {"type": "object"}},
    title=_nullable({"type": "string"}),
    persona_id=_nullable({"type": "string"}),
    created_at=_nullable({"type": "string"}),
    updated_at=_nullable({"type": "string"}),
    token_usage=_nullable({"type": "integer"}),
)
CONVERSATION_CREATE_SCHEMA = _object_schema(
    platform_id=_nullable({"type": "string"}),
    history=_nullable({"type": "array", "items": {"type": "object"}}),
    title=_nullable({"type": "string"}),
    persona_id=_nullable({"type": "string"}),
)
CONVERSATION_UPDATE_SCHEMA = _object_schema(
    history=_nullable({"type": "array", "items": {"type": "object"}}),
    title=_nullable({"type": "string"}),
    persona_id=_nullable({"type": "string"}),
    token_usage=_nullable({"type": "integer"}),
)
CONVERSATION_NEW_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
    conversation=_nullable(CONVERSATION_CREATE_SCHEMA),
)
CONVERSATION_NEW_OUTPUT_SCHEMA = _object_schema(
    required=("conversation_id",),
    conversation_id={"type": "string"},
)
CONVERSATION_SWITCH_INPUT_SCHEMA = _object_schema(
    required=("session", "conversation_id"),
    session={"type": "string"},
    conversation_id={"type": "string"},
)
CONVERSATION_SWITCH_OUTPUT_SCHEMA = _object_schema()
CONVERSATION_DELETE_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
    conversation_id=_nullable({"type": "string"}),
)
CONVERSATION_DELETE_OUTPUT_SCHEMA = _object_schema()
CONVERSATION_GET_INPUT_SCHEMA = _object_schema(
    required=("session", "conversation_id"),
    session={"type": "string"},
    conversation_id={"type": "string"},
    create_if_not_exists={"type": "boolean"},
)
CONVERSATION_GET_OUTPUT_SCHEMA = _object_schema(
    required=("conversation",),
    conversation=_nullable(CONVERSATION_RECORD_SCHEMA),
)
CONVERSATION_LIST_INPUT_SCHEMA = _object_schema(
    session=_nullable({"type": "string"}),
    platform_id=_nullable({"type": "string"}),
)
CONVERSATION_LIST_OUTPUT_SCHEMA = _object_schema(
    required=("conversations",),
    conversations={"type": "array", "items": CONVERSATION_RECORD_SCHEMA},
)
CONVERSATION_UPDATE_INPUT_SCHEMA = _object_schema(
    required=("session",),
    session={"type": "string"},
    conversation_id=_nullable({"type": "string"}),
    conversation=_nullable(CONVERSATION_UPDATE_SCHEMA),
)
CONVERSATION_UPDATE_OUTPUT_SCHEMA = _object_schema()
KNOWLEDGE_BASE_RECORD_SCHEMA = _object_schema(
    required=("kb_id", "kb_name", "embedding_provider_id", "doc_count", "chunk_count"),
    kb_id={"type": "string"},
    kb_name={"type": "string"},
    description=_nullable({"type": "string"}),
    emoji=_nullable({"type": "string"}),
    embedding_provider_id={"type": "string"},
    rerank_provider_id=_nullable({"type": "string"}),
    chunk_size=_nullable({"type": "integer"}),
    chunk_overlap=_nullable({"type": "integer"}),
    top_k_dense=_nullable({"type": "integer"}),
    top_k_sparse=_nullable({"type": "integer"}),
    top_m_final=_nullable({"type": "integer"}),
    doc_count={"type": "integer"},
    chunk_count={"type": "integer"},
    created_at=_nullable({"type": "string"}),
    updated_at=_nullable({"type": "string"}),
)
KNOWLEDGE_BASE_CREATE_SCHEMA = _object_schema(
    required=("kb_name", "embedding_provider_id"),
    kb_name={"type": "string"},
    embedding_provider_id={"type": "string"},
    description=_nullable({"type": "string"}),
    emoji=_nullable({"type": "string"}),
    rerank_provider_id=_nullable({"type": "string"}),
    chunk_size=_nullable({"type": "integer"}),
    chunk_overlap=_nullable({"type": "integer"}),
    top_k_dense=_nullable({"type": "integer"}),
    top_k_sparse=_nullable({"type": "integer"}),
    top_m_final=_nullable({"type": "integer"}),
)
KB_GET_INPUT_SCHEMA = _object_schema(
    required=("kb_id",),
    kb_id={"type": "string"},
)
KB_GET_OUTPUT_SCHEMA = _object_schema(
    required=("kb",),
    kb=_nullable(KNOWLEDGE_BASE_RECORD_SCHEMA),
)
KB_CREATE_INPUT_SCHEMA = _object_schema(
    required=("kb",),
    kb=KNOWLEDGE_BASE_CREATE_SCHEMA,
)
KB_CREATE_OUTPUT_SCHEMA = _object_schema(
    required=("kb",),
    kb=KNOWLEDGE_BASE_RECORD_SCHEMA,
)
KB_DELETE_INPUT_SCHEMA = _object_schema(
    required=("kb_id",),
    kb_id={"type": "string"},
)
KB_DELETE_OUTPUT_SCHEMA = _object_schema(
    required=("deleted",),
    deleted={"type": "boolean"},
)
REGISTRY_COMMAND_REGISTER_INPUT_SCHEMA = _object_schema(
    required=("command_name", "handler_full_name"),
    command_name={"type": "string"},
    handler_full_name={"type": "string"},
    source_event_type={"type": "string"},
    desc={"type": "string"},
    priority={"type": "integer"},
    use_regex={"type": "boolean"},
    ignore_prefix={"type": "boolean"},
)
REGISTRY_COMMAND_REGISTER_OUTPUT_SCHEMA = _object_schema()
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
REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_INPUT_SCHEMA = _object_schema(
    required=("event_type",),
    event_type={"type": "string"},
)
REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_OUTPUT_SCHEMA = _object_schema(
    required=("handlers",),
    handlers={"type": "array", "items": {"type": "object"}},
)
REGISTRY_GET_HANDLER_BY_FULL_NAME_INPUT_SCHEMA = _object_schema(
    required=("full_name",),
    full_name={"type": "string"},
)
REGISTRY_GET_HANDLER_BY_FULL_NAME_OUTPUT_SCHEMA = _object_schema(
    required=("handler",),
    handler=_nullable({"type": "object"}),
)
PROVIDER_META_SCHEMA = _object_schema(
    required=("id", "type", "provider_type"),
    id={"type": "string"},
    model=_nullable({"type": "string"}),
    type={"type": "string"},
    provider_type={"type": "string"},
)
MANAGED_PROVIDER_RECORD_SCHEMA = _object_schema(
    required=("id", "type", "provider_type", "loaded", "enabled"),
    id={"type": "string"},
    model=_nullable({"type": "string"}),
    type={"type": "string"},
    provider_type={"type": "string"},
    loaded={"type": "boolean"},
    enabled={"type": "boolean"},
    provider_source_id=_nullable({"type": "string"}),
)
PROVIDER_CHANGE_EVENT_SCHEMA = _object_schema(
    required=("provider_id", "provider_type"),
    provider_id={"type": "string"},
    provider_type={"type": "string"},
    umo=_nullable({"type": "string"}),
)
LLM_TOOL_SPEC_SCHEMA = _object_schema(
    required=("name", "description", "parameters_schema", "active"),
    name={"type": "string"},
    description={"type": "string"},
    parameters_schema={"type": "object"},
    handler_ref=_nullable({"type": "string"}),
    handler_capability=_nullable({"type": "string"}),
    active={"type": "boolean"},
)
AGENT_SPEC_SCHEMA = _object_schema(
    required=("name", "description", "tool_names", "runner_class"),
    name={"type": "string"},
    description={"type": "string"},
    tool_names={"type": "array", "items": {"type": "string"}},
    runner_class={"type": "string"},
)
PROVIDER_GET_USING_INPUT_SCHEMA = _object_schema(umo=_nullable({"type": "string"}))
PROVIDER_GET_USING_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(PROVIDER_META_SCHEMA),
)
PROVIDER_GET_BY_ID_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
)
PROVIDER_GET_BY_ID_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(PROVIDER_META_SCHEMA),
)
PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_INPUT_SCHEMA = _object_schema(
    umo=_nullable({"type": "string"}),
)
PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_OUTPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id=_nullable({"type": "string"}),
)
PROVIDER_LIST_ALL_INPUT_SCHEMA = _object_schema()
PROVIDER_LIST_ALL_OUTPUT_SCHEMA = _object_schema(
    required=("providers",),
    providers={"type": "array", "items": PROVIDER_META_SCHEMA},
)
PROVIDER_STT_GET_TEXT_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "audio_url"),
    provider_id={"type": "string"},
    audio_url={"type": "string"},
)
PROVIDER_STT_GET_TEXT_OUTPUT_SCHEMA = _object_schema(
    required=("text",),
    text={"type": "string"},
)
PROVIDER_TTS_GET_AUDIO_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "text"),
    provider_id={"type": "string"},
    text={"type": "string"},
)
PROVIDER_TTS_GET_AUDIO_OUTPUT_SCHEMA = _object_schema(
    required=("audio_path",),
    audio_path={"type": "string"},
)
PROVIDER_TTS_SUPPORT_STREAM_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
)
PROVIDER_TTS_SUPPORT_STREAM_OUTPUT_SCHEMA = _object_schema(
    required=("supported",),
    supported={"type": "boolean"},
)
PROVIDER_TTS_AUDIO_CHUNK_SCHEMA = _object_schema(
    required=("audio_base64",),
    audio_base64={"type": "string"},
    text=_nullable({"type": "string"}),
)
PROVIDER_TTS_GET_AUDIO_STREAM_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
    text=_nullable({"type": "string"}),
    text_chunks={"type": "array", "items": {"type": "string"}},
)
PROVIDER_TTS_GET_AUDIO_STREAM_OUTPUT_SCHEMA = PROVIDER_TTS_AUDIO_CHUNK_SCHEMA
PROVIDER_EMBEDDING_GET_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "text"),
    provider_id={"type": "string"},
    text={"type": "string"},
)
PROVIDER_EMBEDDING_GET_OUTPUT_SCHEMA = _object_schema(
    required=("embedding",),
    embedding={"type": "array", "items": {"type": "number"}},
)
PROVIDER_EMBEDDING_GET_MANY_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "texts"),
    provider_id={"type": "string"},
    texts={"type": "array", "items": {"type": "string"}},
)
PROVIDER_EMBEDDING_GET_MANY_OUTPUT_SCHEMA = _object_schema(
    required=("embeddings",),
    embeddings={
        "type": "array",
        "items": {"type": "array", "items": {"type": "number"}},
    },
)
PROVIDER_EMBEDDING_GET_DIM_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
)
PROVIDER_EMBEDDING_GET_DIM_OUTPUT_SCHEMA = _object_schema(
    required=("dim",),
    dim={"type": "integer"},
)
PROVIDER_RERANK_RESULT_SCHEMA = _object_schema(
    required=("index", "score", "document"),
    index={"type": "integer"},
    score={"type": "number"},
    document={"type": "string"},
)
PROVIDER_RERANK_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "query", "documents"),
    provider_id={"type": "string"},
    query={"type": "string"},
    documents={"type": "array", "items": {"type": "string"}},
    top_n=_nullable({"type": "integer"}),
)
PROVIDER_RERANK_OUTPUT_SCHEMA = _object_schema(
    required=("results",),
    results={"type": "array", "items": PROVIDER_RERANK_RESULT_SCHEMA},
)
PROVIDER_MANAGER_SET_INPUT_SCHEMA = _object_schema(
    required=("provider_id", "provider_type"),
    provider_id={"type": "string"},
    provider_type={"type": "string"},
    umo=_nullable({"type": "string"}),
)
PROVIDER_MANAGER_SET_OUTPUT_SCHEMA = _object_schema()
PROVIDER_MANAGER_GET_BY_ID_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
)
PROVIDER_MANAGER_GET_BY_ID_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(MANAGED_PROVIDER_RECORD_SCHEMA),
)
PROVIDER_MANAGER_LOAD_INPUT_SCHEMA = _object_schema(
    required=("provider_config",),
    provider_config={"type": "object"},
)
PROVIDER_MANAGER_LOAD_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(MANAGED_PROVIDER_RECORD_SCHEMA),
)
PROVIDER_MANAGER_TERMINATE_INPUT_SCHEMA = _object_schema(
    required=("provider_id",),
    provider_id={"type": "string"},
)
PROVIDER_MANAGER_TERMINATE_OUTPUT_SCHEMA = _object_schema()
PROVIDER_MANAGER_CREATE_INPUT_SCHEMA = _object_schema(
    required=("provider_config",),
    provider_config={"type": "object"},
)
PROVIDER_MANAGER_CREATE_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(MANAGED_PROVIDER_RECORD_SCHEMA),
)
PROVIDER_MANAGER_UPDATE_INPUT_SCHEMA = _object_schema(
    required=("origin_provider_id", "new_config"),
    origin_provider_id={"type": "string"},
    new_config={"type": "object"},
)
PROVIDER_MANAGER_UPDATE_OUTPUT_SCHEMA = _object_schema(
    required=("provider",),
    provider=_nullable(MANAGED_PROVIDER_RECORD_SCHEMA),
)
PROVIDER_MANAGER_DELETE_INPUT_SCHEMA = _object_schema(
    provider_id=_nullable({"type": "string"}),
    provider_source_id=_nullable({"type": "string"}),
)
PROVIDER_MANAGER_DELETE_OUTPUT_SCHEMA = _object_schema()
PROVIDER_MANAGER_GET_INSTS_INPUT_SCHEMA = _object_schema()
PROVIDER_MANAGER_GET_INSTS_OUTPUT_SCHEMA = _object_schema(
    required=("providers",),
    providers={"type": "array", "items": MANAGED_PROVIDER_RECORD_SCHEMA},
)
PROVIDER_MANAGER_WATCH_CHANGES_INPUT_SCHEMA = _object_schema()
PROVIDER_MANAGER_WATCH_CHANGES_OUTPUT_SCHEMA = _object_schema(
    required=("provider_id", "provider_type"),
    provider_id={"type": "string"},
    provider_type={"type": "string"},
    umo=_nullable({"type": "string"}),
)
LLM_TOOL_MANAGER_GET_INPUT_SCHEMA = _object_schema()
LLM_TOOL_MANAGER_GET_OUTPUT_SCHEMA = _object_schema(
    required=("registered", "active"),
    registered={"type": "array", "items": LLM_TOOL_SPEC_SCHEMA},
    active={"type": "array", "items": LLM_TOOL_SPEC_SCHEMA},
)
LLM_TOOL_MANAGER_ACTIVATE_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
LLM_TOOL_MANAGER_ACTIVATE_OUTPUT_SCHEMA = _object_schema(
    required=("activated",),
    activated={"type": "boolean"},
)
LLM_TOOL_MANAGER_DEACTIVATE_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
LLM_TOOL_MANAGER_DEACTIVATE_OUTPUT_SCHEMA = _object_schema(
    required=("deactivated",),
    deactivated={"type": "boolean"},
)
LLM_TOOL_MANAGER_ADD_INPUT_SCHEMA = _object_schema(
    required=("tools",),
    tools={"type": "array", "items": LLM_TOOL_SPEC_SCHEMA},
)
LLM_TOOL_MANAGER_ADD_OUTPUT_SCHEMA = _object_schema(
    required=("names",),
    names={"type": "array", "items": {"type": "string"}},
)
LLM_TOOL_MANAGER_REMOVE_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
LLM_TOOL_MANAGER_REMOVE_OUTPUT_SCHEMA = _object_schema(
    required=("removed",),
    removed={"type": "boolean"},
)
AGENT_TOOL_LOOP_RUN_INPUT_SCHEMA = _object_schema(
    prompt=_nullable({"type": "string"}),
    system_prompt=_nullable({"type": "string"}),
    session_id=_nullable({"type": "string"}),
    contexts={"type": "array", "items": {"type": "object"}},
    image_urls={"type": "array", "items": {"type": "string"}},
    tool_names=_nullable({"type": "array", "items": {"type": "string"}}),
    tool_calls_result={"type": "array", "items": {"type": "object"}},
    provider_id=_nullable({"type": "string"}),
    model=_nullable({"type": "string"}),
    temperature={"type": "number"},
    max_steps={"type": "integer"},
    tool_call_timeout={"type": "integer"},
)
AGENT_TOOL_LOOP_RUN_OUTPUT_SCHEMA = LLM_CHAT_RAW_OUTPUT_SCHEMA
AGENT_REGISTRY_LIST_INPUT_SCHEMA = _object_schema()
AGENT_REGISTRY_LIST_OUTPUT_SCHEMA = _object_schema(
    required=("agents",),
    agents={"type": "array", "items": AGENT_SPEC_SCHEMA},
)
AGENT_REGISTRY_GET_INPUT_SCHEMA = _object_schema(
    required=("name",),
    name={"type": "string"},
)
AGENT_REGISTRY_GET_OUTPUT_SCHEMA = _object_schema(
    required=("agent",),
    agent=_nullable(AGENT_SPEC_SCHEMA),
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
    "platform.list_instances": {
        "input": PLATFORM_LIST_INSTANCES_INPUT_SCHEMA,
        "output": PLATFORM_LIST_INSTANCES_OUTPUT_SCHEMA,
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
    "persona.get": {
        "input": PERSONA_GET_INPUT_SCHEMA,
        "output": PERSONA_GET_OUTPUT_SCHEMA,
    },
    "persona.list": {
        "input": PERSONA_LIST_INPUT_SCHEMA,
        "output": PERSONA_LIST_OUTPUT_SCHEMA,
    },
    "persona.create": {
        "input": PERSONA_CREATE_INPUT_SCHEMA,
        "output": PERSONA_CREATE_OUTPUT_SCHEMA,
    },
    "persona.update": {
        "input": PERSONA_UPDATE_INPUT_SCHEMA,
        "output": PERSONA_UPDATE_OUTPUT_SCHEMA,
    },
    "persona.delete": {
        "input": PERSONA_DELETE_INPUT_SCHEMA,
        "output": PERSONA_DELETE_OUTPUT_SCHEMA,
    },
    "conversation.new": {
        "input": CONVERSATION_NEW_INPUT_SCHEMA,
        "output": CONVERSATION_NEW_OUTPUT_SCHEMA,
    },
    "conversation.switch": {
        "input": CONVERSATION_SWITCH_INPUT_SCHEMA,
        "output": CONVERSATION_SWITCH_OUTPUT_SCHEMA,
    },
    "conversation.delete": {
        "input": CONVERSATION_DELETE_INPUT_SCHEMA,
        "output": CONVERSATION_DELETE_OUTPUT_SCHEMA,
    },
    "conversation.get": {
        "input": CONVERSATION_GET_INPUT_SCHEMA,
        "output": CONVERSATION_GET_OUTPUT_SCHEMA,
    },
    "conversation.list": {
        "input": CONVERSATION_LIST_INPUT_SCHEMA,
        "output": CONVERSATION_LIST_OUTPUT_SCHEMA,
    },
    "conversation.update": {
        "input": CONVERSATION_UPDATE_INPUT_SCHEMA,
        "output": CONVERSATION_UPDATE_OUTPUT_SCHEMA,
    },
    "kb.get": {"input": KB_GET_INPUT_SCHEMA, "output": KB_GET_OUTPUT_SCHEMA},
    "kb.create": {
        "input": KB_CREATE_INPUT_SCHEMA,
        "output": KB_CREATE_OUTPUT_SCHEMA,
    },
    "kb.delete": {
        "input": KB_DELETE_INPUT_SCHEMA,
        "output": KB_DELETE_OUTPUT_SCHEMA,
    },
    "registry.command.register": {
        "input": REGISTRY_COMMAND_REGISTER_INPUT_SCHEMA,
        "output": REGISTRY_COMMAND_REGISTER_OUTPUT_SCHEMA,
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
    "registry.get_handlers_by_event_type": {
        "input": REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_INPUT_SCHEMA,
        "output": REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_OUTPUT_SCHEMA,
    },
    "registry.get_handler_by_full_name": {
        "input": REGISTRY_GET_HANDLER_BY_FULL_NAME_INPUT_SCHEMA,
        "output": REGISTRY_GET_HANDLER_BY_FULL_NAME_OUTPUT_SCHEMA,
    },
    "provider.get_using": {
        "input": PROVIDER_GET_USING_INPUT_SCHEMA,
        "output": PROVIDER_GET_USING_OUTPUT_SCHEMA,
    },
    "provider.get_by_id": {
        "input": PROVIDER_GET_BY_ID_INPUT_SCHEMA,
        "output": PROVIDER_GET_BY_ID_OUTPUT_SCHEMA,
    },
    "provider.get_current_chat_provider_id": {
        "input": PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_INPUT_SCHEMA,
        "output": PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_OUTPUT_SCHEMA,
    },
    "provider.list_all": {
        "input": PROVIDER_LIST_ALL_INPUT_SCHEMA,
        "output": PROVIDER_LIST_ALL_OUTPUT_SCHEMA,
    },
    "provider.list_all_tts": {
        "input": PROVIDER_LIST_ALL_INPUT_SCHEMA,
        "output": PROVIDER_LIST_ALL_OUTPUT_SCHEMA,
    },
    "provider.list_all_stt": {
        "input": PROVIDER_LIST_ALL_INPUT_SCHEMA,
        "output": PROVIDER_LIST_ALL_OUTPUT_SCHEMA,
    },
    "provider.list_all_embedding": {
        "input": PROVIDER_LIST_ALL_INPUT_SCHEMA,
        "output": PROVIDER_LIST_ALL_OUTPUT_SCHEMA,
    },
    "provider.list_all_rerank": {
        "input": PROVIDER_LIST_ALL_INPUT_SCHEMA,
        "output": PROVIDER_LIST_ALL_OUTPUT_SCHEMA,
    },
    "provider.get_using_tts": {
        "input": PROVIDER_GET_USING_INPUT_SCHEMA,
        "output": PROVIDER_GET_USING_OUTPUT_SCHEMA,
    },
    "provider.get_using_stt": {
        "input": PROVIDER_GET_USING_INPUT_SCHEMA,
        "output": PROVIDER_GET_USING_OUTPUT_SCHEMA,
    },
    "provider.stt.get_text": {
        "input": PROVIDER_STT_GET_TEXT_INPUT_SCHEMA,
        "output": PROVIDER_STT_GET_TEXT_OUTPUT_SCHEMA,
    },
    "provider.tts.get_audio": {
        "input": PROVIDER_TTS_GET_AUDIO_INPUT_SCHEMA,
        "output": PROVIDER_TTS_GET_AUDIO_OUTPUT_SCHEMA,
    },
    "provider.tts.support_stream": {
        "input": PROVIDER_TTS_SUPPORT_STREAM_INPUT_SCHEMA,
        "output": PROVIDER_TTS_SUPPORT_STREAM_OUTPUT_SCHEMA,
    },
    "provider.tts.get_audio_stream": {
        "input": PROVIDER_TTS_GET_AUDIO_STREAM_INPUT_SCHEMA,
        "output": PROVIDER_TTS_GET_AUDIO_STREAM_OUTPUT_SCHEMA,
    },
    "provider.embedding.get_embedding": {
        "input": PROVIDER_EMBEDDING_GET_INPUT_SCHEMA,
        "output": PROVIDER_EMBEDDING_GET_OUTPUT_SCHEMA,
    },
    "provider.embedding.get_embeddings": {
        "input": PROVIDER_EMBEDDING_GET_MANY_INPUT_SCHEMA,
        "output": PROVIDER_EMBEDDING_GET_MANY_OUTPUT_SCHEMA,
    },
    "provider.embedding.get_dim": {
        "input": PROVIDER_EMBEDDING_GET_DIM_INPUT_SCHEMA,
        "output": PROVIDER_EMBEDDING_GET_DIM_OUTPUT_SCHEMA,
    },
    "provider.rerank.rerank": {
        "input": PROVIDER_RERANK_INPUT_SCHEMA,
        "output": PROVIDER_RERANK_OUTPUT_SCHEMA,
    },
    "provider.manager.set": {
        "input": PROVIDER_MANAGER_SET_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_SET_OUTPUT_SCHEMA,
    },
    "provider.manager.get_by_id": {
        "input": PROVIDER_MANAGER_GET_BY_ID_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_GET_BY_ID_OUTPUT_SCHEMA,
    },
    "provider.manager.load": {
        "input": PROVIDER_MANAGER_LOAD_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_LOAD_OUTPUT_SCHEMA,
    },
    "provider.manager.terminate": {
        "input": PROVIDER_MANAGER_TERMINATE_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_TERMINATE_OUTPUT_SCHEMA,
    },
    "provider.manager.create": {
        "input": PROVIDER_MANAGER_CREATE_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_CREATE_OUTPUT_SCHEMA,
    },
    "provider.manager.update": {
        "input": PROVIDER_MANAGER_UPDATE_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_UPDATE_OUTPUT_SCHEMA,
    },
    "provider.manager.delete": {
        "input": PROVIDER_MANAGER_DELETE_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_DELETE_OUTPUT_SCHEMA,
    },
    "provider.manager.get_insts": {
        "input": PROVIDER_MANAGER_GET_INSTS_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_GET_INSTS_OUTPUT_SCHEMA,
    },
    "provider.manager.watch_changes": {
        "input": PROVIDER_MANAGER_WATCH_CHANGES_INPUT_SCHEMA,
        "output": PROVIDER_MANAGER_WATCH_CHANGES_OUTPUT_SCHEMA,
    },
    "platform.manager.get_by_id": {
        "input": PLATFORM_MANAGER_GET_BY_ID_INPUT_SCHEMA,
        "output": PLATFORM_MANAGER_GET_BY_ID_OUTPUT_SCHEMA,
    },
    "platform.manager.clear_errors": {
        "input": PLATFORM_MANAGER_CLEAR_ERRORS_INPUT_SCHEMA,
        "output": PLATFORM_MANAGER_CLEAR_ERRORS_OUTPUT_SCHEMA,
    },
    "platform.manager.get_stats": {
        "input": PLATFORM_MANAGER_GET_STATS_INPUT_SCHEMA,
        "output": PLATFORM_MANAGER_GET_STATS_OUTPUT_SCHEMA,
    },
    "llm_tool.manager.get": {
        "input": LLM_TOOL_MANAGER_GET_INPUT_SCHEMA,
        "output": LLM_TOOL_MANAGER_GET_OUTPUT_SCHEMA,
    },
    "llm_tool.manager.activate": {
        "input": LLM_TOOL_MANAGER_ACTIVATE_INPUT_SCHEMA,
        "output": LLM_TOOL_MANAGER_ACTIVATE_OUTPUT_SCHEMA,
    },
    "llm_tool.manager.deactivate": {
        "input": LLM_TOOL_MANAGER_DEACTIVATE_INPUT_SCHEMA,
        "output": LLM_TOOL_MANAGER_DEACTIVATE_OUTPUT_SCHEMA,
    },
    "llm_tool.manager.add": {
        "input": LLM_TOOL_MANAGER_ADD_INPUT_SCHEMA,
        "output": LLM_TOOL_MANAGER_ADD_OUTPUT_SCHEMA,
    },
    "llm_tool.manager.remove": {
        "input": LLM_TOOL_MANAGER_REMOVE_INPUT_SCHEMA,
        "output": LLM_TOOL_MANAGER_REMOVE_OUTPUT_SCHEMA,
    },
    "agent.tool_loop.run": {
        "input": AGENT_TOOL_LOOP_RUN_INPUT_SCHEMA,
        "output": AGENT_TOOL_LOOP_RUN_OUTPUT_SCHEMA,
    },
    "agent.registry.list": {
        "input": AGENT_REGISTRY_LIST_INPUT_SCHEMA,
        "output": AGENT_REGISTRY_LIST_OUTPUT_SCHEMA,
    },
    "agent.registry.get": {
        "input": AGENT_REGISTRY_GET_INPUT_SCHEMA,
        "output": AGENT_REGISTRY_GET_OUTPUT_SCHEMA,
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
    "system.file.register": {
        "input": SYSTEM_FILE_REGISTER_INPUT_SCHEMA,
        "output": SYSTEM_FILE_REGISTER_OUTPUT_SCHEMA,
    },
    "system.file.handle": {
        "input": SYSTEM_FILE_HANDLE_INPUT_SCHEMA,
        "output": SYSTEM_FILE_HANDLE_OUTPUT_SCHEMA,
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
    "system.event.llm.get_state": {
        "input": SYSTEM_EVENT_LLM_GET_STATE_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_LLM_GET_STATE_OUTPUT_SCHEMA,
    },
    "system.event.llm.request": {
        "input": SYSTEM_EVENT_LLM_REQUEST_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_LLM_REQUEST_OUTPUT_SCHEMA,
    },
    "system.event.result.get": {
        "input": SYSTEM_EVENT_RESULT_GET_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_RESULT_GET_OUTPUT_SCHEMA,
    },
    "system.event.result.set": {
        "input": SYSTEM_EVENT_RESULT_SET_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_RESULT_SET_OUTPUT_SCHEMA,
    },
    "system.event.result.clear": {
        "input": SYSTEM_EVENT_RESULT_CLEAR_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_RESULT_CLEAR_OUTPUT_SCHEMA,
    },
    "system.event.handler_whitelist.get": {
        "input": SYSTEM_EVENT_HANDLER_WHITELIST_GET_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_HANDLER_WHITELIST_GET_OUTPUT_SCHEMA,
    },
    "system.event.handler_whitelist.set": {
        "input": SYSTEM_EVENT_HANDLER_WHITELIST_SET_INPUT_SCHEMA,
        "output": SYSTEM_EVENT_HANDLER_WHITELIST_SET_OUTPUT_SCHEMA,
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
    "PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_INPUT_SCHEMA",
    "PROVIDER_GET_CURRENT_CHAT_PROVIDER_ID_OUTPUT_SCHEMA",
    "PROVIDER_GET_BY_ID_INPUT_SCHEMA",
    "PROVIDER_GET_BY_ID_OUTPUT_SCHEMA",
    "PROVIDER_GET_USING_INPUT_SCHEMA",
    "PROVIDER_GET_USING_OUTPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_DIM_INPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_DIM_OUTPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_INPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_MANY_INPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_MANY_OUTPUT_SCHEMA",
    "PROVIDER_EMBEDDING_GET_OUTPUT_SCHEMA",
    "PROVIDER_CHANGE_EVENT_SCHEMA",
    "PROVIDER_LIST_ALL_INPUT_SCHEMA",
    "PROVIDER_LIST_ALL_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_CREATE_INPUT_SCHEMA",
    "PROVIDER_MANAGER_CREATE_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_DELETE_INPUT_SCHEMA",
    "PROVIDER_MANAGER_DELETE_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_GET_BY_ID_INPUT_SCHEMA",
    "PROVIDER_MANAGER_GET_BY_ID_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_GET_INSTS_INPUT_SCHEMA",
    "PROVIDER_MANAGER_GET_INSTS_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_LOAD_INPUT_SCHEMA",
    "PROVIDER_MANAGER_LOAD_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_SET_INPUT_SCHEMA",
    "PROVIDER_MANAGER_SET_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_TERMINATE_INPUT_SCHEMA",
    "PROVIDER_MANAGER_TERMINATE_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_UPDATE_INPUT_SCHEMA",
    "PROVIDER_MANAGER_UPDATE_OUTPUT_SCHEMA",
    "PROVIDER_MANAGER_WATCH_CHANGES_INPUT_SCHEMA",
    "PROVIDER_MANAGER_WATCH_CHANGES_OUTPUT_SCHEMA",
    "PROVIDER_META_SCHEMA",
    "PROVIDER_RERANK_INPUT_SCHEMA",
    "PROVIDER_RERANK_OUTPUT_SCHEMA",
    "PROVIDER_RERANK_RESULT_SCHEMA",
    "PROVIDER_STT_GET_TEXT_INPUT_SCHEMA",
    "PROVIDER_STT_GET_TEXT_OUTPUT_SCHEMA",
    "PROVIDER_TTS_AUDIO_CHUNK_SCHEMA",
    "PROVIDER_TTS_GET_AUDIO_INPUT_SCHEMA",
    "PROVIDER_TTS_GET_AUDIO_OUTPUT_SCHEMA",
    "PROVIDER_TTS_GET_AUDIO_STREAM_INPUT_SCHEMA",
    "PROVIDER_TTS_GET_AUDIO_STREAM_OUTPUT_SCHEMA",
    "PROVIDER_TTS_SUPPORT_STREAM_INPUT_SCHEMA",
    "PROVIDER_TTS_SUPPORT_STREAM_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ACTIVATE_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ACTIVATE_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ADD_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_ADD_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_REMOVE_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_REMOVE_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_DEACTIVATE_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_DEACTIVATE_OUTPUT_SCHEMA",
    "LLM_TOOL_MANAGER_GET_INPUT_SCHEMA",
    "LLM_TOOL_MANAGER_GET_OUTPUT_SCHEMA",
    "LLM_TOOL_SPEC_SCHEMA",
    "AGENT_REGISTRY_GET_INPUT_SCHEMA",
    "AGENT_REGISTRY_GET_OUTPUT_SCHEMA",
    "AGENT_REGISTRY_LIST_INPUT_SCHEMA",
    "AGENT_REGISTRY_LIST_OUTPUT_SCHEMA",
    "AGENT_SPEC_SCHEMA",
    "AGENT_TOOL_LOOP_RUN_INPUT_SCHEMA",
    "AGENT_TOOL_LOOP_RUN_OUTPUT_SCHEMA",
    "MANAGED_PROVIDER_RECORD_SCHEMA",
    "PLATFORM_ERROR_SCHEMA",
    "PLATFORM_GET_MEMBERS_INPUT_SCHEMA",
    "PLATFORM_GET_MEMBERS_OUTPUT_SCHEMA",
    "PLATFORM_GET_GROUP_INPUT_SCHEMA",
    "PLATFORM_GET_GROUP_OUTPUT_SCHEMA",
    "PLATFORM_INSTANCE_SCHEMA",
    "PLATFORM_LIST_INSTANCES_INPUT_SCHEMA",
    "PLATFORM_LIST_INSTANCES_OUTPUT_SCHEMA",
    "PLATFORM_MANAGER_CLEAR_ERRORS_INPUT_SCHEMA",
    "PLATFORM_MANAGER_CLEAR_ERRORS_OUTPUT_SCHEMA",
    "PLATFORM_MANAGER_GET_BY_ID_INPUT_SCHEMA",
    "PLATFORM_MANAGER_GET_BY_ID_OUTPUT_SCHEMA",
    "PLATFORM_MANAGER_GET_STATS_INPUT_SCHEMA",
    "PLATFORM_MANAGER_GET_STATS_OUTPUT_SCHEMA",
    "PLATFORM_MANAGER_STATE_SCHEMA",
    "PLATFORM_SEND_CHAIN_INPUT_SCHEMA",
    "PLATFORM_SEND_CHAIN_OUTPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_INPUT_SCHEMA",
    "PLATFORM_SEND_BY_SESSION_OUTPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_INPUT_SCHEMA",
    "PLATFORM_SEND_IMAGE_OUTPUT_SCHEMA",
    "PLATFORM_SEND_INPUT_SCHEMA",
    "PLATFORM_SEND_OUTPUT_SCHEMA",
    "PLATFORM_STATS_SCHEMA",
    "PERSONA_CREATE_INPUT_SCHEMA",
    "PERSONA_CREATE_OUTPUT_SCHEMA",
    "PERSONA_CREATE_SCHEMA",
    "PERSONA_DELETE_INPUT_SCHEMA",
    "PERSONA_DELETE_OUTPUT_SCHEMA",
    "PERSONA_GET_INPUT_SCHEMA",
    "PERSONA_GET_OUTPUT_SCHEMA",
    "PERSONA_LIST_INPUT_SCHEMA",
    "PERSONA_LIST_OUTPUT_SCHEMA",
    "PERSONA_RECORD_SCHEMA",
    "PERSONA_UPDATE_INPUT_SCHEMA",
    "PERSONA_UPDATE_OUTPUT_SCHEMA",
    "PERSONA_UPDATE_SCHEMA",
    "CONVERSATION_CREATE_SCHEMA",
    "CONVERSATION_DELETE_INPUT_SCHEMA",
    "CONVERSATION_DELETE_OUTPUT_SCHEMA",
    "CONVERSATION_GET_INPUT_SCHEMA",
    "CONVERSATION_GET_OUTPUT_SCHEMA",
    "CONVERSATION_LIST_INPUT_SCHEMA",
    "CONVERSATION_LIST_OUTPUT_SCHEMA",
    "CONVERSATION_NEW_INPUT_SCHEMA",
    "CONVERSATION_NEW_OUTPUT_SCHEMA",
    "CONVERSATION_RECORD_SCHEMA",
    "CONVERSATION_SWITCH_INPUT_SCHEMA",
    "CONVERSATION_SWITCH_OUTPUT_SCHEMA",
    "CONVERSATION_UPDATE_INPUT_SCHEMA",
    "CONVERSATION_UPDATE_OUTPUT_SCHEMA",
    "CONVERSATION_UPDATE_SCHEMA",
    "KB_CREATE_INPUT_SCHEMA",
    "KB_CREATE_OUTPUT_SCHEMA",
    "KB_DELETE_INPUT_SCHEMA",
    "KB_DELETE_OUTPUT_SCHEMA",
    "KB_GET_INPUT_SCHEMA",
    "KB_GET_OUTPUT_SCHEMA",
    "KNOWLEDGE_BASE_CREATE_SCHEMA",
    "KNOWLEDGE_BASE_RECORD_SCHEMA",
    "REGISTRY_COMMAND_REGISTER_INPUT_SCHEMA",
    "REGISTRY_COMMAND_REGISTER_OUTPUT_SCHEMA",
    "REGISTRY_GET_HANDLER_BY_FULL_NAME_INPUT_SCHEMA",
    "REGISTRY_GET_HANDLER_BY_FULL_NAME_OUTPUT_SCHEMA",
    "REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_INPUT_SCHEMA",
    "REGISTRY_GET_HANDLERS_BY_EVENT_TYPE_OUTPUT_SCHEMA",
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
    "SYSTEM_EVENT_HANDLER_WHITELIST_GET_INPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_GET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_SET_INPUT_SCHEMA",
    "SYSTEM_EVENT_HANDLER_WHITELIST_SET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_GET_STATE_INPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_GET_STATE_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_REQUEST_INPUT_SCHEMA",
    "SYSTEM_EVENT_LLM_REQUEST_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_CLEAR_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_CLEAR_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_GET_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_GET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_SET_INPUT_SCHEMA",
    "SYSTEM_EVENT_RESULT_SET_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CHUNK_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_CLOSE_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_STREAMING_OUTPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_INPUT_SCHEMA",
    "SYSTEM_EVENT_SEND_TYPING_OUTPUT_SCHEMA",
    "SYSTEM_FILE_HANDLE_INPUT_SCHEMA",
    "SYSTEM_FILE_HANDLE_OUTPUT_SCHEMA",
    "SYSTEM_FILE_REGISTER_INPUT_SCHEMA",
    "SYSTEM_FILE_REGISTER_OUTPUT_SCHEMA",
]
