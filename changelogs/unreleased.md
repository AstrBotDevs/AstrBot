# Unreleased

- Local Agent input images are always prepared as JPEG/PNG files strictly below 512 KiB. Transparent previews retain PNG alpha; animations become 3×3 montages. Original attachment paths remain available to tools, and event-owned previews are deleted after use without a shared conversion cache.
- Configuration mapping: **Enable image compression** (`provider_settings.image_compress_enabled`) is replaced by always-on preparation; **JPEG quality** (`provider_settings.image_compress_options.quality`) is replaced by automatic size control; **Maximum edge length** (`provider_settings.image_compress_options.max_size`) remains available. User attachments in CUA sessions follow the same limits.
