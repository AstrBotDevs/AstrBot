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

##### Core

我们使用 Ruff 作为代码格式化和静态分析工具。在提交代码之前，请运行以下命令以确保代码符合规范：

```bash
ruff format .
ruff check .
```

如果您使用 VSCode，可以安装 `Ruff` 插件。

##### Vendored SDK 同步

`astrbot-sdk/` 是主仓库中的 vendored SDK 副本。它只能通过手动执行 subtree 同步来升级，不能直接在主仓库里修改 vendored 内容。

建议在以下场景执行同步：

- SDK 仓库的 `sdk-remote/vendor-branch` 已经准备好给主仓库消费的新版本。
- 主仓库明确需要升级 vendored SDK，而不是临时试验或本地调试。

首次接入（本地还没有 `sdk-remote` 时）：

```powershell
git remote add sdk-remote https://github.com/united-pooh/astrbot-sdk.git
pwsh -File .\scripts\sync-sdk.ps1
```

```bash
git remote add sdk-remote https://github.com/united-pooh/astrbot-sdk.git
bash ./scripts/sync-sdk.sh
```

后续更新：

```powershell
pwsh -File .\scripts\sync-sdk.ps1
```

```bash
bash ./scripts/sync-sdk.sh
```

脚本会：

- 先 `git fetch sdk-remote vendor-branch`
- 校验远端分支是否仍然包含主仓库当前需要的 SDK 包布局
- 使用 `git subtree pull --prefix=astrbot-sdk sdk-remote vendor-branch --squash` 执行同步

如果 `vendor-branch` 不包含 `pyproject.toml` 或 `src/astrbot_sdk/` 等关键路径，脚本会直接失败并提示原因，而不是把不兼容的快照同步进来。

同步后请至少执行以下检查：

```powershell
git status --short
Get-ChildItem .\astrbot-sdk
Test-Path .\astrbot-sdk\pyproject.toml
Test-Path .\astrbot-sdk\src\astrbot_sdk\__init__.py
uv sync
```

```bash
git status --short
ls ./astrbot-sdk
test -e ./astrbot-sdk/pyproject.toml
test -e ./astrbot-sdk/src/astrbot_sdk/__init__.py
uv sync
```

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

##### Core

We use Ruff as our code formatter and static analysis tool. Before submitting your code, please run the following commands to ensure your code adheres to the style guidelines:

```bash
ruff format .
ruff check .
```

##### Vendored SDK Sync

`astrbot-sdk/` is a vendored SDK copy inside the main repository. Upgrade it only through the manual subtree sync flow; do not edit vendored files in place inside this repository.

Run the sync only when:

- `sdk-remote/vendor-branch` has been prepared as the SDK version intended for the main repository.
- the main repository explicitly wants to upgrade the vendored SDK.

First-time setup (when `sdk-remote` is not configured locally yet):

```powershell
git remote add sdk-remote https://github.com/united-pooh/astrbot-sdk.git
pwsh -File .\scripts\sync-sdk.ps1
```

```bash
git remote add sdk-remote https://github.com/united-pooh/astrbot-sdk.git
bash ./scripts/sync-sdk.sh
```

Subsequent updates:

```powershell
pwsh -File .\scripts\sync-sdk.ps1
```

```bash
bash ./scripts/sync-sdk.sh
```

The script will:

- `git fetch sdk-remote vendor-branch`
- verify that the remote branch still exposes the SDK package layout required by the main repository
- run `git subtree pull --prefix=astrbot-sdk sdk-remote vendor-branch --squash`

If `vendor-branch` is missing critical paths such as `pyproject.toml` or `src/astrbot_sdk/`, the script fails fast instead of syncing an incompatible snapshot.

After syncing, validate the directory layout with:

```powershell
git status --short
Get-ChildItem .\astrbot-sdk
Test-Path .\astrbot-sdk\pyproject.toml
Test-Path .\astrbot-sdk\src\astrbot_sdk\__init__.py
uv sync
```

```bash
git status --short
ls ./astrbot-sdk
test -e ./astrbot-sdk/pyproject.toml
test -e ./astrbot-sdk/src/astrbot_sdk/__init__.py
uv sync
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
