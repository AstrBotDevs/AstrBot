# AstrBot Live API Protocol

This document describes the current WebSocket protocol for AstrBot Live API.

## Endpoint

- Legacy JWT endpoint: `/api/live_chat/ws`
- Legacy unified JWT endpoint: `/api/unified_chat/ws`
- Open API endpoint: `/api/v1/live/ws`

## Authentication

### Legacy dashboard endpoints

Pass a dashboard JWT in the `token` query parameter.

Example:

```text
ws://localhost:6185/api/live_chat/ws?token=<dashboard_jwt>
```

### Open API endpoint

Use an API key and provide `username` in the query string.

Examples:

```text
ws://localhost:6185/api/v1/live/ws?api_key=<api_key>&username=alice
ws://localhost:6185/api/v1/live/ws?api_key=<api_key>&username=alice&ct=chat
```

`ct` values:

- `live`: voice conversation mode
- `chat`: unified chat mode over the same WebSocket transport

The Open API endpoint reuses the `chat` API key scope.

## Transport

- Protocol: WebSocket
- Payload format: UTF-8 JSON text frames
- Audio upload format in `live` mode:
  - client sends raw PCM frames encoded as Base64
  - sample rate: `16000`
  - channels: `1`
  - sample width: `16-bit`

## Top-Level Envelope

### Client to server

```json
{
  "t": "message_type",
  "...": "message specific fields"
}
```

When using the unified socket, the client can also include:

```json
{
  "ct": "live|chat",
  "t": "message_type"
}
```

### Server to client

Legacy `live` mode uses:

```json
{
  "t": "message_type",
  "data": {}
}
```

Unified `chat` mode uses:

```json
{
  "ct": "chat",
  "type": "message_type",
  "data": {}
}
```

Some forwarded `chat` frames may also contain `t`, `streaming`, `chain_type`, `message_id`, or `session_id`.

## Live Mode

### Client messages

#### `start_speaking`

Start a voice capture segment.

```json
{
  "t": "start_speaking",
  "stamp": "seg_001"
}
```

#### `speaking_part`

Send one audio frame.

```json
{
  "t": "speaking_part",
  "data": "<base64_pcm_bytes>"
}
```

#### `end_speaking`

Finish the current voice capture segment.

```json
{
  "t": "end_speaking",
  "stamp": "seg_001"
}
```

#### `text_input`

Send a plain text input directly while using `ct=live`. The server will still route through Live mode with TTS and interrupt handling.

```json
{
  "t": "text_input",
  "text": "Hello, what is the weather today?"
}
```

You can also send message parts and use attachment IDs (same segment format as other APIs), e.g. image/file references:

```json
{
  "t": "text_input",
  "message": [
    { "type": "plain", "text": "参考这张图" },
    { "type": "image", "attachment_id": "att_1234567890" }
  ]
}
```

Attachment-based inputs are accepted only when `ct=live`; this is converted to the same internal message format as chat mode and then processed by the live pipeline.

#### `interrupt`

Interrupt the current model or TTS response.

```json
{
  "t": "interrupt"
}
```

### Server messages

#### `metrics`

Performance and provider metadata.

Example:

```json
{
  "t": "metrics",
  "data": {
    "wav_assemble_time": 0.12,
    "stt": "whisper_api",
    "llm_ttft": 0.84,
    "tts_total_time": 1.72
  }
}
```

#### `user_msg`

STT result from the uploaded audio.

```json
{
  "t": "user_msg",
  "data": {
    "text": "Hello there",
    "ts": 1710000000000
  }
}
```

#### `bot_delta_chunk`

Raw model text delta. This is the token or chunk level stream and is not sentence segmented.

```json
{
  "t": "bot_delta_chunk",
  "data": {
    "text": "Hel"
  }
}
```

Notes:

- This event is generated directly from the model streaming path.
- It is independent from TTS chunking.
- Consumers should append `data.text` to a local buffer.

#### `bot_text_chunk`

Text associated with the current TTS chunk. This is usually sentence or phrase segmented.

```json
{
  "t": "bot_text_chunk",
  "data": {
    "text": "Hello there."
  }
}
```

