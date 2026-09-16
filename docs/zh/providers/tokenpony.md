# 接入 TokenPony（小马算力）

## 配置对话模型

注册并登录小马算力 [TokenPony](https://www.tokenpony.cn/3YPyf) 。

在小马算力 [API Keys](https://www.tokenpony.cn/#/user/keys) 页面创建一个新的 API Key，留存备用。

在小马算力[模型页面](https://www.tokenpony.cn/#/model)选择需要使用的模型，留存模型名称备用。

进入 AstrBot WebUI 的「模型提供商」→「对话」，点击「新增」，选择 `TokenPony`。

填写提供商名称和 `API Key`，确认 `API Base URL`，点击「保存并获取模型」。在模型列表中点击所需模型右侧的 `+`，确认模型已启用；也可先「保存配置」，再通过「自定义模型」填写准确的模型 ID。点击已配置模型旁的「测试模型」按钮可检查是否可用。

## 应用对话模型

进入「配置文件」，选择要使用的配置文件，在「AI 配置」→「模型」中将「对话模型」设为刚添加的模型，点击右下角「保存配置」。此项用于 AstrBot 内置 AI。
