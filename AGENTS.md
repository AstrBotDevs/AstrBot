# CLAUDE Notes

- 2026-03-12: `refactor.md` on disk was empty, while the active collaboration context contained the full v4 refactor design. Treat the conversation-approved v4 design as source of truth unless a newer committed document replaces it.
- 2026-03-12: Legacy `handshake` payloads only contain `event_type` / `handler_full_name` metadata and do not preserve v4 command/message trigger details such as command names, aliases, keywords, or regex. Any legacy-to-v4 handshake translation must approximate handlers as coarse event subscriptions and keep the raw handshake payload in metadata for lossless fallback.
- 2026-03-12: `src/astrbot_sdk/tests/start_client.py` and `benchmark_8_plugins_resource_usage.py` still reference legacy `astrbot_sdk.runtime.galaxy`, but `src-new/astrbot_sdk/runtime/galaxy.py` no longer exists. Treat `tests_v4/test_script_migrations.py` as the maintained replacement instead of reviving the old Galaxy path.