Notes:

- This event is aligned to TTS output, not raw token streaming.
- It may be coarser than `bot_delta_chunk`.

#### `response`

One TTS audio chunk, Base64 encoded.

```json
{
  "t": "response",
  "data": "<base64_audio_bytes>"
}
```

Attachment results can also be returned as attachment events when produced by the model:

```json
{
  "t": "image",
  "data": {
    "attachment_id": "att_1234567890",
    "filename": "abc.jpg",
    "type": "image"
  }
}
```

#### `bot_msg`

Final bot text when the response completed without audio streaming.

```json
{
  "t": "bot_msg",
  "data": {
    "text": "Final reply text",
    "ts": 1710000001234
  }
}
```

#### `stop_play`

Stop client-side audio playback because the response was interrupted.

```json
{
  "t": "stop_play"
}
```

#### `end`

Marks the end of the current response turn.

```json
{
  "t": "end"
}
```

#### `error`

Recoverable or terminal processing error.

```json
{
  "t": "error",
  "data": "error message"
}
```

## Unified Chat Mode

Set `ct=chat` on the Open API endpoint or include `"ct": "chat"` in each client frame when using `/api/unified_chat/ws`.

### Client messages

#### `bind`

Subscribe to an existing webchat session.

```json
{
  "ct": "chat",
  "t": "bind",
  "session_id": "session_001"
}
```

#### `send`

Send a chat request.

```json
{
  "ct": "chat",
  "t": "send",
  "username": "alice",
  "session_id": "session_001",
  "message_id": "msg_001",
  "message": [
    {
      "type": "plain",
      "text": "Please summarize this"
    }
  ],
  "selected_provider": "openai_chat_completion",
  "selected_model": "gpt-4.1-mini",
  "enable_streaming": true
}
```

`message` uses the same message-part schema as `POST /api/v1/chat`.

#### `interrupt`

Interrupt the current chat response.

```json
{
  "ct": "chat",
  "t": "interrupt"
}
```

### Server messages

#### `session_bound`

Acknowledges a successful `bind`.

```json
{
  "ct": "chat",
  "type": "session_bound",
  "session_id": "session_001",
  "message_id": "ws_sub_xxx"
}
```

#### Forwarded streaming events

The server forwards the normal webchat queue payloads. Common examples:

```json
{
  "ct": "chat",
  "type": "plain",
  "data": "Hello",
  "streaming": true,
  "chain_type": null,
  "message_id": "msg_001"
}
```

```json
{
  "ct": "chat",
  "type": "image",
  "data": "[IMAGE]file.jpg",
  "streaming": false,
  "message_id": "msg_001"
}
```

```json
{
  "ct": "chat",
  "type": "agent_stats",
  "data": {
    "time_to_first_token": 0.8
  }
}
```

```json
{
  "ct": "chat",
  "type": "message_saved",
  "data": {
    "id": 123,
    "created_at": "2026-03-16T10:00:00Z"
  }
}
```

```json
{
  "ct": "chat",
  "type": "end",
  "data": "",
  "streaming": false,
  "message_id": "msg_001"
}
```

#### Chat errors

```json
{
  "ct": "chat",
  "t": "error",
  "code": "INVALID_MESSAGE_FORMAT",
  "data": "message must be list"
}
```

## Recommended Client Strategy

For `live` mode:

1. Append every `bot_delta_chunk.data.text` into a raw transcript buffer.
2. Use `bot_text_chunk` only when you need text aligned with audio playback.
3. Decode and play each `response` audio chunk in arrival order.
4. Reset per-turn buffers after `end`.

For `chat` mode:

1. Treat `plain + streaming=true` as incremental text.
2. Treat `complete` or `end` as the end of a response turn.
3. Persist `message_saved` metadata if you need server-side history IDs.

## Compatibility Notes

- `bot_text_chunk` remains sentence or phrase segmented for TTS compatibility.
- `bot_delta_chunk` is the new delta-level text event for real-time rendering.
- The legacy JWT endpoints and the new Open API endpoint share the same runtime behavior after authentication.
