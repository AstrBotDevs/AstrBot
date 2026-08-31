# AI 使用政策 / AI Policy

> 本文件为中英双语。中文版在前，英文版在后。两个版本具有同等效力；如有歧义，以中文版为准。
>
> This document is bilingual. The Chinese version comes first. Both versions
> are equally authoritative; if they disagree, the Chinese version prevails.

---

# AI 使用政策（中文）

本 fork 允许并鼓励把 AI（大语言模型、编码助手、仓库内智能体）当作维护工具。贡献者与维护者对合入 `master` 的代码负责，质量标准与来源无关。

一句话：**AI 可以自主推进工作，但合并必须有人审，且须有 AI 辅助评审。**

## 允许与禁止

AI **可以**：

- 阅读仓库、跑检查、写代码、写测试、写文档。
- 在功能分支上 commit、push。
- 开启开发用 Issue 与 Pull Request，在讨论中评论，请求评审。
- 按 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [`.agents/shared/conventional-commit/REFERENCE.md`](.agents/shared/conventional-commit/REFERENCE.md) 生成提交说明。

AI **不可以**：

- 合并 Pull Request，或把提交直接推到 `master`。
- 对受保护分支 force-push。
- 打 tag、创建 GitHub Release、发布 PyPI / 容器镜像 / 其他发行资产。
- 修改分支保护、仓库密钥、组织设置。
- 把安全漏洞写成公开 Issue 或公开 PR 描述。安全报告只走 [SECURITY.md](SECURITY.md)。
- 代维护者在 PR 上点 Approve，或伪造他人的评审。

## 合并门槛

一条 Pull Request 合入 `master` 之前必须同时满足：

1. **人类维护者**完成审查，并明确批准或给出可合入的结论。
2. **同一条 PR 上存在 AI 辅助评审**（组织评审机器人、Copilot、或维护者另行发起的智能体评审）。作者智能体自己的说明不算这条评审。

人类维护者对合并决定负责。缺一不可：没有人审不得合；没有 AI 辅助评审也不得合。作者智能体不得以「CI 已绿」为由自行合并。

## 理解，而不是照搬

无论代码是否由 AI 生成，提交者必须能说明：这段改动解决什么问题、为什么这样写、边界与取舍是什么。评审时回答不出这些问题，就不应请求合并。

把 AI 当成打字快的协作者，不要把决策外包给它。无法解释的输出：删掉重写，或先读懂再改，不要直接请求合入。

## 提交说明与 PR 正文

提交标题仍用英文 Conventional Commits。AI 定稿的 commit message 必须带 `AI-Generated: true` 与 UTC `Generated-At:`，见 conventional-commit 参考。

PR / Issue 正文末尾必须有一段**意图说明**，且必须由实际作者撰写：

- **人类**使用 AI 辅助时，写 `## Human note`，用母语，用自己的话，说明想做什么、为何这样、验证了什么。不要粘贴 AI 摘要。
- **智能体**作为作者时，写 `## Agent note`，说明目标、触及路径、跑过的检查、剩余风险、以及用了哪些 AI 工具。不要伪造 `## Human note`。

## 与维护者沟通

- 人类贡献者不要用 AI 代写 Issue / PR 里的讨论回复。需要引用模型输出时，放进引用块并标明来源，再附自己的判断。
- 智能体可以评论与请求评审，但必须基于仓库事实与已运行的检查，不得编造「已验证」或「已与维护者确认」。
- 安全敏感改动（Dashboard 认证、Agent 沙箱、MCP/工具、文件令牌、适配器解析、知识库上传、备份导入）必须在 PR 中写明如何验证边界、失败路径与资源上限。

## 敏感区额外核对

AI 生成内容常在这些地方出错，提交前核对：

- 是否复活了废弃 API、旧插件格式、旧知识库布局，或 Python 3.10–3.13 回退。
- 是否绕过证书校验、MCP 私网默认拒绝、DOMPurify、`defusedxml`、配置脱敏。
- 用户可见失败是否仍是泛化错误；日志与 API 是否泄漏密钥、URL、token。
- OpenAPI、生成客户端、`docs/public/openapi.json`、测试是否一起改。
- 中英文文档是否结构对齐。
- 是否把上游 PyPI / 镜像 / `docs.astrbot.app` 写成 fork 产物。

