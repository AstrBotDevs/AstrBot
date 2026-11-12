# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.
- Plugin market: plugins can now declare a marketplace category in `metadata.yaml` (canonical identifiers served by the plugin API, unknown values log a warning and fall back to `other` without blocking installation or updates), and the WebUI category filter moved from the toolbar dropdown to a chip row above the plugin list (old entry: Extensions → Plugin Market → toolbar "Category" dropdown; new entry: Extensions → Plugin Market → category row above the list).
