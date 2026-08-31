---
outline: deep
---

# 源码开发

本页给出当前 fork 的通用开发流程。Linux 的系统依赖和进程管理细节另见 [Linux 开发环境](/dev/linux)。

## 工具链基线

- Python 包要求：3.14 及以上
- 当前开发、Docker 与 CI Python：3.14.6
- Node.js：26.5.0
- Dashboard 与文档 pnpm：11.21.0
- Python 依赖管理：`uv`

版本来源分别是 `.python-version`、工作流、Dockerfile 和各目录的 `packageManager` 字段。升级工具链时必须同步这些位置及相应锁文件。

## 首次初始化

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`make doctor` 检查 Python 3.14.x、`uv`、Node 26.x 和 Dashboard pnpm 11.21.x；在 POSIX 上还检查 `shfmt`、`shellcheck` 和 `hadolint`。`make bootstrap` 使用锁文件同步 Python dev 依赖、根目录 Node 格式化工具和 Dashboard 依赖，但不会安装文档依赖。

- Windows：另需 GNU Make、PowerShell 7；PowerShell 检查还需要 PSScriptAnalyzer。`make doctor` 当前不会验证这三项。
- Linux/macOS：使用 Bash，不要求 PowerShell；严格检查需要 `shfmt`、`shellcheck` 和 `hadolint`。

如果只修改单个组件，也可以使用下方的直接命令，但不得绕过锁文件：

```bash
uv sync --group dev --locked
npm ci
cd dashboard
pnpm install --frozen-lockfile
cd ..
cd docs
pnpm install --frozen-lockfile
cd ..
```

## 启动开发环境

日常联调使用：

```bash
make dev
```

它会启动后端和 Vite Dashboard，不先执行生产构建：

- 后端：`http://127.0.0.1:6185`
- Dashboard dev server：`http://localhost:3000`

`make run` 会先同步 locked runtime 环境、构建 Dashboard 和文档并复制到 `data/dist`（文档在 `help/`），再启动两个进程；它不会构建 Python wheel/sdist。使用 `make status` 查看状态，`make stop` 只停止进程。`make build-docs` 只构建并同步文档；`make docs` 启动独立的 VitePress 预览（base 为 `/`）。

`make clean` 不是普通进程管理命令：它会先停止进程，然后广泛删除 `dashboard/dist`、`data/dist`、`.tmp`、build/dist、日志、测试/格式缓存和 `__pycache__` 等生成内容。运行前先检查工作树和需要保留的本地产物。

聚焦后端时：

```bash
uv run main.py
```

聚焦 Dashboard 时：

```bash
cd dashboard
pnpm dev
```

运行时数据写入当前 runtime root 的 `data/`。测试和临时验证不要读取或覆盖开发者真实的 `data/` 目录；使用 pytest 的临时目录 fixture 或设置独立的 `ASTRBOT_ROOT`。

