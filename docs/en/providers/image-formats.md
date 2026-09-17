# Model input images

The local Agent always prepares current input images before sending them to the model. This covers ordinary attachments, quoted images, and plugin `ProviderRequest` images, including images added or replaced by `OnLLMRequestEvent`.

## Limits and formats

- Original image files larger than **64 MiB** are skipped before reading their contents or decoding pixels. Files up to and including 64 MiB are processed normally.
- Each prepared image file is **strictly smaller than 512 KiB** (524,288 bytes). This limit applies to image bytes before Base64 encoding, not the entire request.
- **Maximum edge length**, under **Configuration**, remains configurable through `provider_settings.image_compress_options.max_size` (default 1280 pixels). Images keep their aspect ratio and are never enlarged. They may be reduced further to meet the byte limit.
- Correctly oriented JPEG/PNG images already within both limits retain their original bytes. Other still images are orientation-corrected and encoded as JPEG, or PNG when they have transparency. Transparent images retain their alpha channel even when further reduction is necessary.
- GIF, animated WebP, and APNG inputs become a white 3×3 frame montage. Up to nine evenly spaced frames include the first and last animation frames; unused cells stay blank. An independent APNG cover is excluded.
- Unneeded metadata is removed when re-encoding. A color profile is retained when compatible with the output and the byte limit.

These limits also apply to user attachments in CUA sessions. Screenshot and other tool-result images keep their own handling.

## Configuration changes

| Previous setting | Current behavior |
| --- | --- |
| Enable image compression (`image_compress_enabled`) | Removed; current input images are always prepared. |
| JPEG quality (`image_compress_options.quality`) | Removed; output size is controlled automatically. |
| Maximum edge length (`image_compress_options.max_size`) | Retained; applies together with the strict 512 KiB limit. |

Values of the removed settings in existing configuration files no longer affect image preparation.

## Original files and preview lifetime

`image_urls` and image content parts reuse compliant local JPEG/PNG files directly; no working copy is created. Images requiring conversion use prepared preview files. The attachment paths shown to the model for file access continue to point to the **original images**, so tools can read the originals. Original files and event image components are not overwritten.

Preview files are owned by the current event and deleted when the event finishes, including failure or cancellation. There is no shared image-conversion cache. Repeated references within one request reuse the same preview, including the preparation pass after the request hook.

Successfully localized original attachments, including quoted images, survive event cleanup. Retained originals under the temporary directory remain subject to `temp_dir_max_size` cleanup and are not permanent storage. Sources that have not yet been successfully adopted when request collection fails remain event-owned.

Conversation history captures the prepared image content as Base64 data URIs before preview files expire. Old history is not reprocessed. An unreadable image is skipped; valid text and other images remain. Cancellation, resource exhaustion, and programming errors are not treated as bad images.

Third-party Agent backends, direct calls that bypass the local pipeline, and tool-result images are outside this input preparation flow.
