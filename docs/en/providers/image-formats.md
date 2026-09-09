# Model input images in the local ProcessStage

“Enable image compression” (`provider_settings.image_compress_enabled`) is enabled by default. The local Agent branch of ProcessStage prepares the current input before building the Agent, including ordinary attachments, quoted images and plugin `ProviderRequest` images. It checks images added or replaced by `OnLLMRequestEvent` once more before Runner reset.

## Preparation rules

- Still images become single-frame PNGs, preserving display orientation and transparency. Valid, oriented PNGs within the size limit can reuse their encoded content.
- Animations are detected from their frames, including GIF, animated WebP and APNG. Up to nine evenly sampled frames, including the first and last, become one white 3×3 PNG grid. Unused cells stay white; an APNG independent cover is excluded.
- Stills and montages share `image_compress_options.max_size` (default 1280). Small images are not enlarged. PNG does not guarantee smaller file sizes; the existing `quality` setting is not a PNG quality control.
- Disabling compression keeps generic localization and reading, without resizing, transcoding, sampling or consulting the derived-image cache.

The Agent receives readable local paths. Original image files and event components keep their original content, and attachment text continues to reference the source image. Providers only read/encode references and assemble their protocols.

## Errors and lifetime

An unreadable, corrupt or locally undecodable image is skipped with a short warning; valid text and other images remain. If nothing usable remains, request preparation supplies a placeholder. Cancellation, resource exhaustion and programming errors are not treated as bad images.

Derived bytes are cached by source content, effective size, still/montage category and algorithm version. Missing or corrupt entries are rebuilt. Each request receives independent event-owned working files, so event cleanup does not remove shared cache files. An unwritable cache can be bypassed; inability to create the working file skips that image.

Existing message serialization stores the visual content the model received, including prepared PNGs, before temporary paths expire. Replay and fallback reuse that content; old history is not rescanned or migrated.

This feature covers only current inputs through the local ProcessStage. Third-party Agent backends, direct plugin calls to Agent/Provider APIs, tool-result images, read_file and CUA retain their existing behavior. Tool-image handling is a separate follow-up and is not required for this feature.
