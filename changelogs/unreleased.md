# Unreleased

- WebUI: Plugin detail pages and the `pageTitle` sent to plugin view iframes now resolve the canonical `views.<view>.*` i18n namespace before falling back to the legacy `pages.<view>.*`, matching how the sidebar already resolves view titles.
- WebUI：插件详情页以及发送给插件视图 iframe 的 `pageTitle`，现在会先解析正式的 `views.<view>.*` 命名空间，再回退到旧的 `pages.<view>.*`，与侧边栏的解析方式保持一致。
