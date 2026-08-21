# AstrBot Star

AstrBot 将插件称为 `Star`。AstrBot 是一个高度模块化的项目，通过插件可以发挥这种模块化的能力，实现各种功能。

插件管理使用原生指令组：

- `/plugin list`：列出当前已加载插件。
- `/plugin show <插件名>`：查看指定插件的版本、作者和已注册指令。
- `/plugin disable <插件名>`：停用插件，需要 `extension.manage`。
- `/plugin enable <插件名>`：启用插件，需要 `extension.manage`。
- `/plugin install <仓库 URL>`：安装插件，需要 `extension.plugin_install` 和 Dashboard step-up。

仅输入 `/plugin` 会显示可用子指令树。仓库 URL 如果包含 `&`、`#` 等特殊字符，应使用单引号，例如：

```text
/plugin install 'https://example.com/plugin.git?ref=main&source=manual#install'
```

插件加载、卸载、重载或启禁后，AstrBot 会立即重建指令 catalog，并刷新已启用的 Telegram/Discord 原生命令入口。在管理面板中也可以管理已经安装的插件。

Dashboard 插件市场的默认源是上游兼容源，不是本 fork 的官方市场。能在市场里搜到不等于能在本分支运行。安装前检查 `astrbot_version`；需要 Dashboard 页面的插件必须声明 `requires.dashboard_extension: 1` 并使用 Extension Protocol v1。不兼容时用 `/plugin install <仓库 URL>` 或 WebUI 的 URL/文件安装。

如果想自己开发插件，详见 [AstrBot 插件开发指南](/dev/star/plugin-new)。
