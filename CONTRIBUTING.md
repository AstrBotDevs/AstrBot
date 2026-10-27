# CONTRIBUTING

## 贡献指南

首先，感谢您花时间做出贡献！❤️

所有类型的贡献都受到鼓励和重视。有关不同的帮助方式和处理方式的详细信息，请参阅[目录](#目录)。在做出贡献之前，请确保阅读相关部分。这将使我们维护人员的工作变得更加容易，并为所有参与者带来顺畅的体验。社区期待您的贡献。🎉

### 目录

- [报告问题](#报告问题)
- [提交代码更改](#提交代码更改)

### 报告问题

如果您在使用 AstrBot 时遇到任何问题，请按照以下步骤报告：

1. **检查现有问题**：在提交新问题之前，请先检查 [Issues](https://github.com/AstrBotDevs/AstrBot/issues) 中是否已经存在类似的问题。
2. **创建新问题**：如果没有类似的问题，请创建一个新问题。请确保提供以下信息：
   - 问题的简要描述
   - 重现问题的步骤
   - 预期结果和实际结果
   - 相关日志或错误消息

### 提交代码更改

#### 分支命名

我们使用 `fix/` 前缀来修复错误，使用 `feat/` 前缀来添加新功能。对于 `fix/` 分支，请使用简短的描述，或者直接使用 Issue 编号。例如：`fix/1234` 或者 `fix/1234-login-typo`。对于 `feat/` 分支，请使用简短的描述，例如：`feat/add-user-profile`。

#### PR 描述

- 请使用英文描述您的 PR。
- 标题请使用 `fix: `, `feat: `, `docs: `, `style: `, `refactor: `, `test: `, `chore: ` 等语义化前缀，并简要描述更改内容。如：`fix: correct login page typo`。

#### 代码规范

##### WebUI 与文档同步

- 修改菜单入口、页面结构或界面术语时，在同一个 PR 中更新 `docs/zh` 和 `docs/en` 的相关操作说明、链接与截图。没有对应英文页面时无需为此翻译整篇文档，但应检查已有英文说明。
- 按当前默认侧边栏、实际按钮文案和完整操作流程核对文档。重点检查配置文件、模型提供商、机器人、插件和系统设置；仅通过链接检查不能证明入口说明仍然正确。
- 入口改名、移动或合并时，在对应文档和 `changelogs/` 中写明「旧入口 → 新入口」，并同步维护 [WebUI 入口对照](docs/zh/use/webui.md#菜单与旧入口对照)。截图若仍展示旧结构，应更新或移除，并用可独立完成操作的文字步骤替代。
- 将布局重设计与新增功能尽量拆成独立 PR。新增功能优先沿用现有页面结构；确需调整已有入口时，在 PR 中说明原因和受影响的流程，避免连续、无关的页面重排。
- 提交前运行 `cd docs && pnpm run docs:build`，并按更新后的步骤核对相关 WebUI 页面。在 PR 中写明核对的页面和验证结果。

##### Core

我们使用 Ruff 作为代码格式化和静态分析工具。在提交代码之前，请运行以下命令以确保代码符合规范：

```bash
ruff format .
ruff check .
```

如果您使用 VSCode，可以安装 `Ruff` 插件。

##### PR 功能完整性验证（推荐）

如果您希望在本地做一套接近 CI 的完整验证，可使用：

```bash
make pr-test-neo
```

该命令会执行：
- `uv sync --group dev`
- `ruff format --check .` 与 `ruff check .`
- Neo 相关关键测试
- `main.py` 启动 smoke test（检测 `http://localhost:6185`）

需要全量验证时可使用：

```bash
make pr-test-full
```

如果只想快速重复执行（跳过依赖同步和 dashboard 构建）：

```bash
make pr-test-full-fast
```


## Contributing Guide

First off, thanks for taking the time to contribute! ❤️

All types of contributions are encouraged and valued. See the [Table of Contents](#table-of-contents) for different ways to help and details about how this project handles them. Please make sure to read the relevant section before making your contribution. It will make it a lot easier for us maintainers and smooth out the experience for all involved. The community looks forward to your contributions. 🎉

### Table of Contents

- [Reporting Issues](#reporting-issues)
- [Pull Requests](#pull-requests)

### Reporting Issues

If you encounter any issues while using AstrBot, please follow these steps to report them:
1. **Check Existing Issues**: Before submitting a new issue, please check if a similar issue already exists in the [Issues](https://github.com/AstrBotDevs/AstrBot/issues) section of the repository.
2. **Create a New Issue**: If no similar issue exists, please create a new issue. Make sure to provide the following information:
   - A brief description of the issue
   - Steps to reproduce the issue
   - Expected and actual results
   - Relevant logs or error messages

### Pull Requests

#### Branch Naming

We use the `fix/` prefix for bug fixes and the `feat/` prefix for new features. For `fix/` branches, please use a short description or directly use the Issue number, e.g., `fix/1234` or `fix/1234-login-typo`. For `feat/` branches, please use a short description, e.g., `feat/add-user-profile`.

#### PR Description
- Please use English to describe your PR.
- Use semantic prefixes like `fix: `, `feat: `, `docs: `, `style: `, `refactor: `, `test: `, `chore: ` in the title, followed by a brief description of the changes, e.g., `fix: correct login page typo`.

#### Code Style

##### Keep WebUI and documentation in sync

- When changing navigation, page structure, or UI labels, update the affected instructions, links, and screenshots in `docs/zh` and `docs/en` in the same PR. Check existing English instructions; translating an entire missing English page is not required.
- Verify the default sidebar, actual button labels, and complete workflows. Pay particular attention to profiles, providers, platforms, extensions, and system settings. Passing link checks does not establish that navigation instructions are correct.
- For renamed, moved, or merged entry points, include an **old entry → new entry** mapping in the relevant docs and `changelogs/`, and maintain the [WebUI navigation reference](docs/en/use/webui.md#navigation-and-previous-entry-points). Replace or remove screenshots showing outdated layouts, with text instructions sufficient to complete the task on their own.
- Keep layout redesigns and feature additions in separate PRs where practical. Prefer the existing page structure for new features. Explain necessary navigation changes and affected workflows in the PR to avoid repeated, unrelated rearrangements.
- Before submitting, run `cd docs && pnpm run docs:build` and check the affected WebUI pages against the updated steps. Include the checked pages and validation results in the PR.

##### Core

We use Ruff as our code formatter and static analysis tool. Before submitting your code, please run the following commands to ensure your code adheres to the style guidelines:

```bash
ruff format .
ruff check .
```

##### PR completeness checks (recommended)

To run a local validation flow close to CI, use:

```bash
make pr-test-neo
```

This command runs:
- `uv sync --group dev`
- `ruff format --check .` and `ruff check .`
- Neo-related critical tests
- a startup smoke test against `http://localhost:6185`

For full validation, use:

```bash
make pr-test-full
```

For faster repeated runs (skip dependency sync and dashboard build), use:

```bash
make pr-test-full-fast
```
