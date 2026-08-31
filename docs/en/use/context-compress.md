# Context Compression

When the local Agent Runner approaches a model's context-window limit, AstrBot automatically compacts older messages so the request does not fail because of an oversized context. The default strategy summarizes older history with an LLM while preserving recent conversation turns exactly.

![Context compression settings](https://files.astrbot.app/docs/source/images/context-compress/image.png)

## When compression runs

AstrBot checks the context before every Agent step. This includes the next model call after a tool finishes. Compression is triggered when the estimated context usage exceeds **82%** of the model's context window.

The window size is resolved in this order:

1. Use `max_context_tokens` from the model configuration.
2. If it is unset or not positive, look up the model in AstrBot's built-in model metadata.
3. If the model is still unknown, use `agent_runner.config.compression.fallback_max_tokens`, which defaults to `128000`.

For custom model IDs or model names rewritten by a proxy, set an accurate `max_context_tokens` value on the model. A value that is too large can let the provider reject the request first; a value that is too small causes premature compression.

![Model context-window setting](https://files.astrbot.app/docs/source/images/context-compress/image1.png)

## Compression strategies

Choose a strategy with `agent_runner.config.compression.overflow_strategy` in the profile's Agent Runner settings.

### `llm_compress`: LLM summary (default)

AstrBot asks a compression model to summarize complete older turns, then combines that summary with the most recent original turns.

- `agent_runner.config.compression.provider_id` selects the chat model used for summarization. When left empty, AstrBot uses the model active for the current session.
- `agent_runner.config.compression.keep_recent_ratio` is the share of the pre-compression token count preserved as exact recent context. It defaults to `0.15`, is clamped to the range `0`–`0.3`, and is mapped to whole conversation turns rather than splitting a turn. AstrBot also tries to preserve the active, latest user request exactly.
- `agent_runner.config.compression.instruction` overrides the summary instruction.

The default instruction asks the summary to preserve:

1. every core topic, its outcome, and the latest primary focus;
2. tool-call counts and the most valuable tool results;
3. files, documents, code, references, and paths that may be needed later;
4. the user's original goal and current progress;
5. the user's language, plus the latest result and concrete next step for work in progress.

If the configured compression model is unavailable, AstrBot tries the model active for the current session. If no usable model is available, it uses turn-based truncation. The runtime also applies a truncation safeguard when summarization fails or the summarized context is still over the threshold.

### `truncate_by_turns`: turn-based truncation

This strategy makes no extra LLM call. It removes the oldest complete conversation turns, with `agent_runner.config.compression.trim_turns` controlling how many turns are dropped at a time. The default is `1`. It is fast and has no summary-model cost, but old details are discarded instead of condensed.

## Maximum conversation turns

`agent_runner.config.compression.max_turns` is a turn limit independent of the token threshold:

- `-1` disables the turn limit, which is the default;
- a positive integer keeps only that many recent turns before token-based compression runs.

When both limits are configured, the turn limit is enforced first. For long-running tasks with substantial tool output, keep `llm_compress` enabled and configure an accurate context-window size. Use turn-based truncation when avoiding an additional summarization call matters more than retaining older details.
