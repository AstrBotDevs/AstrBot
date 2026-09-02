# 接入 MiraRouter

[MiraRouter](https://mirarouter.com/) 提供稳定、安全且兼容 OpenAI 格式的统一模型 API，可通过一个 API Key 接入多种主流模型，并集中管理密钥、用量与成本。

## 获取 API Key

1. 前往 [MiraRouter](https://mirarouter.com/) 注册并登录账号。
2. 进入控制台，创建并复制 API Key。完整密钥仅在创建时显示，请妥善保存。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **提供商 → 新增 Provider 来源 → MiraRouter**，填写以下信息：

| 配置项       | 值                                 |
| ------------ | ---------------------------------- |
| 提供商名称   | `MiraRouter`                       |
| API Base URL | `https://api.mirarouter.com/v1`    |
| API Key      | 在 MiraRouter 控制台创建的 API Key |

AstrBot 会自动为 MiraRouter 请求添加 `X-APP-CODE: astrbot` 标识。

保存来源后，根据 [MiraRouter 模型与价格](https://mirarouter.com/models) 页面中的模型列表添加需要使用的模型。

## 设为默认模型

进入 **配置文件 → 提供商设置**，将「默认聊天模型」设置为刚刚添加的 MiraRouter 模型，然后保存配置。

更多接入说明请参阅 [MiraRouter 文档](https://docs.mirarouter.com/)。
