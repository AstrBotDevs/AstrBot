# Unreleased

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.
- Restore the previous certifi and pip minimum versions so existing updaters can install dependencies with their current core version locks. Core updates now bypass those locks; plugin and manual package installs retain dependency protection.
