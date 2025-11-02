# AstrBot 开发指南

AstrBot 是一个使用 Python 编写、配备 Vue.js 仪表盘的多平台 LLM 聊天机器人开发框架。它支持多个消息平台（QQ、Telegram、Discord 等）和多种 LLM 提供商（OpenAI、Anthropic、Google Gemini 等）。

始终优先参考这些指南，仅在遇到与此处信息不符的意外情况时才回退到搜索或 bash 命令。

## 高效工作

### 引导和安装依赖
- **需要 Python 3.10+** - 检查 `.python-version` 文件
- 安装 UV 包管理器：`pip install uv`
- 安装项目依赖：`uv sync` -- 很快几分钟。绝不要取消。设置超时时间为 10+ 分钟。
- 创建必需的目录：`mkdir -p data/plugins data/config data/temp`

### 运行应用程序
- 运行主应用程序：`uv run main.py` -- 约 3 秒启动
- 应用程序在 http://localhost:6185 创建 WebUI（默认凭据：`astrbot`/`astrbot`）
- 应用程序自动从 `packages/` 和 `data/plugins/` 目录加载插件

### 仪表盘构建（Vue.js/Node.js）
- **前置要求**：需要 Node.js 20+ 和 npm 10+
- 导航到仪表盘：`cd dashboard`
- 安装仪表盘依赖：`npm install` -- 需要 2-3 分钟。绝不要取消。设置超时时间为 5+ 分钟。
- 构建仪表盘：`npm run build` -- 需要 25-30 秒。绝不要取消。
- 仪表盘在 `dashboard/dist/` 创建优化的生产构建

### 测试
- 暂时不要生成测试文件。

### 代码质量和检查
- 安装 ruff 检查器：`uv add --dev ruff`
- 检查代码风格：`uv run ruff check .` -- 耗时 <1 秒
- 检查格式：`uv run ruff format --check .` -- 耗时 <1 秒
- 修复格式：`uv run ruff format .`
- **始终**在提交更改前运行 `uv run ruff check .` 和 `uv run ruff format .`

### 插件开发
- 插件从 `packages/`（内置）和 `data/plugins/`（用户安装）加载
- 插件系统支持函数工具和消息处理器
- 关键插件：python_interpreter、web_searcher、astrbot、reminder、session_controller

### 常见问题和解决方法
- **仪表盘下载失败**：已知的"除以零"错误问题 - 应用程序仍可正常工作
- **测试中的导入错误**：确保使用 `uv run` 在适当的环境中运行测试
- **构建超时**：始终设置适当的超时时间（uv sync 为 10+ 分钟，npm install 为 5+ 分钟）

## CI/CD 集成
- GitHub Actions 工作流在 `.github/workflows/` 中
- 通过 `Dockerfile` 支持 Docker 构建
- Pre-commit 钩子强制执行 ruff 格式化和检查

## Docker 支持
- 主要部署方法：`docker run soulter/astrbot:latest`
- 可用的 Compose 文件：`compose.yml`
- 暴露端口：6185（WebUI）、6195（WeChat）、6199（QQ）等
- 需要挂载卷：`./data:/AstrBot/data`

## 多语言支持
- 文档包括中文（README.md）、英文（README_en.md）、日文（README_ja.md）
- UI 支持国际化
- 默认语言为中文

请记住：这是一个有真实用户的生产聊天机器人框架。始终进行彻底测试，确保更改不会破坏现有功能。
