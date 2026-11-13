# 大语言模型提供商

在 WebUI 的「模型提供商」→「对话」中点击「新增」，选择模型服务类型。兼容 OpenAI API 的服务可选择 `OpenAI Compatible`，并填写服务商提供的 API Base URL 和 API Key。

填写提供商名称和 `API Key`，确认 `API Base URL`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

进入「配置文件」，选择要使用的配置文件，在「AI」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

详细步骤见 [接入模型服务](./start.md)。

> 提供商连接配置保存在 `data/cmd_config.json` 的 `provider_sources` 字段，具体模型配置保存在 `provider` 字段。

## 自定义请求头变量

提供商配置中的「自定义请求头」支持变量模板，值在每次请求时渲染：

| 变量 | 含义 |
| --- | --- |
| `{conversation_id}` | AstrBot 会话 ID，为空时回退到本次请求 ID |
| `{umo}` | 消息来源标识（unified message origin） |
| `{request_id}` | 一次 Agent 运行内稳定的请求 ID |
| `{model}` | 本次请求最终使用的模型名 |
| `{provider_id}` | 提供商配置 ID |
| `{version}` | AstrBot 版本 |

`{sha256:<模板>}` 计算 SHA-256 摘要；`{uuid5:<模板>}` 使用固定命名空间对原始值生成标准 UUID v5，同一输入的结果稳定。内层均可包含文本和上述变量，引用变量为空时省略请求头。未经转换的变量值中，非 ASCII 字符（例如中文平台 ID）、控制字符和 `%` 会按 UTF-8 百分号编码（与 URL 编码相同），可用标准 URL 解码还原。

只有上表中的变量会被替换，其他内容（包括其他花括号）按原样发送；`Authorization`、`x-api-key` 等鉴权请求头始终按原样发送。

```json
{
  "x-opencode-session": "{sha256:{conversation_id}}",
  "x-session-uuid": "{uuid5:{conversation_id}}"
}
```

`{umo}` 可能包含平台、群组或用户信息，并会随请求发送给第三方服务；SHA-256 和 UUID v5 都是确定性编码，不等于匿名化。
