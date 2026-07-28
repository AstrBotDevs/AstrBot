# 发布插件到插件市场

在编写完插件后，你可以选择将插件发布到 AstrBot 的插件市场，让更多用户使用你的插件。

AstrBot 使用 GitHub 托管插件，因此你需要先将插件代码推送到之前创建的 GitHub 插件仓库中。

你可以前往 [AstrBot 插件发布页面](https://cloud.astrbot.app/publish) 发布你的插件，发布插件需要注册 AstrBot Cloud 账号。

<!-- ![fill out the form](https://files.astrbot.app/docs/source/images/plugin-publish/image.png) -->

以下是一个完整的插件元数据示例（`metadata.yaml`），系统会自动解析这些信息：

```yaml
name: astrbot_plugin_example                 # 插件标识符，英文，唯一
display_name: 示例插件名称                    # 插件展示名称
# short_desc: 一句话介绍你的插件功能           # （可选）紧凑 UI 使用的短描述
desc: 详细描述插件的功能、特性、使用方法等信息。 # 详细描述插件的信息
  可以写多行文本，支持 Markdown 格式。
version: 1.0.0                               # 插件版本号（遵循语义化版本规范）
author: 作者名称                              # 作者名称
repo: https://github.com/your-name/repo      # 插件仓库地址
# astrbot_version: ">=4.17.0"                # （可选）支持的 AstrBot 版本范围
# support_platforms:                         # （可选）支持的平台适配器列表
#   - aiocqhttp
#   - qq_official
# social_link: https://github.com/your-web   # （可选）你的个人网站、GitHub 主页等
# tags:                                      # （可选）标签列表，用于插件市场分类和搜索
  # - example
```

[目前支持的平台适配器](plugin-new.md#声明支持平台-optional)

::: warning 大小限制
发布到插件市场的插件压缩包（zip）大小**不得超过 16MB**。

如果超过此限制，CI/CD 流水线将自动拒绝该发布请求。
::: details 为确保你的插件能顺利通过审核和发布，建议采取以下措施：

- **压缩图片等静态资源**：对插件中的图片、音频等资源文件进行压缩，减小体积。
- **清理不必要的文件**：避免将 `.git` 目录、`__pycache__`、`node_modules`、开发用配置文件等非必需文件提交到插件仓库中。建议在仓库根目录添加 `.gitignore` 来排除它们。
- **优化依赖体积**：如果插件包含体积较大的依赖库，可考虑精简或按需引入。
- **使用 `.gitattributes` 或发布分支**：通过只包含发布所需文件的策略来减小 zip 包体积。

如果插件确实因业务需要无法压缩到 16MB 以内，可以联系维护者手动 bypass 此限制。
:::
