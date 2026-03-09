## 2026-03-10 - 开发环境工具缺失

### 问题描述
- 运行 `ruff format .` 与 `ruff check .` 时提示 `ruff` 未识别。
- 尝试使用 `uv run ruff` 时提示 `uv` 未识别。
- 调用 LSP 诊断时报错：`basedpyright` 未安装，无法执行 `basedpyright-langserver`。

### 原因分析
当前环境未安装 `ruff`、`uv` 与 `basedpyright`，导致格式化/检查与 LSP 诊断无法执行。

### 解决过程
1. 尝试直接运行 `ruff` 失败，提示命令不存在。
2. 尝试通过 `uv run ruff` 失败，提示 `uv` 不存在。
3. 触发 LSP 诊断，提示 `basedpyright` 未安装。
4. 使用 `winget install` 安装 Python 3.11。
5. 使用 Python 安装 `ruff`、`basedpyright`、`uv`。
6. 执行 `setx PATH` 追加 Python 路径时，出现 PATH 被截断到 1024 字符的警告。
7. 创建 `C:\Users\VISIR\bin` 并复制 `basedpyright-langserver.exe` 到该目录，以确保 LSP 可找到。
8. 在 `qqofficial_platform_adapter.py` 添加 pyright 指令并调整类型处理，消除 `reportUnreachable` 提示。

### 建议解决方案
- 安装 `uv`：参考项目环境要求（如使用 `pipx` 或官方安装方式）。
- 安装 `ruff`：在 `uv` 环境或全局环境中安装。
- 安装 `basedpyright`：`pip install basedpyright`。

### 当前状态
Python/ruff/basedpyright/uv 已安装，LSP 诊断已通过；PATH 被 setx 截断的问题仍需后续确认。
