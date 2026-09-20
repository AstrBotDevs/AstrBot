# Connect Dots

AstrBot provides a dedicated **Dots** provider that reuses OpenAI Chat Completions and handles native Dots tool calls.

## Setup

1. Create an API key on the [Dots API platform](https://dots.ai/platform/apikeys).
2. Open **Providers → Chat Completion**, click **Add Provider**, and select **Dots**.
3. Enter the provider name and API key. The default API Base URL is `https://note3-prev-api.askdiandian.com/v1`. The adapter sends the `api-key` header automatically; you do not need to duplicate the key in custom headers.
4. Click **Save and Fetch Models**, click `+` beside `dots3-note-prev`, and ensure the model is enabled. Alternatively, save the configuration and enter the model ID through **Custom Model**.
5. Use **Test Model** beside the model to check connectivity.
6. Open **Config**, select the relevant profile, and go to **AI → Model**. Set **Chat Model** to the newly added model, then click **Save Configuration** at the bottom right.

The API key field supports AstrBot environment variable references, such as `$DOTS_API_KEY`. When multiple keys are configured, the authentication header follows the key selected for each request.

## Migrating from OpenAI Compatible

| Previous configuration | New configuration |
| --- | --- |
| Dots through OpenAI Compatible | Add a Dots provider with the same endpoint and key |
| A profile using the old provider's model | Add the new provider's model and select it as the chat model |
| An `api-key` custom header | Use the provider's API key field and let the adapter handle authentication |

Existing configurations are not migrated automatically. Dots-specific tool handling is enabled only when using the Dots provider.

## Tool calls and streaming

- Standard `tool_calls` responses use the existing tool execution flow.
- When a response explicitly requests tools with `finish_reason: tool_calls`, but puts the calls inside `<dots_function_call>`, the adapter converts them to standard calls, validates tool names and arguments, and removes the call blocks from assistant text.
- If both representations are present, standard calls take precedence to prevent duplicate execution. XML examples in ordinary answers are not interpreted as calls.
- Inline `<think>` and `<thinking>` sections are buffered and kept as reasoning; call examples inside them are not executed. String arguments retain their original whitespace.
- Requests containing tools stream ordinary text immediately, retaining only suffixes that could be split call markers. Once a native call marker is detected, the marker and subsequent text are buffered until the complete response distinguishes a tool call from an XML example. Call blocks are removed; examples are released in their original order. Requests without tools retain their existing streaming behavior.
- Tools execute only after the complete response has been parsed and validated. If the stream disconnects or call parsing fails, ordinary text already displayed cannot be retracted, but buffered call content is not exposed as assistant text.
- Incomplete or invalid native calls raise an error instead of being sent as normal replies. This compatibility layer does not guarantee that the model will avoid repeated tool calls; AstrBot's existing tool-call round limit still applies.

For self-hosted vLLM, enable `--enable-auto-tool-choice --tool-call-parser dots` as described in the [vLLM Dots deployment guide](https://recipes.vllm.ai/dots-studio/dots3-note-prev), so the server returns standard calls.

Refer to the [official Dots API documentation](https://dots.ai/platform/docs) for current model names, capabilities, and endpoints.
