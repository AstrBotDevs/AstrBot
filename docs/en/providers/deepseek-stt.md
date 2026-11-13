# DeepSeek STT Integration

AstrBot can use the official [DeepSeek ASR API](https://api-docs.deepseek.com/zh-cn/guides/asr/) to transcribe user audio before passing the text to the configured chat model. Speech recognition is independent of the chat model, so you can use a chat model from another provider.

## Get an API Key

Sign in to the [DeepSeek Platform](https://platform.deepseek.com/) and create a key on the API Keys page.

## Add the Provider

1. Open the AstrBot dashboard and go to **Providers → Speech to Text → Add**.
2. Select **DeepSeek STT(API)**.
3. Fill in and save the following settings, then enable the provider:

| Setting | Description |
|---------|-------------|
| API Key | The key created on the DeepSeek Platform |
| API Base URL | Defaults to `https://api.deepseek.com/v1`. AstrBot appends `/tools/asr`; do not add another `/v1` suffix |
| Timeout, proxy, custom headers | Optional network settings |

No model name or language parameter is required. The API detects the spoken language automatically.

## Enable Speech Recognition

1. Open **Config Files** and select the configuration to use.
2. Under **AI → Models**, enable **Speech Recognition**.
3. Select the new DeepSeek STT provider as the **Default Speech-to-Text Model** and save.

When a voice message arrives, AstrBot transcribes it and sends the resulting text to the current chat model as the user's message.

## Audio Requirements and Limits

- The DeepSeek API accepts 16-bit PCM WAV and Ogg Opus, detecting the format from the file contents.
- WAV audio may use 8000, 16000, 22050, 24000, 32000, 44100, or 48000 Hz and one or two channels. For stereo audio, only the left channel is recognized.
- AstrBot reuses compatible WAV files and converts other inputs, including SILK and AMR, to mono 16 kHz, 16-bit PCM WAV. SILK conversion uses the existing `silk-python` dependency; other conversions require ffmpeg.
- Each uploaded file can be at most 8 MiB and 120 seconds long. AstrBot checks the actual upload before sending it and reports an error instead of silently truncating oversized audio.
- The API does not support streaming recognition. If no speech is recognized, AstrBot does not invent replacement transcription text.

Refer to the [official DeepSeek documentation](https://api-docs.deepseek.com/zh-cn/guides/asr/) for current API details and account concurrency limits.
