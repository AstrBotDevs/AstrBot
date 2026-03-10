# AstrBot 知识库

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



## 附录 2：免费的嵌入模型申请

### PPIO 派欧云

1. 打开 [PPIO 派欧云官网](https://ppio.cn/user/register?invited_by=AIOONE)，并注册账户（通过此链接注册的账户将会获得 15 元人民币的代金券）。
2. 进入 [模型广场](https://ppio.cn/model-api/console)，点击嵌入模型
3. 点击 BAAI:BGE-M3 （截止至 2025-06-02，该模型在该平台免费）。
4. 找到 API 接入指南，申请 Key。
5. 填写 AstrBot OpenAI Embedding 模型提供商配置：
   1. API Key 为刚刚申请的 PPIO 的 API Key
   2. embedding api base 填写 `https://api.ppinfra.com/v3/openai`
   3. model 填写你选择的模型，此例子中为 `baai/bge-m3`。
