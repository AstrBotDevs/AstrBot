# Getting Help / 获取帮助

Thanks for using AstrBot! This guide points you to the right channel so your
question reaches people who can answer it quickly, and so the issue tracker
stays focused on real bugs and feature work.

> 感谢使用 AstrBot！本指南帮你把问题发到正确的渠道，让能回答的人尽快看到，同时让 Issue 列表保持聚焦于真正的 bug 与功能开发。

## Before you ask / 提问之前

1. Read the in-repo docs — [`docs/zh/`](docs/zh/) / [`docs/en/`](docs/en/).
   This fork has no published docs site. <https://docs.astrbot.app> describes
   **upstream** AstrBot, not this branch.
2. Check the FAQ — [docs/en/faq.md](docs/en/faq.md) / [docs/zh/faq.md](docs/zh/faq.md).
3. Search existing issues — <https://github.com/Xero-Team/AstrBot/issues?q=is%3Aissue>.
4. Check the latest changes — [CHANGELOG.md](CHANGELOG.md).

> 提问前请先：阅读本仓库 `docs/`（本 fork 没有独立文档站点；<https://docs.astrbot.app> 描述的是**上游** AstrBot）、查看 FAQ、搜索已有 Issue、查看最新 CHANGELOG。

## Choose the right channel / 选择正确的渠道

| You want to… / 你想……              | Go to / 去这里                                                                                           | Do NOT / 不要                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Ask a usage question / 使用问题    | [GitHub issues](https://github.com/Xero-Team/AstrBot/issues) — this fork has no first-party chat channel | Treat upstream Discord / QQ as fork support / 把上游群当作本 fork 支持 |
| Report a bug / 报 bug              | [Bug report template](https://github.com/Xero-Team/AstrBot/issues/new?template=bug-report.yml)           | —                                                                      |
| Suggest a feature / 建议新功能     | [Feature request template](https://github.com/Xero-Team/AstrBot/issues/new?template=feature-request.yml) | —                                                                      |
| Report a security issue / 安全问题 | [SECURITY.md](SECURITY.md) — private report / 私密报告                                                   | Public issues / Discord / QQ / 公开渠道                                |
| Contribute code / 贡献代码         | [CONTRIBUTING.md](CONTRIBUTING.md)                                                                       | —                                                                      |
| Report an upstream bug / 上游问题  | <https://github.com/AstrBotDevs/AstrBot>                                                                 | This fork's issues / 本 fork 的 Issue                                  |

> 把问题发到对的地方：本 fork 的协作入口是 GitHub Issue；bug 用 bug 模板；新功能用 feature 模板；安全问题按 SECURITY.md 私密报告；贡献代码看 CONTRIBUTING；在本 fork 无法复现的上游问题报上游仓库。上游 Discord / QQ 群不代表本 fork 支持。

## Community channels / 社区渠道

The collaboration entry point for this fork is GitHub:

- GitHub — <https://github.com/Xero-Team/AstrBot>

QQ groups, Discord, Astrbook, and related links on
[Community](docs/en/community.md) / [社区](docs/zh/community.md) are **upstream
AstrBot community channels**. They do not represent support or on-call
coverage for this fork. If you ask there, say that you are running the
Xero-Team fork so the discussion is not mixed with upstream behavior.

> 本 fork 的协作入口是 GitHub。社区页上的 QQ 群、Discord、Astrbook 等是**上游 AstrBot 社区渠道**，不代表本 fork 支持或值班。若在那些渠道提问，请标明你运行的是 Xero-Team fork，以免和上游行为混淆。

## Reporting a bug / 报 bug

Use the bug-report template and include:

- Reproduction steps.
- Expected vs. actual behavior.
- Debug-level logs, screenshots, and config snippets — **redact secrets and API
  keys**.
- Deployment mode: `uv`, Docker, or source.
- Version — the latest [changelog](changelogs/) entry that matches your
  checkout (this fork publishes no versioned releases).

> 使用 bug 模板并附：复现步骤；预期与实际行为；Debug 级别日志、截图与配置片段（**请脱敏密钥与 API Key**）；部署方式（`uv`/Docker/源码）；版本（与本 checkout 对应的最新 [changelog](changelogs/) 条目，本 fork 不发布版本化 Release）。

## Response expectations / 响应预期

This fork is maintained by volunteers on a best-effort basis. Issues that
lack logs or repro steps may be closed without action — see the bug-report
template. Please be patient and respectful, and follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

> 本 fork 由志愿者尽力维护。缺少日志或复现步骤的 Issue 可能被直接关闭（见 bug 模板）。请保持耐心与尊重，遵守[行为准则](CODE_OF_CONDUCT.md)。
