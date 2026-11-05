# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.

- Audio: Outbound voice messages no longer transcode MP3 payloads to WAV, which inflated base64 bodies by roughly 4.4x for long audio and could exceed platform frame limits; Satori and WebChat now derive the MIME type and file extension from the actual payload.
