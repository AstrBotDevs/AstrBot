# Unreleased

- WebUI：新增“系统设置 → 外观 → 在侧边栏显示 Chat 入口”，默认关闭并保存在当前浏览器。启用后入口从“顶部聊天 / Bot 切换”移至“侧边栏系统上方聊天 → 聊天会话”；“返回导航”回到原管理页面。复用现有会话操作，支持折叠侧栏、手机抽屉和减少动态效果设置。
- WebUI: Added System Settings → Appearance → Show Chat in the sidebar, off by default and saved in the current browser. When enabled, the top Chat / Bot switch moves to Chat above System → chat sessions; Back to navigation returns to the previous admin page. Existing session actions, collapsed sidebars, mobile drawers, and reduced motion remain supported.

- QQ Official: a failed image upload no longer dumps the base64 payload into the log (a single multi-MB line could freeze log writing and the web dashboard), and image upload retries drop from 5 to 3 with a single summary warning instead of one per attempt.
