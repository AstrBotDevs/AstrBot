## Purpose

Provides one bounded lifecycle for images from users, tools, plugins, and external media so that model requests remain within provider limits without multiplying large image payloads in memory.

## ADDED Requirements

### Requirement: All model-bound images use one bounded preparation contract
The system SHALL apply the same preparation contract to user attachments, quoted images, plugin and MCP results, file-reading images, and computer-use screenshots before they become model image content.

#### Scenario: Source-specific image enters a model request
- **WHEN** an image is supplied by any supported source
- **THEN** the system applies the same dimension, format, encoded-byte, cleanup, and failure rules before constructing provider content

### Requirement: Image preparation SHALL enforce final encoded size
The system SHALL enforce a configurable upper bound on the final encoded image payload, in addition to pixel dimensions, and SHALL NOT silently send an image that exceeds the bound after preparation.

#### Scenario: Pixel-compliant image exceeds the byte limit
- **WHEN** an image is within the configured dimensions but its encoded payload exceeds the configured byte limit
- **THEN** the system re-encodes or resizes it until it fits, or returns a readable image-too-large failure without sending the oversized payload

### Requirement: Preparation SHALL release temporary resources
The system SHALL clean resolver-owned temporary files and release image-processing resources after request construction succeeds, fails, is cancelled, or times out.

#### Scenario: Image preparation is cancelled
- **WHEN** request processing is cancelled during download, decode, resize, or encoding
- **THEN** temporary files and owned buffers are released without affecting unrelated media
