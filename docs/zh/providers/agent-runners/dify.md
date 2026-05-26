# 接入 Dify

## 安装 Dify

如果您还没有安装 Dify，请参考 [Dify 安装文档](https://docs.dify.ai/zh-hans/getting-started/install-self-hosted) 安装。

## 在 AstrBot 中配置 Dify

在 WebUI 中，点击「模型提供商」->「新增提供商」，选择「Agent 执行器」，选择「Dify」，进入 Dify 的配置页面。

![image](https://files.astrbot.app/docs/source/images/dify/image.png)

在 Dify 中，一个 `API Key` 唯一对应一个 Dify 应用。因此，您可以创建多个 Provider 以适配多个 Dify 应用。

根据目前的 Dify 项目，一共有三种类型，分别是：

- chat
- agent
- workflow

>[!TIP]
>请确保你在 AstrBot 里设置的 APP 类型和 Dify 里面创建的应用的类型一致。
>![image](https://files.astrbot.app/docs/source/images/dify/image-3.png)


### Chat 和 Agent 应用

按下图所示创建你的 Dify Chat 和 Agent 应用的密钥：

![image](https://files.astrbot.app/docs/source/images/dify/chat-agent-api-key.png)

![image](https://files.astrbot.app/docs/source/images/dify/chat-agent-api-key-2.png)

复制密钥并粘贴到配置中的 `API Key` 字段中，点击「保存」。

### Workflow 应用

#### 配置输入输出变量名

Workflow 应用接收输入变量，然后执行工作流，最后输出结果。

![image](https://files.astrbot.app/docs/source/images/dify/workflow-io-key.png)

对于 Workflow 应用，AstrBot 在每次请求时会附上两个变量:

- `astrbot_text_query`: 输入变量名。即用户输入的文本内容。
- `astrbot_session_id`: 会话 ID

你可以在配置中自定义输入变量名，即上图配置中的 “Prompt 输入变量名”。

您需要修改您的 Workflow 的输入的变量名以适配 AstrBot 的输入。

最终，Workflow 会输出一个结果，您可以自定义这个结果的变量名，即上图配置中的 “Dify Workflow 输出变量名”，默认为  `astrbot_wf_output`。你需要在 Dify 的 Workflow 的输出节点中配置这个变量名，否则 AstrBot 无法正确解析。

#### 创建 API Key

按下图所示创建你的 Dify Workflow 应用的 API Key：

点击右上角发布-访问 API-点击右上角 API 密钥-创建密钥，然后复制 API Key。

![image](https://files.astrbot.app/docs/source/images/dify/workflow-api-key.png)

复制密钥并粘贴到配置中的 `API Key` 字段中，点击「保存」。

### 选择 Agent 执行器

进入左边栏配置页面，点击「Agent 执行方式」，选择「Dify」，然后在下方出现的新的配置项中选择你刚刚创建的 Dify Agent 执行器的 ID，点击右下角「保存」，即可完成配置。

## 附录：在聊天时动态设置输入 Workflow 变量（可选）

可以使用 `/set` 指令动态设置输入变量，如下图所示：

![alt text](https://files.astrbot.app/docs/source/images/dify/image-5.png)

当设置变量后，AstrBot 会在下次向 Dify 请求时附上您设置的变量，以灵活适配您的 Workflow。
    
![alt text](https://files.astrbot.app/docs/source/images/dify/image-4.png)

当然，可以使用 `/unset` 指令来取消设置的变量。

变量在当前会话永久有效。