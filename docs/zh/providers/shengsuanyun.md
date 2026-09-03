# 接入胜算云

[胜算云](https://www.shengsuanyun.com/?from=CH_T70U2X9L) 提供兼容 OpenAI Chat Completions 的统一模型接口，可通过一个 API Key 接入多种模型。

## 获取 API Key

1. 前往[胜算云](https://www.shengsuanyun.com/?from=CH_T70U2X9L)注册并登录。
2. 进入控制台创建并复制 API Key。

## 在 AstrBot 中配置

打开 AstrBot 管理面板，进入 **提供商 → 新增 Provider 来源**，选择 **SSYCloud**，填写 API Key。默认 API Base 为：

```text
https://router.shengsuanyun.com/api/v1
```

保存来源后获取模型，并在配置档的 Provider 设置中选择需要使用的模型。
