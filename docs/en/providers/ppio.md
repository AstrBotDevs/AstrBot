# 接入 PPIO 派欧云

PPIO 派欧云是中国领先的独立分布式云计算服务商，您可以在派欧云上使用稳定、低价甚至免费的模型服务。

## 准备

打开 [PPIO 派欧云官网](https://ppio.cn/user/register?invited_by=AIOONE)，并注册账户（通过此链接注册的账户将会获得 15 元人民币的代金券）。

进入 [模型 API 服务](https://ppio.cn/model-api/console)，找到你想接入的模型。你可以通过筛选器选择不同厂商或者免费的模型。

![image](https://files.astrbot.app/docs/source/images/ppio/image-1.png)

找到你想要接入的模型后，点击模型卡片，侧边会展开一个模型详情卡片，找到下方的 API 接入指南，如果您还没创建过 Key 可以点击创建。

![image](https://files.astrbot.app/docs/source/images/ppio/image-3.png)

打开 AstrBot 控制台 -> 服务提供商页面，点击新增提供商，找到并点击 `PPIO派欧云`(需要版本 >= 3.5.10，旧版本也可使用，见下文)。

![image](https://files.astrbot.app/docs/source/images/ppio/image.png)

将 API Key 和模型名称填入对话框表单，点击保存，即可完成创建。

> [!TIP]
> 如果您是 AstrBot 旧版本（< 3.5.10）的用户，请打开 AstrBot 控制台 -> 服务提供商页面，点击新增提供商，找到 `OpenAI`，点击进入。
> 1. 将 ID 命名为 `ppio`（随意）
> 2. 然后将 `API Base URL` 设置为 `https://api.ppinfra.com/v3/openai`
> 3. 然后将 API Key 和模型名称填入对话框表单，点击保存，即可完成创建。


## 使用

对机器人输入 `/provider` 指令，将提供商切换到刚刚添加的 PPIO 派欧云提供商，即可使用。

## 常见问题

#### 显示 `400` 错误

```log
Error code: 400 - {'code': 400, 'message': '"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set', 'type': 'BadRequestError'}
```


请暂时使用 `/tool off_all` 禁用所有的函数调用工具即可使用，或者换用其他模型。