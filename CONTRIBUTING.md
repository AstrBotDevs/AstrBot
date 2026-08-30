# CONTRIBUTING

## 中文

### 仓库定位

本仓库是 AstrBot 的现代化 fork。贡献时请遵守以下原则：

- 以当前分支代码事实为准，不为旧 API、旧插件格式、旧知识库布局继续补兼容。
- Python 基线是 `3.14+`。
- 后端开发流程使用 `uv`，Dashboard 前端流程使用 `pnpm`。
- 如果新旧路径并存，优先沿用新路径，不要继续扩展 legacy shim。

### 问题与反馈

本 fork 不运营公开 Issue 跟踪器或支持队列。安全漏洞按 [SECURITY.md](SECURITY.md) 私密报告。代码贡献走 Pull Request。

### 开发环境

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`pre-commit` 不在当前 `pyproject.toml` 的 `dev` 依赖组中，因此不要求安装 Git hook。需要 hook 时可以自行安装 `pre-commit` 并运行 `pre-commit install`；也可以不装 hook，直接使用 `make check`。

常用命令：

```bash
uv run main.py
ruff format .
ruff check .
make dev
make build-docs
make check
make quality
cd dashboard && pnpm generate:api
```

`make run` 会把文档打进 WebUI 的 `/help/`。不要把文档链接指向上游 `docs.astrbot.app`。

如果你修改了后端 OpenAPI、接口路由或响应结构，请同时刷新：

```bash
cd dashboard && pnpm generate:api
uv run python docs/scripts/update_openapi_json.py
```

### 提交代码

- 分支名建议使用 `fix/`、`feat/`、`docs/`、`refactor/` 等前缀。
- Commit 与 PR 标题使用英文 Conventional Commits，格式为 `<type>(<optional scope>): <description>`，例如 `fix: align openapi scope docs with backend`。
- `type` 取自：`feat`、`fix`、`refactor`、`perf`、`style`、`test`、`docs`、`build`、`ops`、`chore`。不要使用 `ci`；持续集成与部署类改动用 `ops`。
- `description` 使用祈使现在时、小写开头、句末不加句号；标题建议不超过约 70 个字符。
- 破坏性变更在 `:` 前加 `!`，并在 footer 写 `BREAKING CHANGE:`。议题编号放在 footer（例如 `Fixes #123`），不要当作 scope。
- AI 辅助生成或定稿的 commit message 必须遵守 [`.agents/shared/conventional-commit/REFERENCE.md`](.agents/shared/conventional-commit/REFERENCE.md)，并在 footer 附加 `AI-Generated: true` 与 UTC `Generated-At:`。人工撰写的提交可以省略这两项 footer。
- 不要把“兼容旧版本”的文案或代码路径重新带回仓库。

提交前至少运行：

```bash
ruff format .
ruff check .
make check
```

如果希望执行一套更接近 CI 的验证：

```bash
make pr-test-neo
make pr-test-full
make pr-test-full-fast
```

Linux contributors should follow [the Linux development guide](docs/zh/dev/linux.md)
for system prerequisites, log locations, and native process management.

## English

### Repository Scope

This repository is a modernized AstrBot fork. Please follow these rules:

- Match the current branch, not upstream historical behavior.
- Do not add or preserve compatibility shims for deprecated APIs, plugin formats, or old knowledge-base layouts.
- The Python baseline is `3.14+`.
- Backend workflows use `uv`; dashboard workflows use `pnpm`.

### Issues and Feedback

This fork does not operate a public issue tracker or support queue. Security reports go through [SECURITY.md](SECURITY.md). Code contributions go through a Pull Request.

### Development Setup

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`pre-commit` is not in the current `pyproject.toml` `dev` dependency group, so a Git hook is optional. Install `pre-commit` yourself and run `pre-commit install` if you want the hook; otherwise skip it and run `make check`.

Common commands:

```bash
uv run main.py
ruff format .
ruff check .
make dev
make build-docs
make check
make quality
cd dashboard && pnpm generate:api
```

`make run` serves documentation from the WebUI at `/help/`. Do not point documentation links at upstream `docs.astrbot.app`.

If you change backend OpenAPI routes, request schemas, or response schemas, also refresh:

```bash
cd dashboard && pnpm generate:api
uv run python docs/scripts/update_openapi_json.py
```

### Pull Requests

- Prefer branch names such as `fix/...`, `feat/...`, `docs/...`, or `refactor/...`.
- Use English Conventional Commits for commit and PR titles: `<type>(<optional scope>): <description>`, for example `docs: align docker guide with repo compose files`.
- Allowed types: `feat`, `fix`, `refactor`, `perf`, `style`, `test`, `docs`, `build`, `ops`, `chore`. Do not use `ci`; use `ops` for CI/CD and deployment changes.
- Write a lowercase imperative description with no trailing period. Keep the header under about 70 characters.
- Mark breaking changes with `!` before `:` and a `BREAKING CHANGE:` footer. Put issue IDs in footers (`Fixes #123`), never as scopes.
- AI-assisted commit messages must follow [`.agents/shared/conventional-commit/REFERENCE.md`](.agents/shared/conventional-commit/REFERENCE.md) and append `AI-Generated: true` plus a UTC `Generated-At:` footer. Human-written commits may omit those footers.
- Do not reintroduce legacy compatibility narratives or old code paths.

Run at least these checks before submitting:

```bash
ruff format .
ruff check .
make check
```

For a CI-like local pass:

```bash
make pr-test-neo
make pr-test-full
make pr-test-full-fast
```

Linux contributors should follow [the Linux development guide](docs/en/dev/linux.md)
for system prerequisites, log locations, and native process management.
