# Provider 配置

在 WebUI 的 **提供商** 页面管理 Provider 来源和模型；在 **配置** 页面为每个配置档选择默认模型。

![Provider 页面](https://files.astrbot.app/docs/source/images/llm/image.png)

![模型配置](https://files.astrbot.app/docs/source/images/llm/image-1.png)

## Provider 来源

新增来源时重点核对：

- **类型**：决定加载哪个适配器和哪些专用字段；不要仅凭服务名称选择。
- **API Base**：通常应包含服务要求的版本路径，例如 OpenAI 兼容服务常见 `/v1`。这是 AstrBot 的出站请求地址，不是 WebUI 回调地址。原生 Anthropic 适配器应填写 `https://api.anthropic.com`，不要带 `/v1`；已保存的 `/v1` 后缀会在运行时去掉。
- **API Key**：可以填写多个 Key 或 `$ENV_NAME` 引用；不要在日志和截图中暴露。
- **Timeout / Proxy / Custom Headers**：由来源统一继承到模型。自定义 Header 可能包含凭据，也应按 secret 处理。

保存来源后优先通过“获取模型”导入模型列表；服务不支持列举模型时再手工填写。

## 模型实例

模型实例至少需要唯一 ID、真实模型名和 `provider_source_id`。建议同时核对：

- `max_context_tokens`：上下文压缩和请求保护依赖此值；自定义模型名无法从内置元数据识别时必须手填。
- 模态：文本、图片等能力应和服务实际支持一致。
- 工具调用：只有服务完整支持 function/tool calling 时才向 Agent 暴露工具。
- 生成参数：temperature、top-p、max tokens 等是否被目标模型接受。

同一来源可以创建多个模型。不要通过复制 JSON 产生重复 ID；Provider Manager 以 ID 解析默认模型、fallback 和 Persona/配置引用。

## OpenAI Responses

OpenAI Responses 来源提供以下专用设置：

| 字段                                 | 默认值      | 说明                                                                                                |
| ------------------------------------ | ----------- | --------------------------------------------------------------------------------------------------- |
| `responses_state_mode`               | `stateless` | `stateless` 在本地重放上下文；`previous_response_id` 和 `conversation` 使用 OpenAI 保存的远端状态。 |
| `store`                              | `false`     | 允许服务端保存 Responses 状态。两个有状态模式和 background 都要求开启。                             |
| `responses_background`               | `false`     | 提交后台响应并轮询结果；要求非 `stateless` 且 `store=true`。                                        |
| `responses_background_poll_interval` | `1`         | 后台轮询间隔秒数。                                                                                  |
| `responses_background_timeout`       | `600`       | 后台等待超时；中止或超时会尝试取消远端响应。                                                        |
| `web_search`                         | 关闭        | OpenAI 原生 Web Search，可限制域名、上下文大小，并选择返回来源或原始结果。                          |

> [!WARNING]
> `previous_response_id`、`conversation`、`store` 和 background 会把状态保存在远端服务。选择前应确认数据驻留、保留期限、删除能力和组织合规要求。希望所有历史仅由 AstrBot 本地重放时使用 `stateless` 且保持 `store=false`。

Provider 来源内的原生 `web_search` 只作用于 OpenAI Responses；配置档中的 `provider_settings.web_search` 是 AstrBot 自己的跨 Provider 搜索工具，两者可以独立启用，费用和来源格式也不同。

## 默认模型与 fallback

在 **配置** 页的 Agent Runner 中配置：

- `agent_runner.config.model.provider_id`：默认聊天模型；
- `agent_runner.config.model.fallback_provider_ids`：主模型失败后按顺序尝试；
- `agent_runner.config.model.request_max_retries`：每个模型的请求重试上限；
- `default_image_caption_provider_id`、STT、TTS、Embedding 和 Rerank 默认模型。

避免把同一不稳定端点下的多个模型误当作真正的故障隔离。可靠 fallback 应尽量使用不同来源、不同凭据或不同供应商，并控制最坏情况下的总等待时间。

## TTS 与 ElevenLabs

当前 TTS 类型包含 ElevenLabs。配置 `elevenlabs_tts_api` 时需要 API Key、Voice ID 和输出格式；stability、similarity boost、style 与 speaker boost 是可选声音设置。TTS 总开关、默认模型、双输出、文件服务和触发概率位于配置档的 `provider_tts_settings`。

MiMo TTS 当前默认使用 `mimo-v2.5-tts`，因为旧的 `mimo-v2-tts` 模型已经下线。升级时不会自动改写已有 Provider 条目中的模型值；如果 MiMo TTS 条目仍使用旧模型，请手动编辑为新模型。

音频格式能否在最终消息平台播放仍取决于平台适配器，不应只以 Provider 测试成功为准。

## 安全与排错

- 保持 TLS 验证，不要通过 `verify=false`、`ssl=false` 或不受信任的中间人证书绕过下载/Provider 安全。
- 私有端点应通过受控内网、VPN 或反向代理访问；不要为了测试把本地模型端口直接暴露到公网。
- 测试失败时依次核对 API Base、模型 ID、Key 权限、代理、超时、模态和工具能力。
- 修改来源后，重新测试所有引用它的模型以及当前配置档的默认/fallback 链。

配置文件结构见 [AstrBot 配置参考](../dev/astrbot-config)。
