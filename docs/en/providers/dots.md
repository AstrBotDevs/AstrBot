# Connect Dots

AstrBot provides a dedicated **Dots** provider that reuses OpenAI Chat Completions and handles native Dots tool calls. This adapter focuses on text, tool calls, and streaming; audio and video have not been specifically verified.

## Setup

1. Create an API key on the [Dots API platform](https://dots.ai/platform/apikeys).
2. Open **Providers → Chat Completion**, click **Add** in **Provider Sources**, and select **Dots**.
3. Enter the provider name and API key. The default API Base URL is `https://note3-prev-api.askdiandian.com/v1`. The adapter sends the `api-key` header automatically; you do not need to duplicate the key in custom headers.
4. Click **Save and Fetch Models**, click `+` beside `dots3-note-prev`, and ensure the model is enabled. Alternatively, save the configuration and enter the model ID through **Custom Model**.
5. Use **Test Model** beside the model to check connectivity.
6. Open **Config**, select the relevant profile, and go to **AI → Model**. Set **Chat Model** to the newly added model, then click **Save Configuration** at the bottom right.
7. Send a message in a conversation using this profile and confirm that it replies normally.

The API key field supports AstrBot environment variable references, such as `$DOTS_API_KEY`. When multiple keys are configured, the authentication header follows the key selected for each request.

## Migrating from OpenAI Compatible

| Previous configuration | New configuration |
| --- | --- |
| Dots through OpenAI Compatible | Add a Dots provider with the same endpoint and key |
| A profile using the old provider's model | Add the new provider's model and select it as the chat model |
| An `api-key` custom header | Use the provider's API key field and let the adapter handle authentication |

Existing configurations are not migrated automatically. Dots-specific tool handling is enabled only when using the Dots provider.

## Tool calls and streaming

Ensure the model capabilities include **Tool use** before using tools. Web search requires [separate configuration](/en/use/websearch); once configured, send a search request to verify tool execution and the reply based on its results.

Streaming is off by default. Enable **Config → AI → General Settings → Streaming Output** and save the configuration.

- Standard `tool_calls` take precedence. Native `<dots_function_call>` blocks are converted and validated only with `finish_reason: tool_calls`, preventing duplicate execution of both formats in one response.
- Call examples in ordinary answers and reasoning are not executed. String arguments retain their original whitespace. Invalid or incomplete native calls raise an error when no standard calls are present.
- With streaming enabled, ordinary text appears immediately. For requests containing tools, native call markers, inline reasoning markers, and subsequent content are buffered until the response ends, then separated into text, reasoning, and tool calls.
- Tools execute after the complete response is validated; text already displayed cannot be retracted if the stream disconnects or parsing fails. The adapter does not deduplicate calls across rounds; AstrBot's tool-call round limit still applies.

For self-hosted vLLM, enable `--enable-auto-tool-choice --tool-call-parser dots` as described in the [vLLM Dots deployment guide](https://recipes.vllm.ai/dots-studio/dots3-note-prev), so the server returns standard calls.

Refer to the [official Dots API documentation](https://dots.ai/platform/docs) for current model names, capabilities, and endpoints.
