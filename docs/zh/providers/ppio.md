# 接入 PPIO 派欧云

PPIO 派欧云是中国领先的独立分布式云计算服务商，您可以在派欧云上使用稳定、低价甚至免费的模型服务。

## 准备

打开 [PPIO 派欧云官网](https://ppio.cn/user/register?invited_by=AIOONE)，并注册账户（通过此链接注册的账户将会获得 15 元人民币的代金券）。

进入 [模型 API 服务](https://ppio.cn/model-api/console)，找到你想接入的模型。你可以通过筛选器选择不同厂商或者免费的模型。

![image](https://files.astrbot.app/docs/source/images/ppio/image-1.png)

找到你想要接入的模型后，点击模型卡片，侧边会展开一个模型详情卡片，找到下方的 API 接入指南，如果您还没创建过 Key 可以点击创建。

![image](https://files.astrbot.app/docs/source/images/ppio/image-3.png)

进入 AstrBot WebUI 的「模型提供商」→「对话」，点击「新增」，选择 `PPIO`。

填写提供商名称和 `API Key`，确认 `API Base URL`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

## 使用

进入「配置文件」，选择要使用的配置文件，在「AI 配置」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。

对机器人输入 `/provider` 指令，将提供商切换到刚刚添加的 PPIO 派欧云提供商，即可使用。

## 常见问题

#### 显示 `400` 错误

```log
Error code: 400 - {'code': 400, 'message': '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set', 'type': 'BadRequestError'}
```

请在 WebUI 中关闭所有调用工具后即可使用，或者换用其他模型。
