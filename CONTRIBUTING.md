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
