# Unreleased

- QQ Official: **Use Markdown for Proactive Messages → Use Markdown by default** (主动消息使用 Markdown → 默认使用 Markdown). Regular replies and proactive messages now share the `use_markdown` default in both WebSocket and Webhook adapters; explicit message-level settings take precedence. The default remains `true`. Existing `false` configurations now also send regular replies as plain text. (#10832)

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.
