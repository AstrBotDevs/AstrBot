# full_api_showcase

Comprehensive `astrbot_sdk` example plugin exercising:
- Typed Pydantic configuration (`PluginConfig` + `config.schema.json` + `@lifecycle.validate_config` / `@lifecycle.config_changed`)
- Lifecycle hooks (`startup`, `health`, `shutdown`) & `TaskGroup` background tasks
- Plugin KV storage (`ctx.storage`), `data_dir`, chunked/inline asset upload & download (`ctx.assets`)
- Proactive message sending (`ctx.messages.send`) & multi-turn session waits (`ctx.sessions.wait` + `SenderSessionFilter`)
- Conversation CRUD (`ctx.conversations`)
- Cross-plugin services (`@on.service` and `@on.direct_service` via `ctx.plugins.call_service`)
- HTML/text image rendering (`ctx.render`)
- Static, runtime, and discovery tools (`@on.tool`, `ctx.tools.register`/`update_runtime_tools`, `@on.tool_discovery`)
- LLM generation, streaming, embeddings, TTS, STT, and tool-loop agents (`ctx.llm`)
- Pipeline hooks (`@hooks.*`), web routes (`@ctx.web.route`), views, and i18n
