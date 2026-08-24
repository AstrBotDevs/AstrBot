# Security Policy / 安全策略

## Supported Versions / 支持的版本

This repository is a modernized fork that publishes **no PyPI package and no
prebuilt release assets**. There is no versioned support matrix — only the
current `master` branch is supported. The package named `astrbot` on PyPI, AUR
packages, and upstream container images are **not** builds of this branch and
their security issues are out of scope here.

| Version / 版本                           | Supported / 是否支持          |
| ---------------------------------------- | ----------------------------- |
| `master` (this fork)                     | ✅ Supported / 支持           |
| Tagged past commits                      | ⚠️ Best-effort / 尽力而为     |
| Upstream `AstrBot` releases              | ❌ Report upstream / 报上游   |
| PyPI `astrbot` / AUR / `soulter/astrbot` | ❌ Not this branch / 非本分支 |

> 本仓库是不发布 PyPI 包与预构建资产的现代化 fork，不存在版本支持矩阵，仅当前 `master` 分支受支持。PyPI 上的 `astrbot`、AUR 包与上游容器镜像均非本分支构建，其安全问题不在本仓库范围内。

## Reporting a Vulnerability / 报告漏洞

**Do NOT open a public GitHub issue for security vulnerabilities.** Public
issues disclose the problem before a fix exists.

> **切勿为安全漏洞开启公开 Issue。** 公开 Issue 会在修复前暴露问题。

**Preferred channel / 推荐渠道 — GitHub Private Security Advisory:**

1. Go to <https://github.com/Xero-Team/AstrBot/security/advisories/new>.
2. Fill in a description, affected versions/components, and a reproducer if
   you have one.
3. Submit. Only repository maintainers see the report.

> 进入 <https://github.com/Xero-Team/AstrBot/security/advisories/new>，填写描述、受影响版本/组件以及可复现步骤（如有），仅仓库维护者可见。

If GitHub private reporting is unavailable, contact the maintainers directly
(@BegoniaHe, @YUZHEthefool) and request a private channel. Do not post
vulnerability details in any public space, including Discord, QQ groups,
issues, or pull requests.

> 若 GitHub 私密报告不可用，请直接联系维护者（@BegoniaHe、@YUZHEthefool）并索要私密渠道。请勿在 Discord、QQ 群、Issue 或 PR 等任何公开场合发布漏洞细节。

Please include / 请提供：

- A clear description of the vulnerability and its impact.
- Affected component or path (e.g., Dashboard auth, Agent sandbox, a platform
  adapter, an MCP/tool path).
- Steps to reproduce, with minimal config. Redact secrets and API keys.
- Your assessment of severity and any suggested fix.
- How you would like to be credited (optional).

> 包含：漏洞与影响的清晰描述；受影响组件或路径（如 Dashboard 认证、Agent 沙箱、某平台适配器、MCP/工具路径）；最小复现步骤（请脱敏密钥与 API Key）；严重程度评估与修复建议（可选）；是否希望被致谢（可选）。

## Response Timeline / 响应时间

| Step / 步骤                   | Target / 目标                                                                        |
| ----------------------------- | ------------------------------------------------------------------------------------ |
| Acknowledge receipt           | Within 2 business days / 2 个工作日内                                                |
| Initial assessment & severity | Within 5 business days / 5 个工作日内                                                |
| Fix or mitigation plan        | Communicated after assessment / 评估后告知                                           |
| Coordinated disclosure        | After a fix lands, or 90 days, whichever is first / 修复落地后或 90 天，以先到者为准 |

These are targets, not guarantees. We will keep reporters informed at each
step. If you do not receive an acknowledgment within the target window, follow
up through the same private channel.

> 以上为目标而非承诺。我们会在每一步同步进展。若在目标时间内未收到确认，请通过同一私密渠道跟进。

## Coordinated Disclosure / 协调披露

