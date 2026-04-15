# Anthropic

Anthropic 是 Claude 系列模型的提供商。AstrBot 原生支持 Anthropic API 格式。

## 接入步骤

1. 前往 [Anthropic Console](https://console.anthropic.com/) 注册账号并获取 API Key
2. 在 AstrBot 控制台 → 服务提供商页面，点击新增提供商，选择 `Anthropic`
3. 填入 API Key，点击获取模型列表，选择所需模型

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| API Key | Anthropic API 密钥 | - |
| API Base | API 地址，使用官方服务无需修改 | `https://api.anthropic.com/v1` |
| Timeout | 请求超时时间（秒） | 120 |
| Proxy | 代理地址 | - |
| **Max Tokens** | 模型单次回复的最大 token 数量。如果回复经常被截断，可以适当调大 | 4096 |
| Thinking Config | 思考配置，Opus 4.6+ / Sonnet 4.6+ 推荐设为 `adaptive` | - |

### Max Tokens 说明

`max_tokens` 控制模型单次回复可以生成的最大 token 数量。在使用 Agent/工具调用等场景下，模型输出可能较长，建议根据实际需求调大此值（如 8192 或 16384）。

在 AstrBot 控制台 → 服务提供商 → 点击对应的 Anthropic 提供商 → 找到「最大输出 Token 数」进行配置。
