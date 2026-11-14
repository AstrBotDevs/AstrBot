# DeepSeek TTS Integration

AstrBot can synthesize WAV speech with the official [DeepSeek TTS API](https://api-docs.deepseek.com/zh-cn/guides/tts/).

## Get an API Key

Sign in to the [DeepSeek Platform](https://platform.deepseek.com/) and create a key on the API Keys page.

## Add the Provider

1. Open the AstrBot dashboard and go to **Providers → Text to Speech → Add**.
2. Select **DeepSeek TTS(API)**.
3. Fill in and save the following settings, then enable the provider:

| Setting | Description |
|---------|-------------|
| API Key | The key created on the DeepSeek Platform |
| API Base URL | Defaults to `https://api.deepseek.com/v1`. AstrBot appends `/tools/tts`; do not add another `/v1` suffix |
| Voice | **Stella (female, default)** maps to `stella`; **Tide (male)** maps to `tide` |
| Filter Markdown | Removes Markdown formatting before synthesis; enabled by default |
| Timeout, proxy, custom headers | Optional network settings |

The output format is fixed to WAV, and no model name is required. The API detects the language from the text and does not expose language or speaking-rate settings.

## Enable Voice Replies

1. Open **Config Files** and select the configuration to use.
2. Under **AI → Models**, enable **Voice Replies**.
3. Select the new DeepSeek TTS provider as the **Default Text-to-Speech Model** and save.

AstrBot will then use its existing voice-reply flow to synthesize and send WAV audio through DeepSeek TTS.

## Text Limits and Error Handling

- Text must not be empty and is limited to 10,000 billable characters per request. Chinese characters count as 2; other characters count as 1. AstrBot does not silently truncate oversized text.
- The complete JSON request body is limited to 64 KiB.
- Audio is returned as a binary stream. An empty response, a non-WAV response, or an interrupted transfer fails the request and removes the incomplete temporary file.
- A single request can return up to 30 minutes of audio. Refer to the [official DeepSeek documentation](https://api-docs.deepseek.com/zh-cn/guides/tts/) for current concurrency limits and API details.
