# 接入 OpenCode Go

[OpenCode Go](https://opencode.ai/docs/go/) 是面向编程代理的模型订阅服务。

## 获取 API Key

前往 [OpenCode 控制台](https://opencode.ai/auth)，订阅 Go 并复制 API Key。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **服务提供商 → 新增提供商**，根据 [OpenCode Go 文档](https://opencode.ai/docs/go/#endpoints)中模型的接口类型选择 **OpenCode Go Chat Completions**、**OpenCode Go Responses** 或 **OpenCode Go Messages**。

| 配置项 | 值 |
| --- | --- |
| API Base URL | `https://opencode.ai/zen/go/v1` |
| API Key | 在 OpenCode 控制台获取的 API Key |

保存后，点击提供商卡片，添加需要使用的模型。

## 设为默认模型

进入 **配置文件 → 提供商设置**，将「默认聊天模型」设置为刚刚添加的 OpenCode Go 模型，然后保存配置。

支持的模型、使用要求和额度请参阅 [OpenCode Go 文档](https://opencode.ai/docs/go/)。
