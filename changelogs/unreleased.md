# Unreleased

- WebUI: Plugin detail pages and the `pageTitle` sent to plugin view iframes now resolve the canonical `views.<view>.*` i18n namespace before falling back to the legacy `pages.<view>.*`, matching how the sidebar already resolves view titles.
- WebUI：插件详情页以及发送给插件视图 iframe 的 `pageTitle`，现在会先解析正式的 `views.<view>.*` 命名空间，再回退到旧的 `pages.<view>.*`，与侧边栏的解析方式保持一致。
- Plugins: A plugin that ships both `views/` and `pages/` is now reported in the log, because only `views/` is scanned and every view under `pages/` is silently ignored. Plugins still keeping their views in `pages/` get a migration hint instead.
- 插件：同时提供 `views/` 和 `pages/` 的插件现在会在日志中被提示 —— 因为只有 `views/` 会被扫描，`pages/` 下的视图会被静默忽略；仍把视图放在 `pages/` 的插件则会收到迁移提示。
