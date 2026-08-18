# AstrBot 4.27.3, Cron Delivery, and Volcengine Ark Design

## Root cause

The supplied log contains repeated `cron.manager:503` warnings: the cron job agent did not call `send_message_to_user`, so AstrBot delivered its final response as a fallback. The failure is in proactive cron delivery: the agent can finish with a normal assistant response without invoking the delivery tool.

The existing uncommitted change adds the smallest safe fallback at the shared cron boundary, preserving tool delivery when it already happened. The screenshot's visible tool-call markup is supporting evidence only; no parser rewrite is added without a reproducible provider-protocol failure.

## Scope

- Keep `opencode_go_chat_completion` and `opencode_zen_chat_completion` unchanged and present after the version update.
- Update the project version to `4.27.3` and add the release changelog entry.
- Add a named Volcengine Ark provider preset using the existing `openai_chat_completion` adapter, Beijing endpoint `https://ark.cn-beijing.volces.com/api/v3`, and the requested model IDs.
- Validate cron fallback, provider preset, version consistency, and existing OpenCode tests.

## Design

The cron runner sends final assistant text only when a delivery session exists, the agent returned an assistant response with text, and the event has not already sent a message. This prevents duplicates while covering models that ignore the delivery tool.

The Ark preset is configuration-only. Users enter an Ark API key and model ID in the existing provider UI; the OpenAI client uses the configured `/api/v3` base URL. Model guidance lists `deepseek-v4-flash-ga-260731` and `doubao-seed-2-0`; custom endpoint IDs remain valid through the existing model field.

Version metadata remains synchronized between `pyproject.toml` and `astrbot/__init__.py`. No Volcengine dependency is added.

## Error handling and compatibility

- Do not send a cron fallback when the agent already used `send_message_to_user`.
- Do not send empty final text.
- Preserve existing provider retry, timeout, proxy, and custom-header behavior.
- Preserve unrelated user changes in the dirty worktree.

## Verification

- Run focused cron and provider tests.
- Run the full Python test suite, `ruff format --check .`, and `ruff check .`.
- Run dashboard checks if provider metadata changes require them.
- Confirm the final diff contains no API keys and retains both OpenCode adapters.