主 SQLite schema 只由 SQLModel 表、`po/registry.py` 和 `tests/unit/db/test_schema.py` 锁定。`initialize()` 不会给已有 `data/data_v4.db` 加列。本机停进程后删除 `data/data_v4.db*` 再启动即可；测试使用临时库。架构见[项目架构](/dev/architecture#主-sqlite-库)。

## 测试

```bash
uv run pytest
uv run pytest tests/unit
uv run pytest tests/unit/test_event_bus.py
uv run pytest tests/unit/test_event_bus.py::TestEventBusDispatch::test_dispatch_processes_event
uv run pytest --test-profile blocking
make test-blocking
```

`blocking` profile 只排除标记为 `slow`、`integration` 或 `live` 的测试。`platform` 和 `provider` 是领域标签，不会把测试移出 blocking 门禁。`tests/integration/` 和 `tests/e2e/` 下的测试会自动归类为集成测试；真实外网、厂商 SDK 或外部密钥测试使用 `live`。回归测试应放在离被改代码最近的现有测试文件，不要机械地全部放入 `tests/unit/`。

Dashboard 使用 Vitest：

```bash
cd dashboard
pnpm test
```

插件 Dashboard Extension Protocol 使用 Playwright 做浏览器级 E2E。首次运行先安装
Chromium、Firefox 和 WebKit；`playwright.config.ts` 会自动启动隔离测试后端与 Vite，
不需要占用开发者真实的 `data/`：

```bash
cd dashboard
pnpm exec playwright install chromium firefox webkit
pnpm test:e2e
```

用例位于 `dashboard/tests/e2e/`，隔离后端入口是
`tests/e2e/plugin_ui_test_server.py`。PR/push CI 只跑 Chromium；Firefox 与
WebKit 项目定义保留在 `playwright.config.ts`，通过 `workflow_dispatch` 运行。
Linux CI 使用 `playwright install --with-deps` 同时安装系统依赖。

## 格式、检查与质量门禁

常用命令：

```bash
make check       # 当前宿主平台的严格源码检查
make quality     # 类型、安全、依赖审计与复杂度门禁
make test        # pytest 全量测试
make test-blocking  # pytest --test-profile blocking
make pr-test-full
```

`make check` 按宿主平台选择检查面。POSIX 上的 `make check-all-platforms` 会额外检查 PowerShell；Windows 的 `make check` 已包含 PowerShell，该 target 只会重复此项，仍不会模拟 shell/Docker 检查。完整 CI 由多个 workflow 共同组成，不能只用单个 Make target 代替。

`make check` 不运行写入式 formatter，但也不保证文件系统只读：Dashboard build 会写入 `dashboard/dist/`，并可能重新生成受跟踪的 MDI 子集资源。

写入式格式化命令：

```bash
make format
make format-py
make format-web
make format-md
```

`make format` 会修改多种受跟踪文件。`format-py`、`format-web` 和 `format-md` 只按文件类型缩小范围，仍会处理该类型的全仓库文件；脏工作树中需要保护同类型无关改动时，应直接对本次文件运行 Ruff/Prettier，并在格式化后检查 `git diff`。

## Dashboard 与 OpenAPI

普通 Dashboard JSON API 应采用以下结构：

- 路由：`astrbot/dashboard/api/`
- 业务服务：`astrbot/dashboard/services/`
- 请求模型：`astrbot/dashboard/schemas.py`
- 源规范：`openspec/openapi-v1.yaml`

修改路由、请求/响应 schema 或 OpenAPI 后，必须同时生成前端客户端和内置文档使用的 OpenAPI JSON：

```bash
cd dashboard
pnpm generate:api
cd ..
node node_modules/prettier/bin/prettier.cjs --write --ignore-path .gitignore "dashboard/src/api/generated/openapi-v1/**/*.ts"
uv run python docs/scripts/update_openapi_json.py
node node_modules/prettier/bin/prettier.cjs --write docs/public/openapi.json
```

生成目录 `dashboard/src/api/generated/openapi-v1/` 和公开 JSON 不得手工编辑。仓库 `.prettierignore` 默认排除生成客户端，因此必须用上面的 `--ignore-path .gitignore` 显式应用其已提交格式；两个格式化命令都只是机械处理。

## 文档

中英文都有对应页面时，行为、配置和工作流变化需要同步修改两个语言目录，并检查 `docs/.vitepress/config.mjs` 导航。

```bash
cd docs
pnpm install --frozen-lockfile
pnpm run docs:dev
pnpm run docs:build
```

生产构建会检查内部链接。不要编辑 `docs/.vitepress/dist/`；它是生成产物。生产构建默认 `base` 为 `/help/`，由 Dashboard 提供。`make check-md` 只枚举 Git 已跟踪的 Markdown，新建但尚未加入索引的页面还要显式运行 Prettier 和 markdownlint。

## 依赖变更

依赖文件必须成组同步：

- Python runtime：`pyproject.toml`、`requirements.txt`、`uv.lock`
- 根目录 Node 工具：`package.json`、`package-lock.json`
- Dashboard：`dashboard/package.json`、`dashboard/pnpm-lock.yaml`
- 文档：`docs/package.json`、`docs/pnpm-lock.yaml`

GitHub Actions 必须固定到完整 commit SHA，并按 job 授予实际状态变更所需的最小 scope。发布制品、上报代码扫描结果和维护 Issue 等写操作都必须分别论证，不能给整个 workflow 泛化写权限。

## 提交前

至少运行与改动相称的测试，然后执行：

```bash
make check
make quality
```

如果改动涉及 Dashboard、启动流程、跨平台脚本或发布产物，再运行 `make pr-test-full`。Commit 与 PR 标题使用英文 Conventional Commits，类型、描述和破坏性变更规则见仓库根目录 [CONTRIBUTING.md](https://github.com/Xero-Team/AstrBot/blob/master/CONTRIBUTING.md)。按类型选用 `.github/PULL_REQUEST_TEMPLATE/` 下的模板。AI 辅助生成或定稿的 commit message 另须遵守 `.agents/shared/conventional-commit/REFERENCE.md`。
