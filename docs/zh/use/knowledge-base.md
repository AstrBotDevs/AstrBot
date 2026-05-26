# AstrBot 知识库

> [!TIP]
> 需要 AstrBot 版本 >= 4.5.0。
>
> 我们在 4.5.0 版本中重新设计了全新的知识库系统，AstrBot 将原生支持知识库功能。下文介绍的是新版知识库的使用方法。如果您使用的是之前的版本，请参考[旧版知识库使用文档](/use/knowledge-base-old.html)，我们建议您升级到最新版以获得更好的体验。

![知识库预览](https://files.astrbot.app/docs/zh/use/image-3.png)

## 配置嵌入模型

打开服务提供商页面，点击新增服务提供商，选择 Embedding。

目前 AstrBot 支持兼容 OpenAI API 和 Gemini API 的嵌入向量服务。

点击上面的提供商卡片进入配置页面，填写配置。

配置完成后，点击保存。

## 配置重排序模型（可选）

重排序模型可以一定程度上提高最终召回结果的精度。

和嵌入模型的配置类似，打开服务提供商页面，点击新增服务提供商，选择重排序。有关重排序模型的更多信息请参考网络。

## 创建知识库

AstrBot 支持多知识库管理。在聊天时，您可以**自由指定知识库**。

进入知识库页面，点击创建知识库，如下图所示：

![image](https://files.astrbot.app/docs/source/images/knowledge-base/image.png)

填写相关信息。在嵌入模型下拉菜单中您将看到刚刚创建好的嵌入模型和重排序模型（重排序模型可选）。

> [!TIP]
> 一旦选择了一个知识库的嵌入模型，请不要再修改该提供商的**模型**或者**向量维度信息**，否则将**严重影响**该知识库的召回率甚至**报错**。

## 上传文件

创建好知识库之后，可以为知识库上传文档。支持同时上传最多 10 个文件，单个文件大小不超过 128 MB。

![上传文件](https://files.astrbot.app/docs/zh/use/image-4.png)

## 使用知识库

在配置文件中，可以为不同的配置文件指定不同的知识库。

## 附录：高性价比的嵌入模型申请

### 硅基流动

截止至 2026 年 5 月 3 日，`BAAI/bge-m3` 模型在该平台免费。

1. 打开 [硅基流动官网](https://cloud.siliconflow.cn/i/zMCYMSt2)，注册账户并完成实名认证。
2. 打开 [API 密钥](https://cloud.siliconflow.cn/me/account/ak)。
5. 填写 AstrBot OpenAI Embedding 模型提供商配置：
   1. API Key 为刚刚申请的硅基流动的 API Key
   2. embedding api base 填写 `https://api.siliconflow.cn/v1`
   3. model 填写你选择的模型，此例子中为 `BAAI/bge-m3`。
