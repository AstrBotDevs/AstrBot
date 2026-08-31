# 上下文压缩

AstrBot 会在本地 Agent Runner 的上下文接近模型窗口上限时自动整理历史消息，避免请求因为上下文过长而失败。默认策略是使用 LLM 总结较早的历史，并原样保留最近的对话。

![上下文压缩设置](https://files.astrbot.app/docs/source/images/context-compress/image.png)

## 什么时候触发

每个 Agent step 在请求模型前都会检查上下文；这也包括工具执行完成后进入下一次模型调用的步骤。估算的上下文 token 数超过模型窗口的 **82%** 时才会触发压缩。

窗口大小按以下顺序确定：

1. 使用模型配置中的 `max_context_tokens`。
2. 如果该值未设置或不大于 0，尝试从内置模型元数据获取。
3. 如果仍无法识别，使用 `agent_runner.config.compression.fallback_max_tokens`，默认值为 `128000`。

因此，自定义模型 ID 或代理服务使用的模型名无法被自动识别时，最好在模型配置中填写准确的 `max_context_tokens`。过大的值可能导致请求先被服务商拒绝，过小的值则会过早压缩。

![模型上下文窗口设置](https://files.astrbot.app/docs/source/images/context-compress/image1.png)

## 两种策略

在配置档的 Agent Runner 设置中，通过 `agent_runner.config.compression.overflow_strategy` 选择策略。

### `llm_compress`：LLM 摘要（默认）

AstrBot 把较早的完整对话轮次交给压缩模型生成摘要，再把摘要与最近的原始轮次组合成新的上下文。

- `agent_runner.config.compression.provider_id`：指定用于摘要的聊天模型。留空时使用当前会话正在使用的模型。
- `agent_runner.config.compression.keep_recent_ratio`：按压缩前 token 数计算、原样保留最近上下文的比例，默认 `0.15`。该值会限制在 `0` 到 `0.3` 之间，并按完整对话轮次保留；不会从轮次中间截断。最新的活动用户请求也会尽量原样保留。
- `agent_runner.config.compression.instruction`：自定义摘要指令。

默认指令要求摘要覆盖：

1. 所有核心主题、结论和当前主要焦点；
2. 工具调用次数及最有价值的工具输出；
3. 已读取且后续仍可能使用的文件、文档、代码和路径；
4. 用户的初始目标以及当前进度；
5. 使用用户的语言输出，并在任务仍进行时给出最新结果和下一步。

如果指定的压缩模型不可用，AstrBot 会尝试当前会话模型；如果没有可用模型，则使用按轮次截断。摘要调用失败或摘要后仍超过阈值时，运行时还会执行截断保护，确保后续模型请求不会持续携带过大的上下文。

### `truncate_by_turns`：按轮次截断

此策略不额外调用 LLM，而是从最早的完整对话轮次开始移除。`agent_runner.config.compression.trim_turns` 控制每次至少丢弃多少轮，默认值为 `1`。它速度快且没有额外模型费用，但早期细节会直接丢失。

## 最大对话轮数

`agent_runner.config.compression.max_turns` 是独立于 token 阈值的轮数限制：

- `-1`：不按轮数强制限制，这是默认值；
- 正整数：在 token 压缩前先只保留最近的对应轮数。

如果同时设置轮数限制和 token 压缩，轮数限制会先执行。对长时间运行、工具输出较多的任务，通常建议保持 `llm_compress`，并为模型填写准确的上下文窗口；只有在希望完全避免摘要调用时才改用按轮次截断。
