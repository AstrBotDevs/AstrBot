# CONTRIBUTING

## 中文

### 仓库定位

本仓库是 AstrBot 的现代化 fork。贡献时请遵守以下原则：

- 以当前分支代码事实为准，不为旧 API、旧插件格式、旧知识库布局继续补兼容。
- Python 基线是 `3.14+`。
- 后端开发流程使用 `uv`，Dashboard 前端流程使用 `pnpm`。
- 如果新旧路径并存，优先沿用新路径，不要继续扩展 legacy shim。

### 报告问题

请在当前 fork 的仓库提交问题：
<https://github.com/Xero-Team/AstrBot/issues>

提交前请先确认是否已有相同问题，并尽量附上：

- 复现步骤
- 预期行为和实际行为
- 日志、截图、配置片段或调用示例
- 运行方式：`uv`、Docker 或源码

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
make check
make quality
cd dashboard && pnpm generate:api
```

如果你修改了后端 OpenAPI、接口路由或响应结构，请同时刷新：

```bash
cd dashboard && pnpm generate:api
uv run python docs/scripts/update_openapi_json.py
```

### 提交代码

- 分支名建议使用 `fix/`、`feat/`、`docs/`、`refactor/` 等前缀。
- Commit 与 PR 标题请使用英文 Conventional Commits，例如 `fix: align openapi scope docs with backend`.
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

### Reporting Issues

Please file issues in this fork:
<https://github.com/Xero-Team/AstrBot/issues>

Include:

- reproduction steps
- expected and actual behavior
- logs, screenshots, config snippets, or API examples
- deployment mode: `uv`, Docker, or source

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
make check
make quality
cd dashboard && pnpm generate:api
```

If you change backend OpenAPI routes, request schemas, or response schemas, also refresh:

```bash
cd dashboard && pnpm generate:api
uv run python docs/scripts/update_openapi_json.py
```

### Pull Requests

- Prefer branch names such as `fix/...`, `feat/...`, `docs/...`, or `refactor/...`.
- Use English Conventional Commit titles, for example `docs: align docker guide with repo compose files`.
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
