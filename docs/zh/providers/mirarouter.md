# 接入 MiraRouter

[MiraRouter](https://mirarouter.com/) 提供稳定、安全且兼容 OpenAI 格式的统一模型 API，可通过一个 API Key 接入多种主流模型，并集中管理密钥、用量与成本。

## 获取 API Key

1. 前往 [MiraRouter](https://mirarouter.com/) 注册并登录账号。
2. 进入控制台，创建并复制 API Key。完整密钥仅在创建时显示，请妥善保存。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **模型提供商 → 对话 → 新增 → MiraRouter**，填写以下信息：

| 配置项 | 值 |
| --- | --- |
| 提供商名称 | `MiraRouter` |
| API Base URL | `https://api.mirarouter.com/v1` |
| API Key | 在 MiraRouter 控制台创建的 API Key |

AstrBot 会自动为 MiraRouter 请求添加 `X-APP-CODE: astrbot` 标识。

填写提供商名称和 `API Key`，确认 `API Base URL`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

## 设为默认模型

进入「配置文件」，选择要使用的配置文件，在「AI 配置」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

更多接入说明请参阅 [MiraRouter 文档](https://docs.mirarouter.com/)。
