# 接入胜算云

[胜算云](https://www.shengsuanyun.com/?from=CH_T70U2X9L) 提供兼容 OpenAI 等格式的统一模型接口，可通过一个 API Key 接入多种主流模型。

## 获取 API Key

1. 前往 [胜算云](https://www.shengsuanyun.com/?from=CH_T70U2X9L) 注册并登录账号。
2. 进入控制台，创建并复制 API Key。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **服务提供商 → 新增提供商 → OpenAI**，填写以下信息：

| 配置项 | 值 |
| --- | --- |
| 提供商名称 | `胜算云` |
| API Base URL | `https://router.shengsuanyun.com/api/v1` |
| API Key | 在胜算云控制台创建的 API Key |

保存后，点击该提供商卡片，根据胜算云控制台中的模型列表添加需要使用的模型。

## 设为默认模型

进入 **配置文件 → 提供商设置**，将「默认聊天模型」设置为刚刚添加的胜算云模型，然后保存配置。
