# 接入 Dots

AstrBot 提供独立的 **Dots** 模型服务商，复用 OpenAI Chat Completions 协议，并兼容 Dots 原生工具调用格式。本适配主要覆盖文本、工具调用和流式输出；音频、视频尚未专项验证。

## 配置步骤

1. 在 [Dots API 开放平台](https://dots.ai/platform/apikeys)创建 API Key。
2. 打开 **模型提供商 → 对话**，在 **提供商源** 中点击 **新增**，选择 **Dots**。
3. 填写服务商名称和 API Key。默认 API Base URL 为 `https://note3-prev-api.askdiandian.com/v1`。适配器自动发送 `api-key` 请求头，无需在自定义请求头中重复填写密钥。
4. 点击 **保存并获取模型**，在 `dots3-note-prev` 旁点击 `+`，并确保模型已启用。也可以保存配置后，通过 **自定义模型** 输入模型 ID。
5. 点击模型旁的 **测试模型** 检查连通性。
6. 打开 **配置文件**，选择需要使用的配置文件，在 **AI → 模型** 中将 **对话模型** 设为刚刚添加的模型，点击右下角 **保存配置**。
7. 在使用该配置文件的会话中发送一条消息，确认正常回复。

API Key 支持 AstrBot 的环境变量写法，例如 `$DOTS_API_KEY`。配置多个 Key 时，鉴权请求头随本次请求选中的 Key 更新。

## 从 OpenAI Compatible 配置迁移

| 原配置 | 新配置 |
| --- | --- |
| 使用 OpenAI Compatible 接入 Dots | 新增 Dots 服务商，填入相同的端点与 Key |
| 配置文件选用旧服务商下的模型 | 添加新服务商下的模型后，重新选择对话模型 |
| 自定义请求头手动填写 `api-key` | 使用服务商的 API Key 字段，由适配器处理鉴权 |

旧配置不会自动迁移。只有选择 Dots 服务商，才会启用专用的工具调用兼容处理。

## 工具调用与流式输出

使用工具前，确认模型能力包含 **工具使用**。网页搜索需[单独配置](/use/websearch)，配置后可发送搜索请求验证工具调用和结果回复。

流式输出默认关闭，可在 **配置文件 → AI → 通用设置 → 流式输出** 中开启并保存配置。

- 标准 `tool_calls` 优先；原生 `<dots_function_call>` 仅在 `finish_reason: tool_calls` 时转换并校验，避免同一响应中的两种格式重复执行。
- 普通回答和思考内容中的调用示例不会执行，字符串参数保留原始空白。无标准调用时，非法或不完整的原生调用会报错。
- 开启流式后，普通文字实时输出。请求携带工具时，原生调用标记、正文内思考标记及后续内容会暂存至响应结束，再区分正文、思考和工具调用。
- 工具在完整响应校验后执行；断流或解析失败时，已显示文字无法撤回。适配器不做跨轮工具去重，仍受 AstrBot 的工具调用轮数限制。

自建 vLLM 服务时，建议按 [vLLM Dots 部署文档](https://recipes.vllm.ai/dots-studio/dots3-note-prev)启用 `--enable-auto-tool-choice --tool-call-parser dots`，让服务端返回标准工具调用。

模型名称、能力和可用端点以 [Dots 官方接口文档](https://dots.ai/platform/docs)为准。
