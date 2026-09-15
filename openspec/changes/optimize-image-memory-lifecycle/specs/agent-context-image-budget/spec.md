## Purpose

Keeps the active model context bounded by treating image payload bytes as a real request cost and by resolving only image data required by the active provider request.

## ADDED Requirements

### Requirement: Active context SHALL use a bounded image budget
The system SHALL validate encoded image bytes and known provider request-size limits independently from text token estimates. It MUST NOT introduce additional image eviction, replace available images with summaries, or re-encode historical images on every turn to fit a changing budget.

#### Scenario: Context contains many images
- **WHEN** the active context contains images whose encoded payloads exceed the image budget
- **THEN** the system reports a readable size-limit error before sending a known-oversized request, without silently dropping images or changing historical image bytes

### Requirement: Historical media SHALL be resolved on demand
The system SHALL keep historical image content as a resolvable media reference and SHALL materialize its bytes only when the image is selected for the active provider request.

#### Scenario: Old image is outside the active context
- **WHEN** a historical image is outside the selected context window and is not input to the summarization request
- **THEN** the system does not read, decode, or base64-encode that image for the request

### Requirement: Summarization SHALL retain its existing image input semantics
The system SHALL resolve selected image references for an image-capable summarization provider just as it does for the main provider. Images summarized out of the main window may still need loading for that separate summary request; this cost SHALL be measured separately.

#### Scenario: Old image participates in a summary
- **WHEN** the existing context compression policy passes an old image to an image-capable summary provider
- **THEN** that provider receives the image rather than an unresolved reference, while the subsequent main request contains only its selected context

### Requirement: Lazy loading SHALL preserve provider-visible image bytes
The system SHALL preserve image bytes, MIME type, detail, order, and message placement for a fixed prepared image across persistence, restart, and subsequent requests to the same provider configuration.

#### Scenario: A later turn loads a persisted image
- **WHEN** a later text message causes an existing image reference to be materialized
- **THEN** the image content is byte-identical to its earlier prepared representation and the stable historical request prefix remains unchanged

### Requirement: Existing inline images SHALL remain readable
The system SHALL continue to read existing persisted inline image data and SHALL apply the active image budget when such data is included in a request.

#### Scenario: Existing conversation contains a data URI
- **WHEN** a conversation created before media references is loaded
- **THEN** the conversation remains readable and its inline image is handled by the same bounded request policy
