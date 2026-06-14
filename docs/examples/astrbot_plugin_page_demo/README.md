# AstrBot Plugin Page Demo

This demo plugin reproduces the Plugin Page bridge APIs and the recommended `astrbot.api.web` backend helpers.

Covered bridge APIs:

- `ready()`
- `getContext()`
- `getLocale()`
- `getI18n()`
- `t(key, fallback)`
- `onContext(handler)`
- `apiGet(endpoint, params)`
- `apiPost(endpoint, body)`
- `upload(endpoint, file)`
- `download(endpoint, params, filename)`
- `subscribeSSE(endpoint, handlers, params)`
- `unsubscribeSSE(subscriptionId)`

Covered backend helpers:

- `request.query`
- `await request.json(default={})`
- `await request.form()`
- `await request.files()`
- `json_response()`
- `error_response()`
- `file_response()`
- `stream_response()`

For local manual testing, place this directory under `data/plugins/astrbot_plugin_page_demo`, restart or reload plugins, then open the `Bridge Lab` Page from the plugin detail page.
