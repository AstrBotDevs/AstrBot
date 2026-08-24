# Getting Help / 获取帮助

Thanks for using AstrBot! This guide points you to the right channel so your
question reaches people who can answer it quickly, and so the issue tracker
stays focused on real bugs and feature work.

> 感谢使用 AstrBot！本指南帮你把问题发到正确的渠道，让能回答的人尽快看到，同时让 Issue 列表保持聚焦于真正的 bug 与功能开发。

## Before you ask / 提问之前

1. Read the docs — <https://docs.astrbot.app> (English / 简体中文).
2. Check the FAQ — [docs/en/faq.md](docs/en/faq.md) / [docs/zh/faq.md](docs/zh/faq.md).
3. Search existing issues — <https://github.com/Xero-Team/AstrBot/issues?q=is%3Aissue>.
4. Check the latest changes — [CHANGELOG.md](CHANGELOG.md).

> 提问前请先：阅读文档、查看 FAQ、搜索已有 Issue、查看最新 CHANGELOG。

## Choose the right channel / 选择正确的渠道

| You want to… / 你想……              | Go to / 去这里                                                                                           | Do NOT / 不要                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Ask a usage question / 使用问题    | Discord, QQ groups — see [Community](docs/en/community.md) / [社区](docs/zh/community.md)                | GitHub issues / GitHub Issue            |
| Report a bug / 报 bug              | [Bug report template](https://github.com/Xero-Team/AstrBot/issues/new?template=bug-report.yml)           | Discord / QQ                            |
| Suggest a feature / 建议新功能     | [Feature request template](https://github.com/Xero-Team/AstrBot/issues/new?template=feature-request.yml) | —                                       |
| Report a security issue / 安全问题 | [SECURITY.md](SECURITY.md) — private report / 私密报告                                                   | Public issues / Discord / QQ / 公开渠道 |
| Contribute code / 贡献代码         | [CONTRIBUTING.md](CONTRIBUTING.md)                                                                       | —                                       |
| Report an upstream bug / 上游问题  | <https://github.com/AstrBotDevs/AstrBot>                                                                 | This fork's issues / 本 fork 的 Issue   |

> 把问题发到对的地方：使用问题走社区渠道；bug 用 bug 模板；新功能用 feature 模板；安全问题按 SECURITY.md 私密报告；贡献代码看 CONTRIBUTING；在本 fork 无法复现的上游问题报上游仓库。

## Community channels / 社区渠道

See [Community](docs/en/community.md) / [社区](docs/zh/community.md) for the
full, up-to-date list:

- Discord — <https://discord.gg/hAVk6tgV36>
- QQ groups — see the community page for current group numbers
- GitHub — <https://github.com/Xero-Team/AstrBot>

## Reporting a bug / 报 bug

Use the bug-report template and include:

- Reproduction steps.
- Expected vs. actual behavior.
- Debug-level logs, screenshots, and config snippets — **redact secrets and API
  keys**.
- Deployment mode: `uv`, Docker, Kubernetes, Launcher, or Desktop.
- Version — the latest [changelog](changelogs/) entry that matches your
  checkout (this fork publishes no versioned releases).

> 使用 bug 模板并附：复现步骤；预期与实际行为；Debug 级别日志、截图与配置片段（**请脱敏密钥与 API Key**）；部署方式（`uv`/Docker/Kubernetes/Launcher/Desktop）；版本（与本 checkout 对应的最新 [changelog](changelogs/) 条目，本 fork 不发布版本化 Release）。

## Response expectations / 响应预期

AstrBot is maintained by volunteers on a best-effort basis. Community channels
often respond faster than issues for quick questions. Issues that lack logs or
repro steps may be closed without action — see the bug-report template. Please
be patient and respectful, and follow the [Code of Conduct](CODE_OF_CONDUCT.md).

> AstrBot 由志愿者尽力维护。简单问题在社区渠道通常更快得到回复。缺少日志或复现步骤的 Issue 可能被直接关闭（见 bug 模板）。请保持耐心与尊重，遵守[行为准则](CODE_OF_CONDUCT.md)。
