# Project Context

## Purpose
AstrBot 是一个多平台的对话机器人框架，目标是提供可扩展的插件系统与统一的仪表盘（Web UI），便于在不同消息平台（QQ、Telegram、Discord 等）上快速构建、部署和运维基于 LLM 的聊天体验。

主要职责：
- 提供一致的插件加载与运行时（packages/ 与 data/plugins/）
- 抽象各消息平台和 provider 层，方便接入不同 LLM 后端
- 提供一个 Vue.js 驱动的 dashboard（仪表盘）用于监控与配置

## Tech Stack
- Python 3.10+（代码主体）
	- 入口文件：`main.py`
	- 包结构：`astrbot/`（核心逻辑、API、CLI、core）
- 包管理 / 项目命令：`uv`（项目使用的推荐工具）
	- 安装依赖：`uv sync`
	- 运行应用：`uv run main.py`
- Dashboard (UI)：Vue.js（TypeScript 支持）
	- Node.js 20+ / npm 10+
	- 仪表盘目录：`dashboard/`（`package.json`、`src/`、`public/`）
- 测试：pytest（仓库中已有若干测试文件 `tests/`）
- Lint & Formatting：`ruff`（作为主要 linter/formatter）
- 打包 / 部署：Dockerfile 已支持容器部署（仓库根目录下）

## Project Conventions

### Code Style
- 使用 `ruff` 进行静态检查与格式化：
	- 检查：`uv run ruff check .`
	- 自动格式化：`uv run ruff format .`
- 请遵循现有代码风格（保持现有缩进/命名模式），新增代码应包含类型注释（如果合适）并包含单元测试。

### Architecture Patterns
- 插件化：内置插件在 `packages/`，第三方/运行时插件放到 `data/plugins/`。插件应保持小而单一的职责。
- 多层分离：`astrbot/api/`（HTTP/外部协议）、`astrbot/core/`（业务逻辑）和 `astrbot/cli/`（命令行）分离。
- 仪表盘作为单独前端项目（`dashboard/`），通过后端 API 与核心服务通信。

### Testing Strategy
- 现有基础测试位于 `tests/`。提交新功能时应至少提供：
	- 1 个 happy-path 单元测试
	- 1 个关键边界/错误路径测试
- 不要在首次提交时生成大量测试；优先覆盖关键逻辑。

### Git Workflow
- 默认分支：`master`
- 分支命名约定：`feat/<short-desc>`、`fix/<short-desc>`、`chore/<short-desc>`、`refactor/<short-desc>`。
- 提交信息建议：
	- 使用简短前缀（feat/fix/docs/chore） + 说明
	- 在 PR 描述中引用相关 `openspec` 变更目录（如有）

## Domain Context
- AstrBot 关注点为跨平台消息与 LLM 集成：会处理会话管理、插件沙箱、provider 适配、以及 dashboard 的多租户/多账号视图。
- 主要“能力”通常以 `openspec/specs/<capability>/spec.md` 的形式记录。

## Important Constraints
- Python 运行时必须 >= 3.10（仓库 `.python-version` 表明这一点）
- 仪表盘依赖 Node.js 20+ / npm 10+。
- CI/PR 中应保持 `ruff` 通过并运行核心单元测试（如有配置的 CI）。

## External Dependencies
- 可能使用的 LLM 提供者（OpenAI、Anthropic、Google 等）通过 provider 插件接入。
- 仪表盘构建依赖于 npm registry（需要网络访问）

## Assumptions and Notes
- 假设：`uv` 是团队约定的项目管理工具（见 `.github/copilot-instructions.md` / 仓库 README）。
- 假设当前分支策略与上文 Git Workflow 一致（若不一致请告知具体策略，我会调整 `project.md`）。
- 如果你希望我把项目中的具体文件引用（例如某些 capability 的 spec）嵌入这里，请告诉我要引用的 spec id 或路径。

---

如果你同意以上内容，我可以：
- 直接把这个内容提交到 `openspec/project.md`（已完成）
- 基于本 `project.md` 创建 OpenSpec 变更提案的模板并运行 `openspec validate`（如果你希望我执行验证，请先确认本地是否安装 `openspec` 工具或授权我运行验证命令）
