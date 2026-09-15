## Why

AstrBot currently prepares images through several partially independent paths. Some inputs are resized only by pixel dimensions, while the final base64 payload can still exceed provider limits and consume several copies of the image in memory. Conversation history can also retain complete inline image data, so every later request pays the deserialization and request-construction cost again. Issue #10089 demonstrates request-size failures, while #10092 demonstrates process-level memory exhaustion.

## What Changes

- Add one image preparation contract for user attachments, quoted images, plugins, MCP/tool results, file reading, and screenshots.
- Enforce both dimension limits and a configurable final encoded-payload byte limit; reject or degrade images that cannot satisfy the limit instead of silently sending oversized data.
- Store historical images as durable media references and metadata rather than embedding complete base64 data in every conversation message.
- Resolve historical image references only when the active provider request needs them, with bounded loading and cleanup.
- Keep the current conversation semantics: images in the active context remain available to the model; this change does not silently remove images merely to improve memory numbers.
- Add memory-ablation tests covering preparation, history loading, request assembly, persistence, and repeated conversations.
- Preserve backward compatibility by reading existing inline data URIs and provide an explicit migration/repair path instead of rewriting them implicitly.

## Capabilities

### New Capabilities

- `image-memory-lifecycle`: bounded image preparation, durable media references, lazy resolution, and memory-safe request assembly.
- `agent-context-image-budget`: active requests validate image byte size independently from token accounting and resolve references without changing image visibility.
- `conversation-history-media`: persisted messages may use media references and must remain readable across restart while preserving existing inline-image histories.

## Impact

- Affects media resolution and compression, provider request assembly, agent context processing, conversation persistence, tool/plugin image paths, and related tests.
- Adds a local media storage/index lifecycle with cleanup and missing-media handling.
- Adds configuration for final encoded image size and bounded media storage behavior; existing pixel/quality settings remain compatible.
- Provider payloads remain provider-specific; only the internal history representation and preparation boundary change.
