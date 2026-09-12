# Model input images in the local ProcessStage

“Enable image compression” (`provider_settings.image_compress_enabled`) is enabled by default. The local Agent branch of ProcessStage prepares the current input before building the Agent, including ordinary attachments, quoted images and plugin `ProviderRequest` images. It checks images added or replaced by `OnLLMRequestEvent` once more before Runner reset.

## Preparation rules

- Compliant still images are sent unchanged: already JPEG or PNG, correctly oriented, and within the size limit.
- Other still images are orientation-corrected, resized and re-encoded as needed. Opaque images become JPEG, controlled by `image_compress_options.quality` (default 95), with high-bit-depth samples normalized to 8-bit. Images with transparency become PNG; a PNG larger than 1 MB is flattened onto a white background and re-encoded as JPEG to bound the payload size.
- Animations are detected from their frames, including GIF, animated WebP and APNG. Up to nine evenly sampled frames, including the first and last, become one white 3×3 grid. Unused cells stay white; an APNG independent cover is excluded.
- Stills and montages share `image_compress_options.max_size` (default 1280). Small images are not enlarged.
- Disabling compression keeps generic localization and reading, without resizing, transcoding, sampling or consulting the derived-image cache.

The Agent receives readable local paths. Original image files and event components keep their original content, and attachment text continues to reference the source image. Providers only read/encode references and assemble their protocols.

## Errors and lifetime

An unreadable, corrupt or locally undecodable image is skipped with a short warning; valid text and other images remain. If nothing usable remains, request preparation supplies a placeholder. Cancellation, resource exhaustion and programming errors are not treated as bad images.

Derived bytes are cached by source content, effective size, JPEG quality, still/montage category and algorithm version. Missing or corrupt entries are rebuilt. Each request receives independent event-owned working files, so event cleanup does not remove shared cache files. An unwritable cache can be bypassed; inability to create the working file skips that image.

Successfully localized event attachments and sources adopted during request collection remain available after event cleanup, including quoted images. Attachment text keeps these source paths; model working copies and request-only downloads are still cleaned up. Newly materialized sources stay event-owned if collection fails or is cancelled. Retained files under the temporary directory remain subject to `temp_dir_max_size` cleanup and are not permanent storage.

Existing message serialization stores the visual content the model received, including prepared images, before temporary paths expire. Replay and fallback reuse that content; old history is not rescanned or migrated.

This feature covers only current inputs through the local ProcessStage. Third-party Agent backends, direct plugin calls to Agent/Provider APIs, tool-result images, read_file and CUA retain their existing behavior. Tool-image handling is a separate follow-up and is not required for this feature.
