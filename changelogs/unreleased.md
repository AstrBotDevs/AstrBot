# Unreleased

- Generate numbered original-path notices in the image preparation stage during main-agent construction, including quoted images. After request hooks, apply the same size and format policy only to newly introduced image references and refresh their notices. Skipped and captioned attachments retain explicit status without taking a visual index; animation labels identify frame montages.
- Raise the model image input cap from 32 MiB to 64 MiB. Larger originals are skipped before reading image bytes, with a model notice retaining their paths and suggesting the file-reading tool or a smaller upload; accepted inputs still produce images strictly below 512 KiB.
- Local Agent input images are always prepared as JPEG/PNG files strictly below 512 KiB. Compliant local images are reused without copying. Transparent previews retain PNG alpha; animations become 3×3 montages. Original attachment paths remain available to tools, and event-owned previews are deleted after use without a shared conversion cache.
- Configuration mapping: **Enable image compression** (`provider_settings.image_compress_enabled`) is replaced by always-on preparation; **JPEG quality** (`provider_settings.image_compress_options.quality`) is replaced by automatic size control; **Maximum edge length** is renamed to **Input image maximum edge length** (`provider_settings.image_compress_options.max_size`). User attachments in CUA sessions follow the same limits.

- WebUI: Keep content corners and borders fixed while pages scroll inside the card. Add 6px right and bottom gaps on desktop; mobile keeps a full-width, flat layout. (#10479)
- WebUI: Restore the content card's right and bottom borders and use the primary theme color for the active sidebar Settings button.
- WebUI: Pin configuration and settings headers and section navigation while only the right content pane scrolls, including embedded configuration drawers.
- WebUI: **System Settings → Appearance → Customize Sidebar → removed**; the sidebar uses the default menu layout. Theme colors and extension collapsing, pinning, and grouping remain available.
- WebUI：页面在内容卡片内部滚动，圆角和边线保持固定。桌面端右侧和底部各保留 6px 间隔，移动端保持全宽平面布局。 (#10479)
- WebUI：补齐内容卡片右侧和底部边框，侧边栏设置按钮选中时使用主题主色背景及文字。
- WebUI：配置页和设置页固定顶部及分区导航，仅滚动右侧内容；嵌入式配置抽屉也采用相同行为。
- WebUI：**系统设置 → 外观 → 自定义侧边栏 → 已移除**；侧边栏使用默认菜单布局。仍可调整主题颜色，以及折叠、置顶和按插件分组扩展功能。