## 归因

在 Human note 或 Agent note 里简短披露 AI 用在了哪里。披露是为了让审查者判断掌握程度，不是把 AI 用法藏起来。

---

# English version

This fork allows and encourages AI (large language models, coding assistants,
and in-repo agents) as a maintenance tool. Contributors and maintainers remain
responsible for anything merged to `master`. The quality bar does not change
with authorship.

One line: **Agents may move work forward on their own; merging requires a
human review plus an AI-assisted review.**

## Allowed and forbidden

An agent **may**:

- Read the repository, run checks, write code, tests, and documentation.
- Commit and push on feature branches.
- Open development issues and pull requests, comment, and request review.
- Generate commit messages per [CONTRIBUTING.md](CONTRIBUTING.md) and
  [`.agents/shared/conventional-commit/REFERENCE.md`](.agents/shared/conventional-commit/REFERENCE.md).

An agent **must not**:

- Merge a pull request, or push commits directly to `master`.
- Force-push a protected branch.
- Create tags, GitHub Releases, or publish PyPI packages, container images,
  or other release assets.
- Change branch protection, repository secrets, or organization settings.
- File a public issue or public PR description for a security vulnerability.
  Use [SECURITY.md](SECURITY.md) only.
- Approve a pull request in a maintainer's name, or fabricate another person's
  review.

## Merge bar

A pull request may land on `master` only when both are true:

1. A **human maintainer** has reviewed it and explicitly approved or stated
   that it is ready to merge.
2. The **same pull request has an AI-assisted review** (the org review bot,
   Copilot, or a maintainer-invoked agent review). The authoring agent's own
   write-up does not count as that review.

The human maintainer is accountable for the merge. Neither review is optional.
The authoring agent must not merge because CI is green.

## Understand, don't relay

Whether or not AI wrote the diff, the submitter must be able to say what
problem it solves, why it is written this way, and what the edge cases are.
If those questions cannot be answered in review, do not ask to merge.

Treat AI as a fast typist, not as the decision maker. If you cannot explain a
piece of output, delete it or learn it; do not request a merge.

## Commit messages and PR bodies

Commit titles stay English Conventional Commits. AI-finalized messages must
include `AI-Generated: true` and a UTC `Generated-At:` footer.

Every PR or Issue body must end with an intent note written by the actual
author:

- A **human** using AI writes `## Human note` in their mother tongue, in their
  own words: intent, why this approach, what they verified. Do not paste an AI
  summary.
- An **agent** as author writes `## Agent note`: goal, paths touched, checks
  run, residual risk, and which AI tools were used. Do not fabricate a
  `## Human note`.

## Talking to maintainers

- Human contributors must not use AI to write discussion replies on issues or
  PRs. If a model excerpt is needed, quote it, label the source, and add your
  own judgment.
- Agents may comment and request review. They must ground claims in repository
  facts and checks they actually ran. They must not invent "verified" or
  "confirmed with maintainers".
- Changes that touch Dashboard auth, the agent sandbox, MCP/tools, file tokens,
  adapter parsing, knowledge-base uploads, or backup import must state how
  boundaries, failure paths, and resource limits were verified.

## Extra checks in sensitive areas

AI output often fails here. Check before submitting:

- Restoring deprecated APIs, old plugin formats, old knowledge-base layouts, or
  Python 3.10–3.13 fallbacks.
- Weakening certificate verification, the MCP private-network default, DOMPurify,
  `defusedxml`, or config redaction.
- Leaking secrets, URLs, or tokens in user-facing errors, logs, or API responses.
- Changing OpenAPI without the generated client, public JSON, and tests.
- Updating only one of `docs/zh/` and `docs/en/`.
- Presenting upstream PyPI, images, or `docs.astrbot.app` as fork artifacts.

## Attribution

Disclose AI use briefly in the Human note or Agent note. The point is that
reviewers can judge how well the change is understood.

---

This policy was adapted from [zpdf's AI policy](https://github.com/Xero-Team/zpdf/blob/main/AI_POLICY.md),
itself adapted from rust-analyzer and uv, then changed for this fork's
agent-maintenance model: agents may open work, humans merge.
