# Codex OAuth extensions

These extensions reuse a configured ChatGPT/Codex OAuth source. Backend access to
search, transcription and GPT-Live is separate from text-model access. An enabled
adapter is not evidence that a particular account is entitled to the endpoint.

## Text and hosted search

The provider implements incremental text, reasoning and function-call streams.
Chunks have `is_chunk=True`; the final response contains complete text, tools,
raw response and usage. Consumers must not append the final full text to chunks.

`oauth_web_search` accepts `disabled` (default), `cached`, or `live`.
`oauth_web_search_domains` optionally restricts domains. Function tools and custom
tools are merged; conflicting definitions fail before sending. Request-level
`tool_choice` is honored. Citations come from actual backend URL annotations;
raw hosted-tool output is preserved in `raw_completion`.

## Ordinary voice messages

Existing AstrBot STT and TTS providers remain usable with the Codex text model.
The optional `openai_oauth_stt` adapter references an existing source using
`oauth_source_id`. It shares refresh state and follows source updates and removal.
The adapter is disabled by default because the transcription endpoint may require
separate account credits. No API-key fallback occurs.

To transcribe attachments passed directly to an OAuth chat provider, opt in using
`oauth_audio_transcription: true`, with optional
`oauth_transcription_model: gpt-4o-transcribe`. Transcription failures propagate;
audio is never silently discarded. Plugins can explicitly call
`await provider.transcribe_audio(audio_url, model="gpt-4o-transcribe")`.

This extension does not claim OAuth access to ordinary `/audio/speech` synthesis.
Use an existing AstrBot TTS provider for ordinary synthesized voice replies.

## Plugin realtime entry

The plugin owns its WebRTC peer connection, microphone input and playback. AstrBot
brokers an SDP offer and keeps a sideband control connection. Credentials remain
on the server. No Dashboard route, UI, or raw PCM transport is added.

Use an OAuth provider obtained with `context.get_provider_by_id(provider_id)`.
Create a realtime session from the plugin's SDP offer, apply the returned answer
to that peer connection, consume session events and close the session when the
plugin unloads or the peer disconnects. The implementation also bounds lifetime,
idle time, event queues and concurrent pending/active sessions. Text-model names
such as `gpt-6-astra` are not realtime model names.

The protocol uses OAuth `realtime/calls?intent=quicksilver&architecture=avas`
and a fixed GPT-Live sideband endpoint. Tool work uses client delegation events,
not an advertised native function schema. Plugins decide how to execute a
delegation and return its result. A failed creation whose response is lost cannot
prove remote cleanup; no unverified HTTP hangup endpoint is substituted.

```python
provider = context.get_provider_by_id("openai_oauth/gpt-6-astra")
session = await provider.create_realtime_session(
    offer_sdp,
    voice="cove",
    instructions="Respond briefly.",
)
async with session:
    await peer.set_remote_answer(session.answer_sdp)  # Implement in the plugin.
    async for event in session.events():
        if event.type == "delegation":
            result = await handle_plugin_delegation(event.text)
            await session.submit_delegation_result(event.delegation_id, result)
        elif event.type in {"input_transcript", "output_transcript", "turn_done"}:
            await handle_plugin_transcript(event)
```

The peer and delegation handlers above are plugin-owned examples. Never send
OAuth tokens to the peer. Close the session and peer together when either fails.
`session.send_text()` and delegation results use `speakable` or `commentary`
channels; `session.touch()` can report active media when sideband transcripts are
temporarily absent. Ping traffic does not reset the idle timer.

Protocol references:

- https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/codex-api/src/endpoint/realtime_call.rs
- https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/codex-api/src/endpoint/realtime_websocket/methods_frameless_bidi.rs
- https://github.com/openclaw/openclaw/blob/15c96969943da24fe52b92ee94c7083d534ee6df/extensions/openai/realtime-quicksilver-session.ts

End-to-end voice acceptance requires a real plugin WebRTC peer and audio input
and output. Unit tests, SDP negotiation and sideband readiness each establish
only their corresponding layer.
