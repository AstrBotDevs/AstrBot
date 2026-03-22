# 接入 TokenPony（小马算力）

## 配置对话模型

注册并登录小马算力 [TokenPony](https://www.tokenpony.cn/3YPyf) 。

在小马算力 [API Keys](https://www.tokenpony.cn/#/user/keys) 页面创建一个新的 API Key，留存备用。

在小马算力[模型页面](https://www.tokenpony.cn/#/model)选择需要使用的模型，留存模型名称备用。

进入 AstrBot WebUI，点击左栏 `服务提供商` -> `新增提供商` -> 选择 `小马算力` (需要版本 >= 4.3.3)

![配置对话模型_1](https://files.astrbot.app/docs/source/images/tokenpony/image.png)

> 如果没有看到 `小马算力` 选项，您也可以直接点击图中的 `接入 OpenAI`，并将 `API Base URL` 修改为 `https://api.tokenpony.cn/v1`。

粘贴上面创建和选择的 `API Key` 和 `模型名称`，点击保存，完成创建。您可以点击下方 `服务提供商可用性` 的 `刷新` 按钮测试配置是否成功。

## 应用对话模型

在 AstrBot WebUI，点击左栏 `配置文件`，找到 AI 配置中的 `默认聊天模型`，选择刚刚创建的 `tokenpony`(小马算力) 提供商，点击保存。

![配置对话模型_2](https://files.astrbot.app/docs/source/images/tokenpony/image_1.png)