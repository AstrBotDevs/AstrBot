# 接入 Dify

## 安装 Dify

如果您还没有安装 Dify，请参考 [Dify 安装文档](https://docs.dify.ai/zh-hans/getting-started/install-self-hosted) 安装。

## 在 AstrBot 中配置 Dify

在 WebUI 中打开「配置文件」，选择要修改的配置文件，进入「AI 配置」。点击标题右侧「更多操作」（`…`）→「更换执行方式」，选择「Dify」，阅读并勾选配置重置提示后点击「使用此方式」。确保「启用 AI」已打开，然后在本页填写连接参数。切换会重置当前执行方式的配置，详情见 [Agent 执行器](../../use/agent-runner.md)。

在 Dify 中，一个 `API Key` 唯一对应一个 Dify 应用。因此，您可以为不同配置文件填写不同的 API Key 来连接多个 Dify 应用。

AstrBot 的「应用类型」选项包括：

- chat
- chatflow
- agent
- workflow

>[!TIP]
>请确保你在 AstrBot 里设置的 APP 类型和 Dify 里面创建的应用的类型一致。
>![image](https://files.astrbot.app/docs/source/images/dify/image-3.png)

### Chat 和 Agent 应用

按下图所示创建你的 Dify Chat 和 Agent 应用的密钥：

![image](https://files.astrbot.app/docs/source/images/dify/chat-agent-api-key.png)

![image](https://files.astrbot.app/docs/source/images/dify/chat-agent-api-key-2.png)

复制密钥并粘贴到配置中的 `API Key` 字段中，点击「保存配置」。

### Workflow 应用

#### 配置输入输出变量名

Workflow 应用接收输入变量，然后执行工作流，最后输出结果。

![image](https://files.astrbot.app/docs/source/images/dify/workflow-io-key.png)

对于 Workflow 应用，AstrBot 在每次请求时会附上两个变量:

- `astrbot_text_query`: 输入变量名。即用户输入的文本内容。
- `astrbot_session_id`: 会话 ID

你可以在配置中自定义输入变量名，即当前 Dify 设置中的「Prompt 输入变量名」。

您需要修改您的 Workflow 的输入的变量名以适配 AstrBot 的输入。

最终，Workflow 会输出一个结果，您可以自定义这个结果的变量名，即当前 Dify 设置中的「Workflow 输出变量名」，默认为  `astrbot_wf_output`。你需要在 Dify 的 Workflow 的输出节点中配置这个变量名，否则 AstrBot 无法正确解析。

#### 创建 API Key

按下图所示创建你的 Dify Workflow 应用的 API Key：

点击右上角发布-访问 API-点击右上角 API 密钥-创建密钥，然后复制 API Key。

![image](https://files.astrbot.app/docs/source/images/dify/workflow-api-key.png)

复制密钥并粘贴到配置中的 `API Key` 字段中，点击「保存配置」。

## 保存配置

填写完成后，点击右下角「保存配置」。该配置文件将直接使用上述执行方式和连接参数，无需另外创建或选择执行器提供商 ID。

## 附录：在聊天时动态设置输入 Workflow 变量（可选）

可以使用 `/set` 指令动态设置输入变量，如下图所示：

![alt text](https://files.astrbot.app/docs/source/images/dify/image-5.png)

当设置变量后，AstrBot 会在下次向 Dify 请求时附上您设置的变量，以灵活适配您的 Workflow。
    
![alt text](https://files.astrbot.app/docs/source/images/dify/image-4.png)

当然，可以使用 `/unset` 指令来取消设置的变量。

变量在当前会话永久有效。