- Reports stay private until a fix is available or the 90-day window elapses.
- We publish a [GitHub Security Advisory](https://github.com/Xero-Team/AstrBot/security/advisories)
  (and request a CVE where applicable) when the fix is released.
- Reporters who report in good faith and follow coordinated disclosure will be
  credited unless they ask otherwise.
- We will not take legal action against good-faith security research that
  respects this policy (safe harbor).

> 报告在修复可用或 90 天窗口期满前保持私密。修复发布时我们会发布 GitHub 安全公告（如适用则申请 CVE）。善意且遵守协调披露的报告者将被致谢（除非另有要求）。对遵守本策略的善意安全研究，我们不会采取法律行动（安全港原则）。

## Scope / 范围

**In scope / 在范围内:**

- Code in this repository: the AstrBot backend (`/astrbot`), the Dashboard
  frontend (`/dashboard`), deployment manifests, and bundled scripts.
- Authentication, authorization, the Dashboard step-up / reauthentication
  flow, the Agent sandbox, MCP/tool execution, and the platform adapters
  shipped in this branch.

**Out of scope / 不在范围内:**

- **Upstream AstrBot** issues that do not reproduce on this fork — report them
  to <https://github.com/AstrBotDevs/AstrBot>.
- **Third-party plugins** — report to the plugin author. A malicious or
  vulnerable plugin is the plugin's responsibility, not the platform's, unless
  the sandbox boundary itself is broken.
- **Self-inflicted exposure** — binding the WebUI to `0.0.0.0` without a
  firewall or reverse proxy, leaking `ASTRBOT_BIND_ADDRESS`, or committing
  secrets/API keys. The default binds to `127.0.0.1`.
- **Vulnerabilities in dependencies** — report to the upstream dependency
  maintainer; we track and patch via Dependabot (see `.github/dependabot.yml`).
- **DoS / resource exhaustion** of self-hosted instances, or spam/social
  engineering.

> 在范围内：本仓库代码（`/astrbot` 后端、`/dashboard` 前端、部署清单与内置脚本）；认证授权、Dashboard 二次验证流程、Agent 沙箱、MCP/工具执行及本分支自带平台适配器。
> 不在范围内：在本 fork 上无法复现的上游 AstrBot 问题（报 <https://github.com/AstrBotDevs/AstrBot>）；第三方插件（报插件作者，除非沙箱边界本身被突破）；自致暴露（无防火墙绑定 `0.0.0.0`、泄露 `ASTRBOT_BIND_ADDRESS`、提交密钥——默认绑定 `127.0.0.1`）；依赖库漏洞（报上游依赖，本仓库通过 Dependabot 跟踪修复）；自托管实例的 DoS/资源耗尽或社工攻击。

## Security Tooling Already in Place / 已有的安全工具

This fork runs continuous security checks that contributors inherit:

- [CodeQL](.github/workflows/codeql.yml) — semantic code analysis on pushes and PRs.
- [Secret scanning](.github/workflows/secret-scan.yml) — detects committed secrets.
- [Dependency review](.github/workflows/dependency-review.yml) — blocks PRs that introduce known-vulnerable dependencies.
- [Dependabot](.github/dependabot.yml) — daily updates for `uv`, npm, and GitHub Actions.

> 本 fork 已内置持续安全检查：CodeQL 语义分析、密钥扫描、依赖审查（阻止引入已知漏洞依赖）、Dependabot 每日更新。

## Hardening Notes for Operators / 运维加固提示

- Keep the WebUI on `127.0.0.1` unless you publish it; if you must expose it,
  put it behind a firewall and an HTTPS reverse proxy.
- Change the initial random password immediately; never share startup logs
  that contain it.
- Run plugins through the Agent sandbox; review plugin permissions before
  enabling.
- Keep API keys and provider tokens out of version control and out of logs.

> 保持 WebUI 在 `127.0.0.1`；如需暴露，请加防火墙与 HTTPS 反向代理；立即修改初始随机密码且勿分享含密码的启动日志；插件经 Agent 沙箱运行并先审查权限；勿将 API Key 与 token 纳入版本控制或日志。
