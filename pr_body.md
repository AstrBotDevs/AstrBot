### 问题描述
当使用 kimi-for-coding 模型开启思考模式（adaptive/思考预算0/思考深度Low）时，用户无法收到回复，控制台显示有思考内容但无报错。

### 根因分析
在 `tool_loop_agent_runner.py` 中，最终结果的 yield 逻辑只检查了 `result_chain` 和 `completion_text`，没有处理仅有 `reasoning_content` 的情况。当模型仅返回思考内容而 `completion_text` 为空时，最终响应不会发送给用户。

### 修复方案
在以下两处添加对 `reasoning_content` 的分支处理：
1. 主逻辑 (721-739行)
2. `skills_like` fallback (754-767行)

当 `completion_text` 为空但 `reasoning_content` 有值时，将 `reasoning_content` 作为 fallback 返回给用户。

### Related Issue
Fixes #7656

## Summary by Sourcery

Bug Fixes:
- Return reasoning content as a fallback response when completion text is empty so users still receive replies in thinking mode.