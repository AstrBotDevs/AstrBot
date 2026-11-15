# 接入 DeepSeek TTS

AstrBot 可通过 [DeepSeek 语音合成接口](https://api-docs.deepseek.com/zh-cn/guides/tts/) 将文字合成为 WAV 语音。

## 获取 API Key

登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，在 API Keys 页面创建并复制密钥。

## 添加提供商

1. 打开 AstrBot 管理面板，进入 **模型提供商 → 文字转语音 → 新增**。
2. 选择 **DeepSeek TTS(API)**。
3. 填写并保存以下配置，然后启用该提供商：

| 配置项 | 说明 |
|--------|------|
| API Key | 在 DeepSeek 开放平台创建的密钥 |
| API Base URL | 默认为 `https://api.deepseek.com/v1`，AstrBot 会追加 `/tools/tts`；不要在末尾重复填写 `/v1` |
| 音色 | **海星（女声，默认）** 对应 `stella`；**暗潮（男声）** 对应 `tide` |
| 过滤 Markdown | 默认启用，在朗读前移除 Markdown 格式 |
| 超时时间、代理、自定义请求头 | 可选，按网络环境配置 |

输出格式固定为 WAV，无需填写模型名称。接口会根据文本自动识别语言，不提供语言或语速配置。

## 启用语音回复

1. 进入 **配置文件**，选择要使用的配置文件。
2. 在 **AI → 模型** 中开启 **语音回复**。
3. 将 **默认文本转语音模型** 设为刚添加的 DeepSeek TTS 提供商并保存。

此后，AstrBot 会通过现有语音回复流程调用 DeepSeek TTS 并发送生成的 WAV 音频。

## 文本限制与错误处理

- 文本不能为空，单次最多 10,000 个计费字符：汉字算 2 个，其他字符算 1 个。AstrBot 不会静默截断超限文本。
- 整个 JSON 请求体最大为 64 KiB。
- 接口以流式二进制返回音频。如果响应为空、不是 WAV，或传输中途失败，本次合成会报错并清理未完成的临时文件。
- 单次请求最多返回 30 分钟音频；账号并发限制及最新接口说明请以 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/guides/tts/) 为准。
