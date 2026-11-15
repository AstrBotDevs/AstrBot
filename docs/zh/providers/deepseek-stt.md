# 接入 DeepSeek STT

AstrBot 可通过 [DeepSeek 语音识别接口](https://api-docs.deepseek.com/zh-cn/guides/asr/) 将用户语音转成文字，再交给当前配置的对话模型处理。语音识别与对话模型相互独立，可以搭配其他品牌的对话模型。

## 获取 API Key

登录 [DeepSeek 开放平台](https://platform.deepseek.com/)，在 API Keys 页面创建并复制密钥。

## 添加提供商

1. 打开 AstrBot 管理面板，进入 **模型提供商 → 语音转文字 → 新增**。
2. 选择 **DeepSeek STT(API)**。
3. 填写并保存以下配置，然后启用该提供商：

| 配置项 | 说明 |
|--------|------|
| API Key | 在 DeepSeek 开放平台创建的密钥 |
| API Base URL | 默认为 `https://api.deepseek.com/v1`，AstrBot 会追加 `/tools/asr`；不要在末尾重复填写 `/v1` |
| 超时时间、代理、自定义请求头 | 可选，按网络环境配置 |

该接口不需要模型名称或语言参数，会自动识别语音语言。

## 启用语音识别

1. 进入 **配置文件**，选择要使用的配置文件。
2. 在 **AI → 模型** 中开启 **语音识别**。
3. 将 **默认语音转文本模型** 设为刚添加的 DeepSeek STT 提供商并保存。

收到语音消息后，AstrBot 会先把语音转成文字，再将转写结果作为用户消息交给当前对话模型。

## 音频要求与限制

- DeepSeek 接口支持 16 位 PCM WAV 和 Ogg Opus，并根据文件实际内容判断格式。
- WAV 支持 8000、16000、22050、24000、32000、44100、48000 Hz，以及单声道或双声道；双声道仅识别左声道。
- AstrBot 会复用已有 WAV，或将 SILK、AMR 等其他输入转换为 16 kHz、单声道、16 位 PCM WAV。转换 SILK 需要现有的 `silk-python` 依赖，其他格式转换需要 ffmpeg。
- 单个上传文件最大为 8 MiB，音频最长为 120 秒。AstrBot 会在发送请求前检查实际上传文件，超限时报错，不会静默截断音频。
- 接口不支持流式识别。未识别到语音时，AstrBot 不会生成虚假的转写内容。

最新接口说明与账号并发限制请以 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/guides/asr/) 为准。
