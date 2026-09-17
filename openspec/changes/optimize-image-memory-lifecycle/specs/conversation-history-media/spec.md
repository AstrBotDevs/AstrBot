## Purpose

Separates durable conversation facts from large media payloads so that conversations remain restartable and image-capable without duplicating complete base64 data in every historical message.

## ADDED Requirements

### Requirement: New persisted image content SHALL use media references
The system SHALL persist a stable media reference with MIME type and image metadata for newly saved model-visible images instead of embedding the complete base64 payload in the conversation record.

#### Scenario: Model-visible image is saved
- **WHEN** a request containing a newly prepared image is saved to conversation history
- **THEN** the history stores a media reference and sufficient metadata to resolve the image later

### Requirement: Media references SHALL survive restart
The system SHALL resolve persisted media references after restart and SHALL report a readable missing-media result when the referenced media is unavailable.

#### Scenario: Referenced media file is missing
- **WHEN** a conversation contains a reference whose media object no longer exists
- **THEN** loading the conversation does not crash, the UI reports unavailable media, and the model receives an explicit bounded missing-image placeholder; this is reported as a recovery condition, not a successful memory optimization

### Requirement: Media lifetime SHALL be independent of temporary cleanup
Referenced media SHALL be durable outside the temporary-file cleanup domain. The system SHALL authorize image reads through conversation access, preserve shared media until no retained history references it, and never interpret a client-controlled media reference as an arbitrary local path.

#### Scenario: Temporary files are cleaned after restart
- **WHEN** temporary media cleanup runs while a saved conversation still references an image
- **THEN** that saved image remains readable

#### Scenario: Another conversation requests an unauthorized image
- **WHEN** a caller supplies an image identifier without access to its owning conversation
- **THEN** the request is rejected without exposing the image or its filesystem path

### Requirement: History migration SHALL be explicit and reversible
The system SHALL preserve existing inline-image histories and SHALL provide an explicit migration or repair operation before replacing inline payloads with media references.

#### Scenario: Existing history has inline base64
- **WHEN** an old conversation is opened without migration
- **THEN** it remains readable and no destructive rewrite occurs automatically
